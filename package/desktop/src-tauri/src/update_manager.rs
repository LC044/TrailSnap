use crate::{data_directory::DataDirectory, portable, update_network, update_transaction};
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
    let client = update_network::client()?;
    let mut info = update_network::first_valid(&update_network::candidates(&url), |url| {
        let client = client.clone();
        async move {
            let catalog = client
                .get(url)
                .timeout(update_network::CATALOG_TIMEOUT)
                .send()
                .await
                .map_err(|e| e.to_string())?
                .error_for_status()
                .map_err(|e| e.to_string())?
                .json::<serde_json::Value>()
                .await
                .map_err(|e| e.to_string())?;
            parse_catalog(catalog)
        }
    })
    .await?;
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
    progress(&app, &info);
    Ok(info)
}

fn parse_catalog(catalog: serde_json::Value) -> Result<UpdateInfo, String> {
    if catalog["schemaVersion"] != 1 {
        return Err("便携更新清单版本不兼容".into());
    }
    let mut info: UpdateInfo =
        serde_json::from_value(catalog["platforms"][update_transaction::platform()].clone())
            .map_err(|e| e.to_string())?;
    semver::Version::parse(&info.version).map_err(|e| e.to_string())?;
    let url = reqwest::Url::parse(&info.url).map_err(|_| "更新下载地址无效")?;
    if url.scheme() != "https" && !(url.scheme() == "http" && url.host_str() == Some("127.0.0.1")) {
        return Err("更新下载地址必须使用 HTTPS".into());
    }
    if info.size == 0 || info.size > 4 * 1024 * 1024 * 1024 {
        return Err("更新包体积无效".into());
    }
    if info.signature.trim().is_empty()
        || info.sha256.len() != 64
        || !info.sha256.bytes().all(|byte| byte.is_ascii_hexdigit())
    {
        return Err("更新清单缺少有效签名或 SHA-256".into());
    }
    // Download state is local; a remote catalog cannot claim to be verified.
    info.phase.clear();
    info.downloaded = 0;
    info.error = None;
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
    let result = download_and_stage(&instance_root, &mut info, |info| progress(&app, info)).await;
    progress(&app, &info);
    result?;
    Ok(info)
}

async fn download_and_stage(
    instance_root: &std::path::Path,
    info: &mut UpdateInfo,
    on_progress: impl Fn(&UpdateInfo),
) -> Result<(), String> {
    let sources = update_network::candidates(&info.url);
    download_and_stage_from(instance_root, info, on_progress, sources).await
}

async fn download_and_stage_from(
    instance_root: &std::path::Path,
    info: &mut UpdateInfo,
    on_progress: impl Fn(&UpdateInfo),
    sources: Vec<String>,
) -> Result<(), String> {
    let download = instance_root
        .join("maintenance")
        .join(format!("download-{}.zip", uuid::Uuid::new_v4()));
    let result = async {
        fs::create_dir_all(download.parent().ok_or("下载目录无效")?).map_err(|e| e.to_string())?;
        let sources = update_network::rank(sources).await;
        let mut last_error = String::new();
        for round in 0..update_network::ROUNDS {
            update_network::backoff(round).await;
            for url in &sources {
                info.downloaded = 0;
                info.error = None;
                on_progress(info);
                let attempt = async {
                    let client = update_network::client()?;
                    let response = tokio::time::timeout(
                        update_network::IDLE_TIMEOUT,
                        client
                            .get(url)
                            .timeout(std::time::Duration::from_secs(60 * 60))
                            .send(),
                    )
                    .await
                    .map_err(|_| "更新下载响应超时")?
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
                        tokio::time::timeout(update_network::IDLE_TIMEOUT, stream.next())
                            .await
                            .map_err(|_| "更新下载超时")?
                    {
                        let chunk = chunk.map_err(|e| e.to_string())?;
                        info.downloaded += chunk.len() as u64;
                        if info.downloaded > info.size {
                            return Err("下载体积超出签名清单".into());
                        }
                        output.write_all(&chunk).map_err(|e| e.to_string())?;
                        on_progress(info);
                    }
                    output.sync_all().map_err(|e| e.to_string())?;
                    drop(output);
                    if info.downloaded != info.size {
                        return Err("更新包下载不完整".into());
                    }
                    let archive = download.clone();
                    let signature = info.signature.clone();
                    let hash = info.sha256.clone();
                    tauri::async_runtime::spawn_blocking(move || {
                        update_transaction::verify_archive(&archive, &signature, &hash)
                    })
                    .await
                    .map_err(|e| e.to_string())??;
                    Ok::<(), String>(())
                }
                .await;
                match attempt {
                    Ok(()) => return stage_download(instance_root, &download, info).await,
                    Err(error) => {
                        last_error = error;
                        let _ = fs::remove_file(&download);
                    }
                }
            }
        }
        Err(format!(
            "所有更新源下载失败（已自动重试），请稍后重试：{last_error}"
        ))
    }
    .await;
    let _ = fs::remove_file(download);
    match result {
        Ok(()) => info.phase = "ready".into(),
        Err(error) => {
            info.phase = "error".into();
            info.error = Some(error.clone());
            return Err(error);
        }
    }
    Ok(())
}

async fn stage_download(
    instance_root: &std::path::Path,
    download: &std::path::Path,
    info: &UpdateInfo,
) -> Result<(), String> {
    let staging_root = instance_root.to_path_buf();
    let archive = download.to_path_buf();
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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn catalog_validation_rejects_bad_sources_and_discards_remote_download_state() {
        let mut catalog = serde_json::json!({"schemaVersion": 1, "platforms": {}});
        let platform = update_transaction::platform();
        catalog["platforms"][&platform] = serde_json::json!({
            "version": "1.2.3", "url": "https://example.com/update.zip",
            "signature": "signature", "sha256": "a".repeat(64), "size": 4,
            "phase": "ready", "downloaded": 4, "error": "remote state"
        });
        let info = parse_catalog(catalog.clone()).unwrap();
        assert_eq!(info.phase, "");
        assert_eq!(info.downloaded, 0);
        assert!(info.error.is_none());
        for (field, value) in [
            ("version", serde_json::json!("invalid")),
            ("url", serde_json::json!("http://example.com/file")),
            ("size", serde_json::json!(0)),
        ] {
            let mut invalid = catalog.clone();
            invalid["platforms"][&platform][field] = value;
            assert!(parse_catalog(invalid).is_err());
        }
        catalog["schemaVersion"] = serde_json::json!(2);
        assert!(parse_catalog(catalog).is_err());
    }

    #[tokio::test]
    async fn failed_and_truncated_sources_are_retried_without_installing_unsigned_bytes() {
        use axum::{
            body::Body,
            http::{Response, StatusCode},
            routing::get,
            Router,
        };
        use std::sync::{
            atomic::{AtomicUsize, Ordering},
            Arc,
        };
        let count = Arc::new(AtomicUsize::new(0));
        let app = Router::new()
            .route(
                "/offline",
                get(|| async { (StatusCode::BAD_GATEWAY, "offline") }),
            )
            .route(
                "/archive",
                get({
                    let count = count.clone();
                    move |headers: axum::http::HeaderMap| {
                        let count = count.clone();
                        async move {
                            if headers.contains_key("range") {
                                return Response::builder()
                                    .status(206)
                                    .body(Body::from("t"))
                                    .unwrap();
                            }
                            // First actual transfer ends early; second reaches signature verification.
                            let body = if count.fetch_add(1, Ordering::SeqCst) == 0 {
                                "te"
                            } else {
                                "test"
                            };
                            Response::new(Body::from(body))
                        }
                    }
                }),
            );
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = listener.local_addr().unwrap();
        let server = tokio::spawn(async move {
            axum::serve(listener, app).await.unwrap();
        });
        let root = std::env::temp_dir().join(uuid::Uuid::new_v4().to_string());
        let mut info = UpdateInfo {
            size: 4,
            phase: "downloading".into(),
            ..Default::default()
        };
        let progress = Mutex::new(Vec::new());
        let error = download_and_stage_from(
            &root,
            &mut info,
            |value| {
                progress.lock().unwrap().push(value.downloaded);
            },
            vec![
                format!("http://{address}/offline"),
                format!("http://{address}/archive"),
            ],
        )
        .await
        .unwrap_err();
        server.abort();
        assert!(error.contains("已自动重试"));
        assert_eq!(count.load(Ordering::SeqCst), update_network::ROUNDS);
        assert!(progress
            .lock()
            .unwrap()
            .windows(2)
            .any(|p| p[0] == 2 && p[1] == 0));
        assert_eq!(info.phase, "error");
        assert!(info.error.is_some());
        assert!(!update_transaction::journal_path(&root).exists());
        assert_eq!(fs::read_dir(root.join("maintenance")).unwrap().count(), 0);
        fs::remove_dir_all(root).unwrap();
    }

    #[tokio::test]
    async fn directory_failure_leaves_retryable_state_and_retry_reaches_download() {
        let root = std::env::temp_dir().join(uuid::Uuid::new_v4().to_string());
        fs::create_dir_all(&root).unwrap();
        fs::write(root.join("maintenance"), b"blocked").unwrap();
        let mut info = UpdateInfo {
            phase: "downloading".into(),
            size: 4,
            ..Default::default()
        };
        assert!(download_and_stage(&root, &mut info, |_| {}).await.is_err());
        assert_eq!(info.phase, "error");
        assert!(info.error.is_some());
        fs::remove_file(root.join("maintenance")).unwrap();
        let listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        info.url = format!("http://{}/update.zip", listener.local_addr().unwrap());
        let server =
            std::thread::spawn(move || {
                use std::io::{Read, Write};
                for _ in 0..update_network::ROUNDS {
                    let (mut socket, _) = listener.accept().unwrap();
                    socket
                        .set_read_timeout(Some(std::time::Duration::from_secs(5)))
                        .unwrap();
                    let mut buffer = [0; 4096];
                    let _ = socket.read(&mut buffer).unwrap();
                    socket
                .write_all(b"HTTP/1.1 200 OK\r\nContent-Length: 4\r\nConnection: close\r\n\r\ntest")
                .unwrap();
                }
            });
        info.phase = "downloading".into();
        // A retry downloads all bytes; the deliberately unsigned payload fails
        // verification and is removed, rather than leaving a stuck operation.
        assert!(download_and_stage(&root, &mut info, |_| {}).await.is_err());
        server.join().unwrap();
        assert_eq!(info.downloaded, 4);
        assert_eq!(info.phase, "error");
        assert_eq!(fs::read_dir(root.join("maintenance")).unwrap().count(), 0);
        fs::remove_dir_all(root).unwrap();
    }
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
