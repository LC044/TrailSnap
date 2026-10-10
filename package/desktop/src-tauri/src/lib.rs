mod ai_extension;
mod ai_gateway;
mod data_directory;
mod llama_runtime;

use data_directory::{desktop_data_directory, desktop_set_data_directory, DataDirectory};

use ai_extension::AIExtensionManager;
use ai_gateway::AIGateway;
use serde::Serialize;
use serde_json::{json, Value};
use std::{
    fs::{self, OpenOptions},
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::{Arc, Mutex},
    time::{Duration, Instant},
};
use tauri::{Emitter, Manager, RunEvent};

#[derive(Clone, Default, Serialize)]
#[serde(rename_all = "camelCase")]
struct RuntimeStatus {
    api_url: String,
    session_secret: String,
    phase: String,
    message: Option<String>,
    ready: bool,
}

#[derive(Default)]
struct DesktopState {
    child: Mutex<Option<Child>>,
    status: Mutex<RuntimeStatus>,
    activity: Arc<Mutex<(bool, usize)>>,
}

struct ActivityGuard(Arc<Mutex<(bool, usize)>>);
impl Drop for ActivityGuard {
    fn drop(&mut self) {
        self.0.lock().expect("activity poisoned").1 -= 1;
    }
}
fn begin_activity(app: &tauri::AppHandle) -> Result<ActivityGuard, String> {
    let activity = app.state::<DesktopState>().activity.clone();
    {
        let mut state = activity.lock().expect("activity poisoned");
        if state.0 {
            return Err("正在准备数据迁移，请在重启完成后重试".into());
        }
        state.1 += 1;
    }
    Ok(ActivityGuard(activity))
}

#[tauri::command]
fn desktop_open_data_directory(app: tauri::AppHandle) -> Result<(), String> {
    use tauri_plugin_opener::OpenerExt;
    let root = app.state::<DataDirectory>().root();
    app.opener()
        .open_path(root.to_string_lossy(), None::<&str>)
        .map_err(|err| err.to_string())
}

#[tauri::command]
fn desktop_reveal_photo(path: String) -> Result<(), String> {
    let file = Path::new(&path);
    if !file.is_absolute() || !file.is_file() {
        return Err("照片原文件不存在或所在磁盘不可用".into());
    }
    tauri_plugin_opener::reveal_item_in_dir(file).map_err(|err| err.to_string())
}

#[tauri::command]
async fn desktop_prepare_migration(app: tauri::AppHandle) -> Result<(), String> {
    let target = app
        .state::<DataDirectory>()
        .pending()
        .ok_or("请先保存迁移设置")?;
    {
        let state = app.state::<DesktopState>();
        let mut activity = state.activity.lock().expect("activity poisoned");
        if activity.0 || activity.1 > 0 {
            return Err("正在安装、导入或准备迁移，请等待完成后重试".into());
        }
        activity.0 = true;
    }
    // Native mutations are sealed before checking asynchronous extension jobs.
    app.state::<AIGateway>().prepare_migration();
    loop {
        let busy = app.state::<AIExtensionManager>().has_active_installs();
        if !busy {
            break;
        }
        tokio::time::sleep(Duration::from_secs(1)).await;
    }
    let status = desktop_runtime_status(app.state());
    let response: Value = reqwest::Client::new()
        .post(format!(
            "{}/api/system/desktop/prepare-migration",
            status.api_url
        ))
        .header("X-TrailSnap-Desktop-Secret", status.session_secret)
        .send()
        .await
        .map_err(|err| format!("准备迁移失败，请重启后重试：{err}"))?
        .json()
        .await
        .map_err(|err| err.to_string())?;
    if response["code"] != 0 || response["data"]["ready"] != true {
        return Err(response["msg"]
            .as_str()
            .unwrap_or("准备迁移失败，请重启后重试")
            .into());
    }
    loop {
        let exited = {
            let state = app.state::<DesktopState>();
            let mut child = state.child.lock().expect("desktop child poisoned");
            match child
                .as_mut()
                .ok_or("本地服务未运行")?
                .try_wait()
                .map_err(|err| err.to_string())?
            {
                Some(exit) if exit.success() => {
                    *child = None;
                    true
                }
                Some(_) => return Err("本地服务异常退出，停止迁移".into()),
                None => false,
            }
        };
        if exited {
            break;
        }
        tokio::time::sleep(Duration::from_millis(200)).await;
    }
    app.state::<AIGateway>().drain_for_migration().await?;
    // Authorize only this destination after every writer has exited.
    app.state::<DataDirectory>().authorize_migration(&target)?;
    Ok(())
}

#[tauri::command]
fn desktop_runtime_status(state: tauri::State<'_, DesktopState>) -> RuntimeStatus {
    state
        .status
        .lock()
        .expect("desktop status poisoned")
        .clone()
}

fn extension_snapshot(manager: &AIExtensionManager, gateway: &AIGateway) -> Value {
    let mut snapshot = manager.list();
    snapshot["gateway"] = gateway.status();
    snapshot
}

#[tauri::command]
fn ai_extension_list(
    manager: tauri::State<'_, AIExtensionManager>,
    gateway: tauri::State<'_, AIGateway>,
) -> Value {
    extension_snapshot(&manager, &gateway)
}

#[tauri::command]
async fn ai_extension_refresh(
    app: tauri::AppHandle,
    manager: tauri::State<'_, AIExtensionManager>,
    gateway: tauri::State<'_, AIGateway>,
) -> Result<Value, String> {
    let _activity = begin_activity(&app)?;
    let _ = manager.refresh_catalog().await;
    Ok(extension_snapshot(&manager, &gateway))
}

#[tauri::command]
fn ai_extension_install(
    app: tauri::AppHandle,
    id: String,
    manager: tauri::State<'_, AIExtensionManager>,
    gateway: tauri::State<'_, AIGateway>,
) -> Result<Value, String> {
    let _activity = begin_activity(&app)?;
    gateway.stop_sidecar();
    manager.start_install(&id)
}

#[tauri::command]
fn ai_extension_pause(
    app: tauri::AppHandle,
    id: String,
    manager: tauri::State<'_, AIExtensionManager>,
) -> Result<Value, String> {
    let _activity = begin_activity(&app)?;
    manager.pause(&id)
}

#[tauri::command]
fn ai_extension_retry(
    app: tauri::AppHandle,
    id: String,
    manager: tauri::State<'_, AIExtensionManager>,
) -> Result<Value, String> {
    let _activity = begin_activity(&app)?;
    manager.retry(&id)
}

#[tauri::command]
async fn ai_extension_import(
    app: tauri::AppHandle,
    path: String,
    manager: tauri::State<'_, AIExtensionManager>,
    gateway: tauri::State<'_, AIGateway>,
) -> Result<Value, String> {
    let _activity = begin_activity(&app)?;
    gateway.stop_sidecar();
    // A complete AI archive is hundreds of megabytes. Hashing and extracting
    // it in a synchronous Tauri command blocks the desktop UI long enough to
    // look like a crash, while the former lightweight extension did not.
    let manager = manager.inner().clone();
    let installed =
        tauri::async_runtime::spawn_blocking(move || manager.import_archive(Path::new(&path)))
            .await
            .map_err(|error| format!("AI 扩展导入任务异常：{error}"))??;
    Ok(json!({ "canceled": false, "installed": installed }))
}

#[tauri::command]
fn ai_extension_uninstall(
    app: tauri::AppHandle,
    id: String,
    manager: tauri::State<'_, AIExtensionManager>,
    gateway: tauri::State<'_, AIGateway>,
) -> Result<Value, String> {
    let _activity = begin_activity(&app)?;
    gateway.stop_sidecar();
    manager.uninstall(&id)?;
    Ok(json!({ "removed": true }))
}

#[tauri::command]
fn llama_runtime_status() -> Value {
    llama_runtime::status()
}

#[tauri::command]
async fn llama_runtime_install(
    app: tauri::AppHandle,
    gateway: tauri::State<'_, AIGateway>,
) -> Result<Value, String> {
    let _activity = begin_activity(&app)?;
    let result = llama_runtime::install().await?;
    // A running Sidecar inherited the pre-install PATH. Restart it lazily so
    // the next AI request receives the newly detected LLAMA_SERVER_PATH.
    gateway.stop_sidecar();
    Ok(result)
}

fn server_executable(resource_dir: &Path) -> PathBuf {
    if let Some(value) = std::env::var_os("TS_DESKTOP_SERVER_BINARY") {
        return PathBuf::from(value);
    }
    let name = if cfg!(windows) {
        "trailsnap-server.exe"
    } else {
        "trailsnap-server"
    };
    resource_dir.join("server").join(name)
}

fn prepare_data_dir(_app: &tauri::AppHandle) -> Result<PathBuf, String> {
    let root = _app.state::<DataDirectory>().root();
    let data_dir = root.join("data");
    fs::create_dir_all(root.join("logs"))
        .and_then(|_| fs::create_dir_all(&data_dir))
        .map_err(|error| format!("无法创建桌面数据目录：{error}"))?;
    let env_file = data_dir.join(".env");
    if !env_file.exists() {
        fs::write(
            &env_file,
            concat!(
                "# TrailSnap Desktop uses SQLite in this data directory.\n",
                "TS_DESKTOP=1\n",
            ),
        )
        .map_err(|error| format!("无法创建桌面配置：{error}"))?;
    }
    Ok(data_dir)
}

fn log_file(path: PathBuf) -> Result<std::fs::File, String> {
    OpenOptions::new()
        .create(true)
        .append(true)
        .open(path)
        .map_err(|error| format!("无法打开日志文件：{error}"))
}

fn update_status(app: &tauri::AppHandle, next: RuntimeStatus) {
    let state = app.state::<DesktopState>();
    *state.status.lock().expect("desktop status poisoned") = next.clone();
    let _ = app.emit("desktop-runtime-status", next);
}

fn spawn_server(app: tauri::AppHandle, ai_gateway_port: u16) -> Result<(), String> {
    let port = app.state::<DataDirectory>().server_port()?;
    let api_url = format!("http://127.0.0.1:{port}");
    update_status(
        &app,
        RuntimeStatus {
            api_url: api_url.clone(),
            session_secret: String::new(),
            phase: "starting".into(),
            message: Some("正在启动本地服务".into()),
            ready: false,
        },
    );

    let resource_dir = app
        .path()
        .resource_dir()
        .map_err(|error| format!("无法定位安装资源：{error}"))?;
    let executable = server_executable(&resource_dir);
    if !executable.is_file() {
        return Err(format!("找不到后端程序：{}", executable.display()));
    }
    let data_dir = prepare_data_dir(&app)?;
    let log_dir = data_dir
        .parent()
        .expect("data directory has parent")
        .join("logs");
    let stdout = log_file(log_dir.join("server.log"))?;
    let stderr = log_file(log_dir.join("server.err.log"))?;
    let database_url = format!(
        "sqlite:///{}",
        data_dir
            .join("trailsnap.sqlite")
            .to_string_lossy()
            .replace('\\', "/")
    );
    let railway_database_url = format!(
        "sqlite:///{}",
        data_dir
            .join("railway.sqlite")
            .to_string_lossy()
            .replace('\\', "/")
    );

    let mut command = Command::new(&executable);
    command
        .args([
            "--port",
            &port.to_string(),
            "--parent-pid",
            &std::process::id().to_string(),
        ])
        .current_dir(&data_dir)
        .env("TS_DATA_DIR", &data_dir)
        .env("TS_DESKTOP", "1")
        .env("TS_DB_URL", database_url)
        .env("RAILWAY_DB_URL", railway_database_url)
        .env(
            "TS_DESKTOP_AI_GATEWAY",
            format!("http://127.0.0.1:{ai_gateway_port}"),
        )
        .env(
            "TS_AI_API_URL",
            format!("http://127.0.0.1:{ai_gateway_port}"),
        )
        .env("AI_API_URL", format!("http://127.0.0.1:{ai_gateway_port}"))
        .stdin(Stdio::null())
        .stdout(Stdio::from(stdout))
        .stderr(Stdio::from(stderr));
    #[cfg(windows)]
    command.creation_flags(0x08000000); // CREATE_NO_WINDOW
    let child = command
        .spawn()
        .map_err(|error| format!("启动本地服务失败：{error}"))?;
    *app.state::<DesktopState>()
        .child
        .lock()
        .expect("desktop child poisoned") = Some(child);

    tauri::async_runtime::spawn(async move {
        let client = reqwest::Client::new();
        let health_url = format!("{api_url}/health-check");
        let started = Instant::now();
        loop {
            if started.elapsed() > Duration::from_secs(60) {
                update_status(
                    &app,
                    RuntimeStatus {
                        api_url,
                        session_secret: String::new(),
                        phase: "failed".into(),
                        message: Some("等待本地服务启动超时，请检查日志".into()),
                        ready: false,
                    },
                );
                break;
            }
            if let Ok(response) = client
                .get(&health_url)
                .timeout(Duration::from_millis(1200))
                .send()
                .await
            {
                if response.status().is_success() {
                    let secret_path = data_dir.join("desktop_session.secret");
                    let session_secret = fs::read_to_string(&secret_path).unwrap_or_default();
                    if !session_secret.is_empty() {
                        let _ = fs::remove_file(secret_path);
                        update_status(
                            &app,
                            RuntimeStatus {
                                api_url,
                                session_secret,
                                phase: "ready".into(),
                                message: None,
                                ready: true,
                            },
                        );
                        break;
                    }
                }
            }
            tokio::time::sleep(Duration::from_millis(300)).await;
        }
    });
    Ok(())
}

fn stop_server(app: &tauri::AppHandle) {
    let state = app.state::<DesktopState>();
    let Some(mut child) = state.child.lock().expect("desktop child poisoned").take() else {
        return;
    };
    #[cfg(windows)]
    {
        let _ = Command::new("taskkill")
            .args(["/pid", &child.id().to_string(), "/t", "/f"])
            .creation_flags(0x08000000)
            .status();
    }
    #[cfg(not(windows))]
    {
        let _ = child.kill();
    }
    let _ = child.wait();
}

#[cfg(windows)]
use std::os::windows::process::CommandExt;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_process::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .manage(DesktopState::default())
        .invoke_handler(tauri::generate_handler![
            desktop_runtime_status,
            desktop_data_directory,
            desktop_set_data_directory,
            desktop_open_data_directory,
            desktop_prepare_migration,
            desktop_reveal_photo,
            ai_extension_list,
            ai_extension_refresh,
            ai_extension_install,
            ai_extension_pause,
            ai_extension_retry,
            ai_extension_import,
            ai_extension_uninstall,
            llama_runtime_status,
            llama_runtime_install,
        ])
        .setup(|app| {
            let handle = app.handle().clone();
            let directory = DataDirectory::load(&handle).map_err(std::io::Error::other)?;
            app.manage(directory);
            let catalog_path = app
                .path()
                .resource_dir()
                .map_err(|error| std::io::Error::other(format!("无法定位 AI 扩展清单：{error}")))?
                .join("ai-extensions.json");
            let catalog_url = std::env::var("TS_AI_EXTENSION_CATALOG_URL").unwrap_or_else(|_| {
                format!(
                    "https://github.com/LC044/TrailSnap/releases/download/v{}/ai-extensions.json",
                    env!("CARGO_PKG_VERSION")
                )
            });
            tauri::async_runtime::spawn(async move {
                let result = async {
                    if let Some(target) = handle.state::<DataDirectory>().pending() {
                        let authorized = handle.state::<DataDirectory>().consume_migration_authorization()?;
                        if !authorized {
                            handle.state::<DataDirectory>().finish_migration(Err("上次退出未完成安全准备。请重新保存目录，并使用“安全重启并迁移”等待上传和任务结束。".into()))?;
                        } else {
                            update_status(
                                &handle,
                                RuntimeStatus {
                                    phase: "migrating".into(),
                                    message: Some("正在迁移数据目录，请勿关闭行影集".into()),
                                    ..Default::default()
                                },
                            );
                            let source = handle.state::<DataDirectory>().root();
                            let resource_dir = handle
                                .path()
                                .resource_dir()
                                .map_err(|err| err.to_string())?;
                            let executable = server_executable(&resource_dir);
                            let migrated = tauri::async_runtime::spawn_blocking(move || {
                                let mut command = Command::new(executable);
                                command
                                    .arg("--migrate-data")
                                    .arg(source)
                                    .arg(target)
                                    .arg("--parent-pid")
                                    .arg(std::process::id().to_string())
                                    .env("PYTHONIOENCODING", "utf-8")
                                    .stdin(Stdio::null());
                                #[cfg(windows)]
                                command.creation_flags(0x08000000);
                                let output = command
                                    .output()
                                    .map_err(|err| format!("无法启动数据迁移：{err}"))?;
                                if output.status.success() {
                                    Ok(())
                                } else {
                                    Err(String::from_utf8_lossy(&output.stderr).trim().to_string())
                                }
                            })
                            .await
                            .map_err(|err| err.to_string())?;
                            handle.state::<DataDirectory>().finish_migration(migrated)?;
                        }
                    }
                    let data_dir = prepare_data_dir(&handle)?;
                    let app_root = data_dir
                        .parent()
                        .expect("data directory has parent")
                        .to_path_buf();
                    std::env::set_var("TS_DESKTOP_ROOT", &app_root);
                    let manager =
                        AIExtensionManager::initialize(&app_root, &catalog_path, catalog_url)?;
                    let gateway = AIGateway::new(manager.clone(), app_root, std::process::id());
                    handle.manage(manager.clone());
                    handle.manage(gateway.clone());
                    let gateway_port = gateway.listen().await?;
                    let refresh_manager = manager.clone();
                    let refresh_handle = handle.clone();
                    tauri::async_runtime::spawn(async move {
                        if let Ok(_activity) = begin_activity(&refresh_handle) {
                            let _ = refresh_manager.refresh_catalog().await;
                        }
                    });
                    spawn_server(handle.clone(), gateway_port)
                }
                .await;
                if let Err(message) = result {
                    update_status(
                        &handle,
                        RuntimeStatus {
                            api_url: String::new(),
                            session_secret: String::new(),
                            phase: "failed".into(),
                            message: Some(message),
                            ready: false,
                        },
                    );
                }
            });
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building TrailSnap desktop application");

    app.run(|app, event| {
        if matches!(event, RunEvent::Exit | RunEvent::ExitRequested { .. }) {
            if let Some(gateway) = app.try_state::<AIGateway>() {
                gateway.stop_sidecar();
            }
            stop_server(app);
        }
    });
}
