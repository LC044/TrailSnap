//! Persist the copy operation before stopping services so failures remain recoverable.
use crate::{data_directory, portable, DataDirectory};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
#[cfg(windows)]
use std::os::windows::process::CommandExt;
use std::{
    io::{BufRead, BufReader, Read},
    path::{Path, PathBuf},
    process::{Command, Stdio},
};
use tauri::{Emitter, Manager};

#[derive(Clone, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Operation {
    pub id: String,
    pub source: PathBuf,
    pub target: PathBuf,
    pub copy_external: bool,
    pub activate: bool,
    pub phase: String,
    pub error: Option<String>,
}

fn record(app: &tauri::AppHandle) -> Result<PathBuf, String> {
    app.state::<DataDirectory>()
        .instance_root
        .as_ref()
        .map(|p| p.join("maintenance/import-operation.json"))
        .ok_or("请先安装新版 Windows 客户端".into())
}

pub async fn helper(
    app: &tauri::AppHandle,
    args: Vec<String>,
    operation: Option<String>,
) -> Result<Value, String> {
    let executable =
        crate::server_executable(&app.path().resource_dir().map_err(|e| e.to_string())?);
    let handle = app.clone();
    let origin = app.state::<DataDirectory>().instance_root.clone();
    let previous_data = app.state::<DataDirectory>().root();
    tauri::async_runtime::spawn_blocking(move || {
        let mut command = Command::new(executable);
        command
            .args(args)
            .env("PYTHONIOENCODING", "utf-8")
            .stdin(Stdio::null())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());
        if let Some(id) = operation {
            command.env("TS_IMPORT_OPERATION", id);
            command.env("TS_IMPORT_PREVIOUS_DATA", &previous_data);
            if let Some(origin) = &origin {
                command.env("TS_IMPORT_ORIGIN", origin);
                let config = portable::load_instance(origin)?;
                command.env("TS_IMPORT_ORIGIN_ID", config.instance_id);
            }
        }
        #[cfg(windows)]
        command.creation_flags(0x08000000);
        let mut child = command.spawn().map_err(|e| e.to_string())?;
        let stderr = child.stderr.take().ok_or("无法读取复制日志")?;
        let reader = std::thread::spawn(move || {
            let mut errors = String::new();
            for line in BufReader::new(stderr).lines().map_while(Result::ok) {
                if let Ok(progress) = serde_json::from_str::<Value>(&line) {
                    if progress["importProgress"] == true {
                        let _ = handle.emit("desktop-import-progress", progress);
                        continue;
                    }
                }
                errors.push_str(&line);
                errors.push('\n');
            }
            errors
        });
        let mut output = String::new();
        child
            .stdout
            .take()
            .ok_or("无法读取复制结果")?
            .read_to_string(&mut output)
            .map_err(|e| e.to_string())?;
        let status = child.wait().map_err(|e| e.to_string())?;
        let error = reader.join().map_err(|_| "复制日志读取失败")?;
        if !status.success() {
            return Err(error);
        }
        serde_json::from_str(
            output
                .lines()
                .rev()
                .find(|line| line.starts_with('{'))
                .ok_or("检查结果缺失")?,
        )
        .map_err(|e| e.to_string())
    })
    .await
    .map_err(|e| e.to_string())?
}

#[tauri::command]
pub async fn desktop_legacy_discovery(app: tauri::AppHandle) -> Result<Value, String> {
    let state = app.state::<DataDirectory>();
    let Some(root) = &state.instance_root else {
        return Ok(json!({"candidates":[],"notices":[],"currentPhotos":0,"completed":true}));
    };
    let mut result = helper(
        &app,
        vec![
            "--discover-old-data".into(),
            root.to_string_lossy().into(),
            state.root().to_string_lossy().into(),
        ],
        None,
    )
    .await?;
    let conversion: Option<Value> = portable::read_json(&root.join("conversion.json")).ok();
    result["previousEntry"] = conversion
        .as_ref()
        .and_then(|v| v.get("previousEntry"))
        .cloned()
        .unwrap_or(Value::Null);
    if root.join("maintenance/library-link.json").is_file() {
        result["completed"] = json!(true);
    }
    result["dismissed"] = json!(root.join("maintenance/legacy-dismissed.json").is_file());
    result["operation"] = if record(&app)?.exists() {
        portable::read_json::<Value>(&record(&app)?)?
    } else {
        Value::Null
    };
    result["canResume"] = json!(result["operation"]["target"]
        .as_str()
        .and_then(|target| {
            portable::read_json::<Value>(&Path::new(target).join("conversion.json")).ok()
        })
        .is_some_and(|proof| proof["operationId"] == result["operation"]["id"]));
    Ok(result)
}

#[tauri::command]
pub fn desktop_dismiss_legacy(app: tauri::AppHandle) -> Result<(), String> {
    let root = app
        .state::<DataDirectory>()
        .instance_root
        .clone()
        .ok_or("未找到当前图库")?;
    portable::write_json(
        &root.join("maintenance/legacy-dismissed.json"),
        &json!({"dismissed":true}),
    )
}

#[tauri::command]
pub async fn desktop_import_space(
    app: tauri::AppHandle,
    source_path: String,
    path: String,
    copy_external: bool,
) -> Result<Value, String> {
    let target = data_directory::validate_target(Path::new(&source_path), Path::new(&path))?;
    data_directory::validate_target(&app.state::<DataDirectory>().root(), &target)?;
    if let Some(root) = &app.state::<DataDirectory>().instance_root {
        data_directory::validate_target(root, &target)?;
    }
    helper(
        &app,
        vec![
            "--import-space".into(),
            source_path,
            target.to_string_lossy().into(),
            app.path()
                .resource_dir()
                .map_err(|e| e.to_string())?
                .to_string_lossy()
                .into(),
            if copy_external { "1" } else { "0" }.into(),
        ],
        None,
    )
    .await
}

pub async fn start(
    app: tauri::AppHandle,
    source: PathBuf,
    target: PathBuf,
    copy_external: bool,
    activate: bool,
) -> Result<Value, String> {
    let resource = app.path().resource_dir().map_err(|e| e.to_string())?;
    let space = helper(
        &app,
        vec![
            "--import-space".into(),
            source.to_string_lossy().into(),
            target.to_string_lossy().into(),
            resource.to_string_lossy().into(),
            if copy_external { "1" } else { "0" }.into(),
        ],
        None,
    )
    .await?;
    if space["enough"] != true {
        return Err("目标磁盘空间不足，请换一个磁盘后重试".into());
    }
    let op = Operation {
        id: uuid::Uuid::new_v4().to_string(),
        source,
        target,
        copy_external,
        activate,
        phase: "copying".into(),
        error: None,
    };
    // Do not orphan a previous recovery operation by overwriting its record.
    if record(&app)?.exists() {
        let old: Operation = portable::read_json(&record(&app)?)?;
        if old.phase != "completed" {
            return Err("上次复制尚未完成，请先重新验证副本或清理未完成的临时文件".into());
        }
    }
    portable::write_json(&record(&app)?, &op)?;
    execute(app, op, false).await
}

async fn execute(app: tauri::AppHandle, mut op: Operation, resume: bool) -> Result<Value, String> {
    let result: Result<Value, String> = async {
        if resume {
            // A private operation nonce proves this is OUR published copy.
            let proof: Value = portable::read_json(&op.target.join("conversion.json"))?;
            if proof["operationId"] != op.id {
                return Err("所选副本不属于上次复制操作，已停止验证".into());
            }
        }
        crate::drain_desktop(&app).await?;
        if !resume {
            let resource = app.path().resource_dir().map_err(|e| e.to_string())?;
            let mut args = vec![
                "--parent-pid".into(),
                std::process::id().to_string(),
                "--convert-portable".into(),
                op.source.to_string_lossy().into(),
                op.target.to_string_lossy().into(),
                resource.to_string_lossy().into(),
                resource
                    .join("portable-launcher.exe")
                    .to_string_lossy()
                    .into(),
            ];
            if op.copy_external {
                args.push("--copy-external".into());
            }
            helper(&app, args, Some(op.id.clone())).await?;
        }
        op.phase = "validating".into();
        portable::write_json(&record(&app)?, &op)?;
        let _ = app.emit(
            "desktop-import-progress",
            json!({"stage":"launching","completed":0,"total":0}),
        );
        let target = op.target.clone();
        tauri::async_runtime::spawn_blocking(move || {
            let mut command = Command::new(target.join("TrailSnap.exe"));
            command.arg("--validate-only").stdin(Stdio::null());
            #[cfg(windows)]
            command.creation_flags(0x08000000);
            let output = command.output().map_err(|e| e.to_string())?;
            if !output.status.success() {
                return Err(format!(
                    "副本启动验证失败：{}。原图库保留，重启后可重新验证，不必再次复制。",
                    String::from_utf8_lossy(&output.stderr)
                ));
            }
            Ok(())
        })
        .await
        .map_err(|e| e.to_string())??;
        let root = app
            .state::<DataDirectory>()
            .instance_root
            .clone()
            .ok_or("未找到当前程序目录")?;
        if op.activate {
            crate::library_link::activate(&root, &op.target)?;
            portable::write_json(
                &root.join("maintenance/handoff.json"),
                &json!({"target":op.target}),
            )?;
        } else {
            portable::write_json(
                &root.join("maintenance/restart.json"),
                &json!({"restart":true}),
            )?;
        }
        op.phase = "completed".into();
        op.error = None;
        portable::write_json(&record(&app)?, &op)?;
        app.exit(0);
        Ok(json!({"target":op.target}))
    }
    .await;
    if let Err(error) = &result {
        op.phase = "failed".into();
        op.error = Some(error.clone());
        let _ = portable::write_json(&record(&app)?, &op);
    }
    result
}

#[tauri::command]
pub async fn desktop_resume_import(app: tauri::AppHandle) -> Result<Value, String> {
    let op: Operation = portable::read_json(&record(&app)?)?;
    if op.phase == "completed" {
        return Err("该副本已完成验证".into());
    }
    execute(app, op, true).await
}

#[tauri::command]
pub async fn desktop_cleanup_import(app: tauri::AppHandle) -> Result<(), String> {
    let _activity = crate::begin_activity(&app)?;
    let op: Operation = portable::read_json(&record(&app)?)?;
    if op.phase == "completed" {
        return Err("已完成的图库不能作为临时文件清理".into());
    }
    helper(
        &app,
        vec![
            "--cleanup-import".into(),
            op.target.to_string_lossy().into(),
            op.id,
        ],
        None,
    )
    .await?;
    // Published copies are deliberately retained. Only forget the recovery job.
    std::fs::remove_file(record(&app)?).map_err(|e| e.to_string())
}

#[tauri::command]
pub async fn desktop_open_previous_library(app: tauri::AppHandle) -> Result<(), String> {
    let root = app
        .state::<DataDirectory>()
        .instance_root
        .clone()
        .ok_or("未找到当前程序目录")?;
    let proof: Value = portable::read_json(&root.join("conversion.json"))?;
    let previous = proof["previousEntry"]
        .as_str()
        .ok_or("没有保留导入前的图库入口")?;
    let target = Path::new(previous);
    let config = portable::load_instance(target)?;
    if proof["previousInstanceId"] != config.instance_id || !target.join("TrailSnap.exe").is_file()
    {
        return Err("导入前的图库入口或身份已改变，请检查原目录".into());
    }
    portable::data_root(target, &config)?;
    crate::drain_desktop(&app).await?;
    portable::write_json(
        &root.join("maintenance/handoff.json"),
        &json!({"target": target, "original": true}),
    )?;
    app.exit(0);
    Ok(())
}

#[tauri::command]
pub async fn desktop_open_linked_library(app: tauri::AppHandle) -> Result<(), String> {
    let root = app
        .state::<DataDirectory>()
        .instance_root
        .clone()
        .ok_or("未找到当前程序目录")?;
    let target = crate::library_link::resolve(&root)?.ok_or("没有已导入的目标图库")?;
    crate::drain_desktop(&app).await?;
    portable::write_json(
        &root.join("maintenance/handoff.json"),
        &json!({"target": target}),
    )?;
    app.exit(0);
    Ok(())
}
