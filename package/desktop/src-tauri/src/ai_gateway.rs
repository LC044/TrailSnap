use crate::ai_extension::AIExtensionManager;
use crate::llama_runtime;
use axum::{
    body::{to_bytes, Body},
    extract::State,
    http::{HeaderMap, Method, StatusCode, Uri},
    response::Response,
    routing::any,
    Router,
};
use serde_json::{json, Value};
use std::{
    fs::{self, OpenOptions},
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::{Arc, Mutex},
    time::{Duration, SystemTime, UNIX_EPOCH},
};
use tokio::sync::Mutex as AsyncMutex;

struct SidecarProcess {
    child: Child,
    port: u16,
    extension_id: String,
}

#[derive(Clone)]
pub struct AIGateway {
    manager: AIExtensionManager,
    app_root: PathBuf,
    parent_pid: u32,
    sidecar: Arc<Mutex<Option<SidecarProcess>>>,
    start_lock: Arc<AsyncMutex<()>>,
    gateway_port: Arc<Mutex<Option<u16>>>,
    last_request_at: Arc<Mutex<Option<u64>>>,
}

impl AIGateway {
    pub fn new(manager: AIExtensionManager, app_root: PathBuf, parent_pid: u32) -> Self {
        Self {
            manager,
            app_root,
            parent_pid,
            sidecar: Arc::new(Mutex::new(None)),
            start_lock: Arc::new(AsyncMutex::new(())),
            gateway_port: Arc::new(Mutex::new(None)),
            last_request_at: Arc::new(Mutex::new(None)),
        }
    }

    pub async fn listen(&self) -> Result<u16, String> {
        let listener = tokio::net::TcpListener::bind(("127.0.0.1", 0))
            .await
            .map_err(|error| format!("无法启动 AI Gateway：{error}"))?;
        let port = listener
            .local_addr()
            .map_err(|error| format!("无法读取 AI Gateway 端口：{error}"))?
            .port();
        *self.gateway_port.lock().expect("AI gateway port poisoned") = Some(port);
        let router = Router::new().fallback(any(proxy)).with_state(self.clone());
        tauri::async_runtime::spawn(async move {
            if let Err(error) = axum::serve(listener, router).await {
                eprintln!("AI Gateway stopped: {error}");
            }
        });
        let idle_gateway = self.clone();
        tauri::async_runtime::spawn(async move {
            let mut timer = tokio::time::interval(Duration::from_secs(60));
            loop {
                timer.tick().await;
                if idle_gateway.is_idle(Duration::from_secs(10 * 60)) {
                    idle_gateway.stop_sidecar();
                }
            }
        });
        Ok(port)
    }

    pub fn status(&self) -> Value {
        let mut sidecar = self.sidecar.lock().expect("AI sidecar poisoned");
        let running = sidecar
            .as_mut()
            .map(|item| item.child.try_wait().ok().flatten().is_none())
            .unwrap_or(false);
        if !running {
            *sidecar = None;
        }
        json!({
            "port": *self.gateway_port.lock().expect("AI gateway port poisoned"),
            "running": running,
            "pid": sidecar.as_ref().map(|item| item.child.id()),
            "extension": sidecar.as_ref().map(|item| item.extension_id.clone()),
            "lastRequestAt": *self.last_request_at.lock().expect("AI last request poisoned"),
        })
    }

    pub fn stop_sidecar(&self) {
        let Some(mut sidecar) = self.sidecar.lock().expect("AI sidecar poisoned").take() else {
            return;
        };
        terminate_process_tree(&mut sidecar.child);
    }

    async fn ensure_sidecar(&self) -> Result<u16, String> {
        if let Some(port) = self.running_port() {
            return Ok(port);
        }
        let _guard = self.start_lock.lock().await;
        if let Some(port) = self.running_port() {
            return Ok(port);
        }
        let (extension, directory) = self
            .manager
            .installed_for_ai()
            .ok_or_else(|| "尚未安装 AI 扩展包".to_string())?;
        let executable = safe_child_path(&directory, &extension.entrypoint)?;
        if !executable.is_file() {
            return Err("AI 扩展包入口不存在，请重新安装".into());
        }
        let port = reserve_port()?;
        let log_dir = self.app_root.join("logs");
        let model_dir = match extension.model_path.as_deref() {
            Some(path) => safe_child_path(&directory, path)?,
            None => self.app_root.join("models"),
        };
        fs::create_dir_all(&log_dir).map_err(|error| error.to_string())?;
        fs::create_dir_all(&model_dir).map_err(|error| error.to_string())?;
        let stdout = open_log(log_dir.join("ai.log"))?;
        let stderr = open_log(log_dir.join("ai.err.log"))?;
        let mut command = Command::new(&executable);
        command
            .args([
                "--port",
                &port.to_string(),
                "--parent-pid",
                &self.parent_pid.to_string(),
            ])
            .current_dir(&self.app_root)
            .env("MODEL_PATH", &model_dir)
            .env("AI_CONFIG_PATH", self.app_root.join("ai-config.json"))
            .env("TS_AI_LOG_DIR", &log_dir)
            .stdin(Stdio::null())
            .stdout(Stdio::from(stdout))
            .stderr(Stdio::from(stderr));
        if let Some(llama_server) = llama_runtime::find_llama_server() {
            command.env("LLAMA_SERVER_PATH", llama_server);
        }
        #[cfg(windows)]
        command.creation_flags(0x08000000);
        let mut child = command
            .spawn()
            .map_err(|error| format!("启动 AI Sidecar 失败：{error}"))?;
        let health_url = format!("http://127.0.0.1:{port}/health-check");
        let client = reqwest::Client::new();
        let started = std::time::Instant::now();
        loop {
            if let Some(status) = child.try_wait().map_err(|error| error.to_string())? {
                return Err(format!("AI Sidecar 提前退出：{status}"));
            }
            if started.elapsed() > Duration::from_secs(90) {
                terminate_process_tree(&mut child);
                return Err("等待 AI Sidecar 启动超时，请检查 ai.err.log".into());
            }
            if let Ok(response) = client
                .get(&health_url)
                .timeout(Duration::from_millis(1500))
                .send()
                .await
            {
                if response.status().is_success() {
                    break;
                }
            }
            tokio::time::sleep(Duration::from_millis(400)).await;
        }
        *self.sidecar.lock().expect("AI sidecar poisoned") = Some(SidecarProcess {
            child,
            port,
            extension_id: extension.id,
        });
        *self
            .last_request_at
            .lock()
            .expect("AI last request poisoned") = Some(now_seconds());
        Ok(port)
    }

    fn running_port(&self) -> Option<u16> {
        let mut sidecar = self.sidecar.lock().expect("AI sidecar poisoned");
        let running = sidecar
            .as_mut()
            .map(|item| item.child.try_wait().ok().flatten().is_none())
            .unwrap_or(false);
        if running {
            sidecar.as_ref().map(|item| item.port)
        } else {
            *sidecar = None;
            None
        }
    }

    fn is_idle(&self, timeout: Duration) -> bool {
        let last = *self
            .last_request_at
            .lock()
            .expect("AI last request poisoned");
        self.running_port().is_some()
            && last
                .map(|value| now_seconds().saturating_sub(value) >= timeout.as_secs())
                .unwrap_or(false)
    }
}

async fn proxy(
    State(gateway): State<AIGateway>,
    method: Method,
    uri: Uri,
    headers: HeaderMap,
    body: Body,
) -> Response {
    match proxy_inner(&gateway, method, uri, headers, body).await {
        Ok(response) => response,
        Err(error) => json_error(StatusCode::SERVICE_UNAVAILABLE, &error),
    }
}

async fn proxy_inner(
    gateway: &AIGateway,
    method: Method,
    uri: Uri,
    headers: HeaderMap,
    body: Body,
) -> Result<Response, String> {
    let port = gateway.ensure_sidecar().await?;
    *gateway
        .last_request_at
        .lock()
        .expect("AI last request poisoned") = Some(now_seconds());
    let url = format!(
        "http://127.0.0.1:{port}{}",
        uri.path_and_query()
            .map(|value| value.as_str())
            .unwrap_or("/")
    );
    let bytes = to_bytes(body, 128 * 1024 * 1024)
        .await
        .map_err(|error| format!("读取 AI 请求失败：{error}"))?;
    let client = reqwest::Client::new();
    let mut request = client.request(
        reqwest::Method::from_bytes(method.as_str().as_bytes())
            .map_err(|error| error.to_string())?,
        url,
    );
    for (name, value) in headers.iter() {
        if !matches!(name.as_str(), "host" | "content-length" | "connection") {
            request = request.header(name, value);
        }
    }
    let upstream = request
        .body(bytes)
        .send()
        .await
        .map_err(|error| format!("AI Sidecar 请求失败：{error}"))?;
    let status = upstream.status();
    let upstream_headers = upstream.headers().clone();
    let payload = upstream
        .bytes()
        .await
        .map_err(|error| format!("读取 AI Sidecar 响应失败：{error}"))?;
    let mut response = Response::builder().status(status.as_u16());
    for (name, value) in upstream_headers.iter() {
        if !matches!(name.as_str(), "content-length" | "connection") {
            response = response.header(name, value);
        }
    }
    response
        .body(Body::from(payload))
        .map_err(|error| error.to_string())
}

fn json_error(status: StatusCode, message: &str) -> Response {
    Response::builder()
        .status(status)
        .header("content-type", "application/json; charset=utf-8")
        .body(Body::from(
            json!({ "detail": message, "extensionRequired": true }).to_string(),
        ))
        .expect("valid AI gateway error response")
}

fn open_log(path: PathBuf) -> Result<std::fs::File, String> {
    OpenOptions::new()
        .create(true)
        .append(true)
        .open(path)
        .map_err(|error| format!("无法打开 AI 日志：{error}"))
}

fn safe_child_path(root: &Path, relative: &str) -> Result<PathBuf, String> {
    let candidate = root.join(relative);
    let root = root.canonicalize().unwrap_or_else(|_| root.to_path_buf());
    let parent = candidate
        .parent()
        .and_then(|value| value.canonicalize().ok())
        .unwrap_or_else(|| candidate.parent().unwrap_or(root.as_path()).to_path_buf());
    if !parent.starts_with(&root) {
        return Err("AI 扩展包路径越界".into());
    }
    Ok(candidate)
}

fn reserve_port() -> Result<u16, String> {
    std::net::TcpListener::bind(("127.0.0.1", 0))
        .and_then(|listener| listener.local_addr())
        .map(|address| address.port())
        .map_err(|error| format!("无法分配 AI Sidecar 端口：{error}"))
}

fn terminate_process_tree(child: &mut Child) {
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

fn now_seconds() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs()
}

#[cfg(windows)]
use std::os::windows::process::CommandExt;

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    #[ignore = "requires TS_TEST_AI_EXTENSION_ARCHIVE"]
    async fn real_extension_starts_through_gateway() {
        let archive = std::env::var("TS_TEST_AI_EXTENSION_ARCHIVE").unwrap();
        let root = std::env::temp_dir().join(format!("trailsnap-ai-gateway-{}", now_seconds()));
        fs::create_dir_all(&root).unwrap();
        let catalog = Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("resources")
            .join("ai-extensions.json");
        let manager = AIExtensionManager::initialize(&root, &catalog, String::new()).unwrap();
        manager.import_archive(Path::new(&archive)).unwrap();
        let gateway = AIGateway::new(manager, root.clone(), std::process::id());
        let port = gateway.listen().await.unwrap();
        let response = reqwest::get(format!("http://127.0.0.1:{port}/health-check"))
            .await
            .unwrap();
        assert!(response.status().is_success());
        let payload = response.json::<Value>().await.unwrap();
        assert_eq!(payload["status"], "ok");
        assert!(gateway.status()["running"].as_bool().unwrap());
        gateway.stop_sidecar();
        fs::remove_dir_all(root).unwrap();
    }
}
