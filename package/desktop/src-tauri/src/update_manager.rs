use crate::{data_directory::DataDirectory, portable, update_transaction};
use futures_util::StreamExt;
use serde::{Deserialize, Serialize};
use std::{fs, io::Write, sync::Mutex};
use tauri::{Emitter, Manager};

#[derive(Clone, Default, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct UpdateInfo {
    pub version: String,
    pub url: String,
    pub signature: String,
    pub sha256: String,
    pub size: u64,
    #[serde(default)]
    pub phase: String,
    #[serde(default)]
    pub downloaded: u64,
    #[serde(default)]
    pub error: Option<String>,
}
#[derive(Default)]
pub struct UpdateState(pub Mutex<UpdateInfo>);

fn root(app: &tauri::AppHandle) -> Result<std::path::PathBuf, String> {
    app.state::<DataDirectory>()
        .instance_root
        .clone()
        .ok_or("此更新接口仅用于便携实例".into())
}
fn progress(app: &tauri::AppHandle, info: &UpdateInfo) {
    *app.state::<UpdateState>().0.lock().expect("update state") = info.clone();
    let _ = app.emit("desktop-update-status", info);
}

#[tauri::command]
pub async fn desktop_update_check(app: tauri::AppHandle) -> Result<UpdateInfo, String> {
    let _activity = crate::begin_activity(&app)?;
    let instance_root = root(&app)?;
    if app
        .state::<UpdateState>()
        .0
        .lock()
        .expect("update state")
        .phase
        == "downloading"
    {
        return Err("更新下载正在进行".into());
    }
    let journal = update_transaction::journal_path(&instance_root);
    if journal.exists() {
        let tx: update_transaction::UpdateTransaction = portable::read_json(&journal)?;
        if tx.phase == "verified" {
            let info = UpdateInfo {
                version: tx.version,
                phase: "ready".into(),
                ..Default::default()
            };
            progress(&app, &info);
            return Ok(info);
        }
    }
    let url = std::env::var("TS_PORTABLE_UPDATE_CATALOG_URL").unwrap_or_else(|_| {
        "https://github.com/LC044/TrailSnap/releases/latest/download/portable-latest.json".into()
    });
    let response = reqwest::Client::new()
        .get(url)
        .timeout(std::time::Duration::from_secs(30))
        .send()
        .await
        .map_err(|e| e.to_string())?
        .error_for_status()
        .map_err(|e| e.to_string())?;
    let catalog: serde_json::Value = response.json().await.map_err(|e| e.to_string())?;
    if catalog["schemaVersion"] != 1 {
        return Err("便携更新清单版本不兼容".into());
    }
    let mut info: UpdateInfo =
        serde_json::from_value(catalog["platforms"][update_transaction::platform()].clone())
            .map_err(|e| e.to_string())?;
    let config = portable::load_instance(&instance_root)?;
    let build: portable::BuildManifest = portable::read_json(
        &instance_root
            .join("app")
            .join(&config.active_build)
            .join("manifest.json"),
    )?;
    let newer = semver::Version::parse(&info.version).map_err(|e| e.to_string())?
        > semver::Version::parse(&build.version).map_err(|e| e.to_string())?;
    info.phase = if newer { "available" } else { "current" }.into();
    if !info.url.starts_with("https://") && !info.url.starts_with("http://127.0.0.1:") {
        return Err("更新下载地址必须使用 HTTPS".into());
    }
    if info.size == 0 || info.size > 4 * 1024 * 1024 * 1024 {
        return Err("更新包体积无效".into());
    }
    progress(&app, &info);
    Ok(info)
}

#[tauri::command]
pub async fn desktop_update_download(app: tauri::AppHandle) -> Result<UpdateInfo, String> {
    let _activity = crate::begin_activity(&app)?;
    let instance_root = root(&app)?;
    let mut info = {
        let state = app.state::<UpdateState>();
        let mut current = state.0.lock().expect("update state");
        if current.phase != "available" && current.phase != "error" {
            return Err("请先检查更新".into());
        }
        current.phase = "downloading".into();
        current.downloaded = 0;
        current.error = None;
        current.clone()
    };
    progress(&app, &info);
    let download = instance_root
        .join("maintenance")
        .join(format!("download-{}.zip", uuid::Uuid::new_v4()));
    fs::create_dir_all(download.parent().ok_or("下载目录无效")?).map_err(|e| e.to_string())?;
    let result = async {
        let response = reqwest::Client::new()
            .get(&info.url)
            .send()
            .await
            .map_err(|e| e.to_string())?
            .error_for_status()
            .map_err(|e| e.to_string())?;
        let mut stream = response.bytes_stream();
        let mut output = fs::OpenOptions::new()
            .create_new(true)
            .write(true)
            .open(&download)
            .map_err(|e| e.to_string())?;
        while let Some(chunk) =
            tokio::time::timeout(std::time::Duration::from_secs(45), stream.next())
                .await
                .map_err(|_| "更新下载超时")?
        {
            let chunk = chunk.map_err(|e| e.to_string())?;
            info.downloaded += chunk.len() as u64;
            if info.downloaded > info.size {
                return Err("下载体积超出签名清单".into());
            }
            output.write_all(&chunk).map_err(|e| e.to_string())?;
            progress(&app, &info);
        }
        output.sync_all().map_err(|e| e.to_string())?;
        drop(output);
        if info.downloaded != info.size {
            return Err("更新包下载不完整".into());
        }
        let staging_root = instance_root.clone();
        let archive = download.clone();
        let signature = info.signature.clone();
        let hash = info.sha256.clone();
        let version = info.version.clone();
        tauri::async_runtime::spawn_blocking(move || {
            update_transaction::stage_update(&staging_root, &archive, &signature, &hash, &version)
        })
        .await
        .map_err(|e| e.to_string())??;
        Ok::<(), String>(())
    }
    .await;
    let _ = fs::remove_file(download);
    match result {
        Ok(()) => info.phase = "ready".into(),
        Err(error) => {
            info.phase = "error".into();
            info.error = Some(error.clone());
            progress(&app, &info);
            return Err(error);
        }
    }
    progress(&app, &info);
    Ok(info)
}

#[tauri::command]
pub fn desktop_update_status(app: tauri::AppHandle) -> Result<serde_json::Value, String> {
    let instance_root = root(&app)?;
    let path = update_transaction::journal_path(&instance_root);
    let transaction: Option<update_transaction::UpdateTransaction> = if path.exists() {
        Some(portable::read_json(&path)?)
    } else {
        None
    };
    let backup_path = transaction.as_ref().map(|tx| {
        app.state::<DataDirectory>()
            .root()
            .join("backups")
            .join(&tx.id)
    });
    Ok(
        serde_json::json!({"download":app.state::<UpdateState>().0.lock().expect("update state").clone(),
        "transaction":transaction,"backupPath":backup_path}),
    )
}

#[tauri::command]
pub async fn desktop_update_apply(app: tauri::AppHandle) -> Result<(), String> {
    let instance_root = root(&app)?;
    let mut tx: update_transaction::UpdateTransaction =
        portable::read_json(&update_transaction::journal_path(&instance_root))?;
    if tx.phase != "verified" {
        return Err("请先下载并校验更新".into());
    }
    crate::drain_desktop(&app, "portable-update").await?;
    tx.phase = "apply_requested".into();
    update_transaction::publish(&instance_root, &tx)?;
    app.exit(0);
    Ok(())
}
