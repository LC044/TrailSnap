use serde::Serialize;
use std::{
    fs::{self, OpenOptions},
    net::TcpListener,
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::Mutex,
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
}

#[tauri::command]
fn desktop_runtime_status(state: tauri::State<'_, DesktopState>) -> RuntimeStatus {
    state
        .status
        .lock()
        .expect("desktop status poisoned")
        .clone()
}

fn reserve_port() -> Result<u16, String> {
    let listener = TcpListener::bind(("127.0.0.1", 0))
        .map_err(|error| format!("无法分配本地端口：{error}"))?;
    listener
        .local_addr()
        .map(|address| address.port())
        .map_err(|error| format!("无法读取本地端口：{error}"))
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

fn prepare_data_dir(app: &tauri::AppHandle) -> Result<PathBuf, String> {
    #[cfg(windows)]
    let root = std::env::var_os("LOCALAPPDATA")
        .map(PathBuf::from)
        .map(|path| path.join("TrailSnap"))
        .ok_or_else(|| "无法读取 LOCALAPPDATA".to_string())?;
    #[cfg(not(windows))]
    let root = app
        .path()
        .app_local_data_dir()
        .map_err(|error| format!("无法确定数据目录：{error}"))?;
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

fn spawn_server(app: tauri::AppHandle) -> Result<(), String> {
    let port = reserve_port()?;
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
        data_dir.join("trailsnap.sqlite").to_string_lossy().replace('\\', "/")
    );
    let railway_database_url = format!(
        "sqlite:///{}",
        data_dir.join("railway.sqlite").to_string_lossy().replace('\\', "/")
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
        .manage(DesktopState::default())
        .invoke_handler(tauri::generate_handler![desktop_runtime_status])
        .setup(|app| {
            let handle = app.handle().clone();
            std::thread::spawn(move || {
                if let Err(message) = spawn_server(handle.clone()) {
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
            stop_server(app);
        }
    });
}
