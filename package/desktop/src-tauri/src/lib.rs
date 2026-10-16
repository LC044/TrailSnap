mod ai_extension;
mod ai_gateway;
mod data_directory;
mod library_link;
mod import_flow;
mod extension_lifecycle;
mod llama_runtime;
mod portable;
mod update_manager;
mod update_transaction;

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
    status: Arc<Mutex<RuntimeStatus>>,
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
fn desktop_open_instance_directory(app: tauri::AppHandle) -> Result<(), String> {
    use tauri_plugin_opener::OpenerExt;
    let state = app.state::<DataDirectory>();
    let root = state.instance_root.clone().unwrap_or_else(|| state.root());
    app.opener()
        .open_path(root.to_string_lossy(), None::<&str>)
        .map_err(|e| e.to_string())
}

#[tauri::command]
async fn desktop_migration_preview(
    app: tauri::AppHandle,
    source_path: Option<String>,
) -> Result<Value, String> {
    let root = source_path
        .map(PathBuf::from)
        .unwrap_or_else(|| app.state::<DataDirectory>().root());
    let executable = server_executable(&app.path().resource_dir().map_err(|e| e.to_string())?);
    tauri::async_runtime::spawn_blocking(move || {
        let mut command = Command::new(executable);
        command
            .arg("--preview-portable")
            .arg(root)
            .env("PYTHONIOENCODING", "utf-8")
            .stdin(Stdio::null());
        #[cfg(windows)]
        command.creation_flags(0x08000000);
        let output = command.output().map_err(|e| e.to_string())?;
        if !output.status.success() {
            return Err(String::from_utf8_lossy(&output.stderr).into_owned());
        }
        serde_json::from_slice(&output.stdout).map_err(|e| e.to_string())
    })
    .await
    .map_err(|e| e.to_string())?
}

#[tauri::command]
async fn desktop_convert_portable(
    app: tauri::AppHandle,
    path: String,
    copy_external: bool,
    source_path: Option<String>,
    activate: Option<bool>,
) -> Result<Value, String> {
    let current = app.state::<DataDirectory>().root();
    let source = portable::clean_path(source_path.map(PathBuf::from).unwrap_or_else(|| current.clone()).canonicalize().map_err(|e| e.to_string())?);
    let _source_lock = if source != current { Some(portable::lock_directory(&source)?) } else { None };
    let target = data_directory::validate_target(&source, Path::new(&path))?;
    data_directory::validate_target(&current, &target)?;
    if let Some(root) = &app.state::<DataDirectory>().instance_root { data_directory::validate_target(root, &target)?; }
    let resource = app.path().resource_dir().map_err(|e| e.to_string())?;
    if !resource.join("portable-launcher.exe").is_file() { return Err("当前发行包缺少启动器，请安装完整新版程序".into()); }
    import_flow::start(app, source, target, copy_external, activate.unwrap_or(true)).await
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
    drain_desktop(&app).await?;
    app.state::<DataDirectory>().authorize_migration(&target)?;
    Ok(())
}

async fn drain_desktop(app: &tauri::AppHandle) -> Result<(), String> {
    if !desktop_runtime_status(app.state()).ready {
        return Err("本地服务尚未就绪，请稍后重试".into());
    }
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
    Ok(())
}

#[tauri::command]
async fn desktop_safe_exit(app: tauri::AppHandle) -> Result<(), String> {
    drain_desktop(&app).await?;
    app.exit(0);
    Ok(())
}

#[tauri::command]
async fn desktop_prepare_update(app: tauri::AppHandle) -> Result<(), String> {
    drain_desktop(&app).await?;
    let root = app.state::<DataDirectory>().root();
    let executable = server_executable(&app.path().resource_dir().map_err(|e| e.to_string())?);
    tauri::async_runtime::spawn_blocking(move || {
        let mut command = Command::new(executable);
        command
            .arg("--snapshot-data")
            .arg(&root)
            .arg(
                root.join("backups")
                    .join(format!("installer-{}", uuid::Uuid::new_v4())),
            )
            .stdin(Stdio::null());
        #[cfg(windows)]
        command.creation_flags(0x08000000);
        let output = command.output().map_err(|e| e.to_string())?;
        if !output.status.success() {
            return Err(String::from_utf8_lossy(&output.stderr).into_owned());
        }
        Ok(())
    })
    .await
    .map_err(|e| e.to_string())?
}

#[tauri::command]
fn desktop_restart(app: tauri::AppHandle) -> Result<(), String> {
    if let Some(root) = &app.state::<DataDirectory>().instance_root {
        portable::write_json(
            &root.join("maintenance/restart.json"),
            &json!({"restart":true}),
        )?;
        app.exit(0);
    } else {
        app.restart();
    }
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
    manager.reconcile().await?;
    Ok(extension_snapshot(&manager, &gateway))
}

#[tauri::command]
fn ai_extension_install(
    app: tauri::AppHandle,
    id: String,
    manager: tauri::State<'_, AIExtensionManager>,
) -> Result<Value, String> {
    let _activity = begin_activity(&app)?;
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
) -> Result<Value, String> {
    let _activity = begin_activity(&app)?;
    // A complete AI archive is hundreds of megabytes. Hashing and extracting
    // it in a synchronous Tauri command blocks the desktop UI long enough to
    // look like a crash, while the former lightweight extension did not.
    let manager = manager.inner().clone();
    let installed = manager.import_archive_safely(PathBuf::from(path)).await?;
    Ok(json!({ "canceled": false, "installed": installed }))
}

#[tauri::command]
async fn ai_extension_uninstall(
    app: tauri::AppHandle,
    id: String,
    manager: tauri::State<'_, AIExtensionManager>,
) -> Result<Value, String> {
    let _activity = begin_activity(&app)?;
    manager.uninstall_safely(&id).await?;
    Ok(json!({ "removed": true }))
}

#[tauri::command]
fn llama_runtime_status() -> Value {
    llama_runtime::status()
}

#[tauri::command]
async fn llama_runtime_install(
    app: tauri::AppHandle,
    manager: tauri::State<'_, AIExtensionManager>,
) -> Result<Value, String> {
    let _activity = begin_activity(&app)?;
    manager.install_llama_runtime().await
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
    if next.phase == "failed" && std::env::var("TS_DESKTOP_VERIFY").as_deref() == Ok("1") {
        if let Some(root) = &app.state::<DataDirectory>().instance_root {
            let _ = portable::write_json(
                &root.join("maintenance/validation-error.json"),
                &json!({"nonce":std::env::var("TS_UPDATE_NONCE").unwrap_or_default(), "error":next.message}),
            );
        }
    }
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
    let startup_error = app
        .state::<DataDirectory>()
        .root()
        .join("startup-error.json");
    let _ = fs::remove_file(&startup_error);
    let nonce =
        std::env::var("TS_UPDATE_NONCE").unwrap_or_else(|_| uuid::Uuid::new_v4().to_string());
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
        .env("LOG_DIR", &log_dir)
        .env("TS_DESKTOP_START_NONCE", &nonce)
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
        // On Windows a refused localhost connection can take about a second.
        // Bound connection attempts separately from the health response timeout.
        let client = reqwest::Client::builder()
            .no_proxy()
            .connect_timeout(Duration::from_millis(100))
            .build()
            .expect("desktop health client");
        let health_url = format!("{api_url}/health-check");
        let started = Instant::now();
        loop {
            let exited = {
                let state = app.state::<DesktopState>();
                let mut child = state.child.lock().expect("desktop child poisoned");
                child
                    .as_mut()
                    .and_then(|child| child.try_wait().ok().flatten())
            };
            if let Some(exit) = exited {
                let details: Option<Value> = portable::read_json(&startup_error).ok();
                let message = details.as_ref().and_then(|v|v["message"].as_str()).map(str::to_string)
                    .unwrap_or_else(||format!("本地服务已退出（{exit}）。请检查磁盘空间、写入权限和日志：{}。数据目录不会自动切换。", log_dir.display()));
                update_status(
                    &app,
                    RuntimeStatus {
                        api_url,
                        session_secret: String::new(),
                        phase: "failed".into(),
                        message: Some(message),
                        ready: false,
                    },
                );
                break;
            }
            if started.elapsed()
                > Duration::from_secs(if std::env::var_os("TS_INSTANCE_ROOT").is_some() {
                    30 * 60
                } else {
                    60
                })
            {
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
                        let identity = client
                            .get(format!("{api_url}/api/system/desktop/runtime"))
                            .timeout(Duration::from_secs(30))
                            .header("X-TrailSnap-Desktop-Secret", &session_secret)
                            .send()
                            .await;
                        let valid = if let Ok(response) = identity {
                            response.json::<Value>().await.ok().is_some_and(|v| {
                                v["code"] == 0
                                    && v["data"]["nonce"] == nonce
                                    && v["data"]["verified"] == true
                            })
                        } else {
                            false
                        };
                        if !valid {
                            tokio::time::sleep(Duration::from_millis(100)).await;
                            continue;
                        }
                        if std::env::var("TS_DESKTOP_VERIFY").as_deref() == Ok("1") {
                            if let Some(root) = &app.state::<DataDirectory>().instance_root {
                                let _ = portable::write_json(
                                    &root.join("maintenance/validated.json"),
                                    &json!({"nonce":nonce,"verified":true}),
                                );
                            }
                        }
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
            tokio::time::sleep(Duration::from_millis(50)).await;
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
    if std::env::var("TS_DESKTOP_TEST_READONLY").as_deref() == Ok("1") {
        std::env::set_var("TS_DESKTOP_VERIFY", "1");
    }
    // Derive the installation from the actual binary, never TS_INSTANCE_ROOT.
    if let Ok(executable) = std::env::current_exe() {
        if let Ok(root) = portable::instance_root_for_executable(&executable) {
            if root.join("TrailSnap.exe").is_file() {
                if std::env::var_os("TS_LAUNCHER_LEASE_TOKEN").is_none() {
                    let mut command = Command::new(root.join("TrailSnap.exe"));
                    #[cfg(windows)]
                    command.creation_flags(0x08000000);
                    let _ = command.spawn();
                    return;
                }
                std::env::set_var("TS_INSTANCE_ROOT", &root);
            } else {
                std::env::remove_var("TS_INSTANCE_ROOT");
                std::env::remove_var("TS_DESKTOP_PORTABLE");
            }
        }
    }
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_process::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .manage(DesktopState::default())
        .manage(update_manager::UpdateState::default())
        .invoke_handler(tauri::generate_handler![
            desktop_runtime_status,
            desktop_data_directory,
            desktop_set_data_directory,
            desktop_open_data_directory,
            desktop_open_instance_directory,
            desktop_migration_preview,
            import_flow::desktop_legacy_discovery,
            import_flow::desktop_dismiss_legacy,
            import_flow::desktop_import_space,
            import_flow::desktop_resume_import,
            import_flow::desktop_cleanup_import,
            import_flow::desktop_open_previous_library,
            import_flow::desktop_open_linked_library,
            desktop_convert_portable,
            desktop_prepare_migration,
            desktop_safe_exit,
            desktop_prepare_update,
            desktop_restart,
            update_manager::desktop_update_check,
            update_manager::desktop_update_download,
            update_manager::desktop_update_status,
            update_manager::desktop_update_apply,
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
            if let Some(root) = &app.state::<DataDirectory>().instance_root {
                let instance = portable::load_instance(root).map_err(std::io::Error::other)?;
                std::env::set_var("TS_DESKTOP_PORTABLE", "1");
                std::env::set_var("TS_DESKTOP_INSTANCE_ID", &instance.instance_id);
                std::env::set_var("TRAILSNAP_INSTANCE_NAME", &instance.display_name);
            }
            let directory_root = app.state::<DataDirectory>().root();
            #[cfg(windows)] {
                let runtime = app.path().resource_dir()?.join("webview-runtime");
                if runtime.join("msedgewebview2.exe").is_file() {
                    std::env::set_var("WEBVIEW2_BROWSER_EXECUTABLE_FOLDER", runtime);
                }
            }
            let mut window = tauri::WebviewWindowBuilder::from_config(app.handle(), &app.config().app.windows[0])?;
            #[cfg(windows)] { window = window.data_directory(portable::webview_directory(&directory_root).map_err(std::io::Error::other)?); }
            if std::env::var("TS_DESKTOP_VERIFY").as_deref() == Ok("1") || std::env::var("TS_DESKTOP_TEST_HEADLESS").as_deref() == Ok("1") { window = window.visible(false); }
            window.build()?;
            let catalog_path = app
                .path()
                .resource_dir()
                .map_err(|error| std::io::Error::other(format!("无法定位 AI 扩展清单：{error}")))?
                .join("ai-extensions.json");
            // Default is the running Server's v{version} Release catalog.
            let catalog_url = std::env::var("TS_AI_EXTENSION_CATALOG_URL").unwrap_or_default();
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
                    if std::env::var("TS_DESKTOP_VERIFY").as_deref() == Ok("1") {
                        return spawn_server(handle.clone(), 0);
                    }
                    let manager =
                        AIExtensionManager::initialize(&app_root, &catalog_path, catalog_url)?;
                    let gateway = AIGateway::new(manager.clone(), app_root, std::process::id());
                    manager.configure_lifecycle(extension_lifecycle::ExtensionLifecycle {
                        server_status: handle.state::<DesktopState>().status.clone(), gateway: gateway.clone(),
                    });
                    handle.manage(manager.clone());
                    handle.manage(gateway.clone());
                    let gateway_port = gateway.listen().await?;
                    let refresh_manager = manager.clone();
                    let refresh_handle = handle.clone();
                    tauri::async_runtime::spawn(async move {
                        if let Ok(_activity) = begin_activity(&refresh_handle) {
                            // Startup refresh can finish before the API sidecar is ready.
                            loop {
                                let status = desktop_runtime_status(refresh_handle.state());
                                if status.ready { break; }
                                if status.phase == "failed" { return; }
                                tokio::time::sleep(Duration::from_millis(200)).await;
                            }
                            let _ = refresh_manager.refresh_catalog().await;
                            if let Err(error) = refresh_manager.reconcile().await {
                                eprintln!("AI extension startup reconciliation failed: {error}");
                            }
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
        .build(tauri::generate_context!());
    let app = match app {
        Ok(app) => app,
        Err(error) => {
            eprintln!("行影集启动失败：{error}");
            #[cfg(windows)]
            unsafe {
                #[link(name = "user32")]
                unsafe extern "system" {
                    fn MessageBoxW(
                        h: *mut std::ffi::c_void,
                        text: *const u16,
                        title: *const u16,
                        flags: u32,
                    ) -> i32;
                }
                let text: Vec<u16> = format!("行影集启动失败：{error}")
                    .encode_utf16()
                    .chain(Some(0))
                    .collect();
                let title: Vec<u16> = "行影集".encode_utf16().chain(Some(0)).collect();
                MessageBoxW(std::ptr::null_mut(), text.as_ptr(), title.as_ptr(), 0x10);
            }
            return;
        }
    };

    app.run(|app, event| {
        if matches!(event, RunEvent::Exit | RunEvent::ExitRequested { .. }) {
            if let Some(gateway) = app.try_state::<AIGateway>() {
                gateway.stop_sidecar();
            }
            stop_server(app);
        }
    });
}
