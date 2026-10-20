use crate::ai_extension::AIExtensionManager;
use crate::llama_runtime;
use axum::{
    body::{to_bytes, Body},
    extract::State,
    http::{HeaderMap, Method, StatusCode, Uri},
    response::Response,
    routing::{any, get},
    Router,
};
use futures_util::StreamExt;
use serde_json::{json, Value};
use std::{
    fs::{self, OpenOptions},
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc, Mutex,
    },
    time::{Duration, SystemTime, UNIX_EPOCH},
};
use tokio::sync::Mutex as AsyncMutex;

#[derive(Debug)]
struct RequestGuard(Arc<Mutex<(bool, usize)>>);
impl Drop for RequestGuard {
    fn drop(&mut self) {
        self.0.lock().expect("AI admission poisoned").1 -= 1;
    }
}

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
    migrating: Arc<AtomicBool>,
    admission: Arc<Mutex<(bool, usize)>>,
}

impl AIGateway {
    pub fn new(manager: AIExtensionManager, app_root: PathBuf, parent_pid: u32) -> Self {
        Self {
            manager: manager.runtime_view(),
            app_root,
            parent_pid,
            sidecar: Arc::new(Mutex::new(None)),
            start_lock: Arc::new(AsyncMutex::new(())),
            gateway_port: Arc::new(Mutex::new(None)),
            last_request_at: Arc::new(Mutex::new(None)),
            migrating: Arc::new(AtomicBool::new(false)),
            admission: Arc::new(Mutex::new((false, 0))),
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
        let router = Router::new()
            .route("/desktop/ai-extension-status", get(extension_status))
            .fallback(any(proxy))
            .with_state(self.clone());
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
                if !idle_gateway.migrating.load(Ordering::SeqCst)
                    && *idle_gateway
                        .admission
                        .lock()
                        .expect("AI admission poisoned")
                        == (false, 0)
                    && idle_gateway.is_idle(Duration::from_secs(10 * 60))
                {
                    if idle_gateway.wait_for_model_downloads().await.is_ok() {
                        let admission = idle_gateway
                            .admission
                            .lock()
                            .expect("AI admission poisoned");
                        if *admission == (false, 0)
                            && idle_gateway.is_idle(Duration::from_secs(10 * 60))
                        {
                            idle_gateway.stop_sidecar();
                        }
                    }
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

    fn begin_request(&self) -> Result<RequestGuard, String> {
        let mut admission = self.admission.lock().expect("AI admission poisoned");
        if admission.0 || self.manager.runtime_state() == "waiting_update" {
            return Err("ai_extension_wait=maintenance 等待 AI 扩展更新".into());
        }
        if self.manager.installed_for_ai().is_none() {
            return Err("ai_extension_wait=missing 等待安装 AI 扩展".into());
        }
        admission.1 += 1;
        Ok(RequestGuard(self.admission.clone()))
    }

    pub fn finish_extension_maintenance(&self, blocked: bool) {
        self.admission.lock().expect("AI admission poisoned").0 = blocked;
    }

    pub async fn drain_for_extension(&self) -> Result<(), String> {
        self.finish_extension_maintenance(true);
        loop {
            if self.admission.lock().expect("AI admission poisoned").1 == 0 {
                break;
            }
            tokio::time::sleep(Duration::from_millis(100)).await;
        }
        let _start_guard = self.start_lock.lock().await;
        self.wait_for_model_downloads().await?;
        self.stop_sidecar();
        Ok(())
    }

    async fn wait_for_model_downloads(&self) -> Result<(), String> {
        let client = reqwest::Client::builder()
            .no_proxy()
            .build()
            .map_err(|e| e.to_string())?;
        while let Some(port) = self.running_port() {
            let response: Value = client
                .get(format!("http://127.0.0.1:{port}/ai/models"))
                .timeout(Duration::from_secs(5))
                .send()
                .await
                .map_err(|e| format!("无法确认 AI 模型下载状态：{e}"))?
                .error_for_status()
                .map_err(|e| e.to_string())?
                .json()
                .await
                .map_err(|e| e.to_string())?;
            let models = response["models"]
                .as_array()
                .ok_or("无法确认 AI 模型状态，已停止扩展维护")?;
            if !models.iter().any(|m| m["status"] == "downloading") {
                break;
            }
            tokio::time::sleep(Duration::from_secs(1)).await;
        }
        Ok(())
    }

    pub async fn drain_for_migration(&self) -> Result<(), String> {
        self.migrating.store(true, Ordering::SeqCst);
        let client = reqwest::Client::new();
        while let Some(port) = self.running_port() {
            let response: Value = client
                .get(format!("http://127.0.0.1:{port}/ai/models"))
                .timeout(Duration::from_secs(5))
                .send()
                .await
                .map_err(|err| format!("无法确认 AI 下载状态，停止迁移：{err}"))?
                .json()
                .await
                .map_err(|err| err.to_string())?;
            let models = response["models"]
                .as_array()
                .ok_or("无法确认 AI 模型状态，停止迁移；请更新 AI 扩展后重试")?;
            if models.iter().any(|model| model["status"] == "downloading") {
                tokio::time::sleep(Duration::from_secs(1)).await;
                continue;
            }
            self.stop_sidecar();
            break;
        }
        Ok(())
    }

    pub fn prepare_migration(&self) {
        self.migrating.store(true, Ordering::SeqCst);
    }

    async fn ensure_sidecar(&self) -> Result<u16, String> {
        if let Some(port) = self.running_port() {
            return Ok(port);
        }
        let _guard = self.start_lock.lock().await;
        if let Some(port) = self.running_port() {
            return Ok(port);
        }
        if self.admission.lock().expect("AI admission poisoned").0
            || self.manager.runtime_state() == "waiting_update"
        {
            return Err("ai_extension_wait=maintenance 等待 AI 扩展更新".into());
        }
        let (extension, directory) = self
            .manager
            .installed_for_ai()
            .ok_or_else(|| "尚未安装 AI 扩展包".to_string())?;
        let executable = safe_child_path(&directory, &extension.entrypoint)?;
        if !executable.is_file() {
            return Err("AI 扩展包入口不存在，请重新安装".into());
        }
        let log_dir = self.app_root.join("logs");
        let model_dir = match extension.model_path.as_deref() {
            Some(path) => safe_child_path(&directory, path)?,
            None => self.app_root.join("models"),
        };
        fs::create_dir_all(&log_dir).map_err(|error| error.to_string())?;
        fs::create_dir_all(&model_dir).map_err(|error| error.to_string())?;
        let client = reqwest::Client::builder()
            .no_proxy()
            .build()
            .map_err(|error| error.to_string())?;
        let mut last_exit = None;
        for attempt in 1..=2 {
            let port = reserve_port()?;
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
            let started = std::time::Instant::now();
            loop {
                if let Some(status) = child.try_wait().map_err(|error| error.to_string())? {
                    last_exit = Some(status);
                    break;
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
                        *self.sidecar.lock().expect("AI sidecar poisoned") = Some(SidecarProcess {
                            child,
                            port,
                            extension_id: extension.id.clone(),
                        });
                        *self
                            .last_request_at
                            .lock()
                            .expect("AI last request poisoned") = Some(now_seconds());
                        return Ok(port);
                    }
                }
                tokio::time::sleep(Duration::from_millis(400)).await;
            }
            if attempt < 2 {
                tokio::time::sleep(Duration::from_millis(250)).await;
            }
        }
        Err(format!(
            "AI Sidecar 提前退出（已重试）：{}，请检查 ai.err.log",
            last_exit
                .map(|status| status.to_string())
                .unwrap_or_else(|| "未知状态".into())
        ))
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

async fn extension_status(State(gateway): State<AIGateway>) -> axum::Json<Value> {
    axum::Json(json!({ "state": gateway.manager.runtime_state(),
        "installedVersion": gateway.manager.installed_for_ai().map(|(installed, _)| installed.version) }))
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
    // Observing maintenance must not start a sidecar or join the requests being
    // drained. Only this exact read-only endpoint may bypass admission.
    let maintenance = gateway.admission.lock().expect("AI admission poisoned").0
        || gateway.manager.runtime_state() == "waiting_update";
    if method == Method::GET && uri.path() == "/ai/models" && maintenance {
        let mut snapshot = json!({ "models": [], "tasks": {} });
        if let Some(port) = gateway.running_port() {
            let response = reqwest::Client::builder()
                .no_proxy()
                .build()
                .map_err(|e| e.to_string())?
                .get(format!("http://127.0.0.1:{port}/ai/models"))
                .timeout(Duration::from_secs(5))
                .send()
                .await;
            if let Ok(response) = response {
                if response.status().is_success() {
                    if let Ok(value) = response.json::<Value>().await {
                        if value.is_object() {
                            snapshot = value;
                        }
                    }
                }
            }
        }
        snapshot["maintenance"] = json!(true);
        return Ok(Response::builder()
            .header("content-type", "application/json")
            .body(Body::from(snapshot.to_string()))
            .expect("valid model status response"));
    }
    let guard = gateway.begin_request()?;
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
    let client = reqwest::Client::builder()
        .no_proxy()
        .build()
        .map_err(|error| error.to_string())?;
    let mut request = client.request(
        reqwest::Method::from_bytes(method.as_str().as_bytes())
            .map_err(|error| error.to_string())?,
        url,
    );
    for (name, value) in headers.iter() {
        if name != "host" && !is_hop_by_hop(name.as_str(), &headers) {
            request = request.header(name, value);
        }
    }
    let upstream = request
        .body(bytes)
        .send()
        .await
        .map_err(|error| format!("AI Sidecar 请求失败：{error}"))?;
    forward_response_tracked(upstream, Some(guard))
}

fn is_hop_by_hop(name: &str, headers: &HeaderMap) -> bool {
    matches!(
        name,
        "connection"
            | "keep-alive"
            | "proxy-authenticate"
            | "proxy-authorization"
            | "te"
            | "trailer"
            | "transfer-encoding"
            | "upgrade"
            | "content-length"
    ) || headers.get_all("connection").iter().any(|value| {
        value
            .to_str()
            .map(|value| {
                value
                    .split(',')
                    .any(|token| token.trim().eq_ignore_ascii_case(name))
            })
            .unwrap_or(false)
    })
}

#[cfg(test)]
fn forward_response(upstream: reqwest::Response) -> Result<Response, String> {
    forward_response_tracked(upstream, None)
}

fn forward_response_tracked(
    upstream: reqwest::Response,
    guard: Option<RequestGuard>,
) -> Result<Response, String> {
    let status = upstream.status();
    let upstream_headers = upstream.headers().clone();
    let mut response = Response::builder().status(status.as_u16());
    for (name, value) in upstream_headers.iter() {
        if !is_hop_by_hop(name.as_str(), &upstream_headers) {
            response = response.header(name, value);
        }
    }
    response
        // SSE must reach the caller as it arrives. Hyper generates framing for
        // this connection; forwarding upstream Transfer-Encoding breaks it.
        .body(Body::from_stream(futures_util::stream::unfold(
            (Box::pin(upstream.bytes_stream()), guard),
            |(mut stream, guard)| async move {
                stream.next().await.map(|chunk| (chunk, (stream, guard)))
            },
        )))
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
    crate::stop_child_process_tree(child);
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
    use futures_util::StreamExt;

    #[tokio::test]
    async fn forwards_sse_before_upstream_finishes_without_hop_headers() {
        let listener = tokio::net::TcpListener::bind(("127.0.0.1", 0))
            .await
            .unwrap();
        let address = listener.local_addr().unwrap();
        let app = Router::new().fallback(any(|| async {
            let stream =
                futures_util::stream::once(async { Ok::<_, std::io::Error>("data: first\n\n") })
                    .chain(futures_util::stream::pending());
            Response::builder()
                .header("content-type", "text/event-stream")
                .header("connection", "keep-alive, x-private")
                .header("x-private", "internal")
                .body(Body::from_stream(stream))
                .unwrap()
        }));
        let server = tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
        let client = reqwest::Client::builder().no_proxy().build().unwrap();
        let upstream = client
            .get(format!("http://{address}/v1/chat/completions"))
            .send()
            .await
            .unwrap();
        assert!(upstream.headers().contains_key("transfer-encoding"));
        let ownership = Arc::new(Mutex::new((false, 1)));
        let response =
            forward_response_tracked(upstream, Some(RequestGuard(ownership.clone()))).unwrap();
        assert_eq!(response.status(), StatusCode::OK);
        assert_eq!(response.headers()["content-type"], "text/event-stream");
        for name in [
            "transfer-encoding",
            "connection",
            "x-private",
            "content-length",
        ] {
            assert!(!response.headers().contains_key(name));
        }
        let mut body = response.into_body().into_data_stream();
        let first = tokio::time::timeout(Duration::from_secs(2), body.next())
            .await
            .unwrap()
            .unwrap()
            .unwrap();
        assert_eq!(&first[..], b"data: first\n\n");
        assert_eq!(ownership.lock().unwrap().1, 1);
        drop(body);
        assert_eq!(ownership.lock().unwrap().1, 0);

        // Also serialize through Hyper: stale upstream framing used to close
        // this connection without any HTTP response, reported as 502 by callers.
        let proxy_listener = tokio::net::TcpListener::bind(("127.0.0.1", 0))
            .await
            .unwrap();
        let proxy_address = proxy_listener.local_addr().unwrap();
        let proxy = Router::new().fallback(any(move || async move {
            let client = reqwest::Client::builder().no_proxy().build().unwrap();
            let upstream = client
                .get(format!("http://{address}/v1/chat/completions"))
                .send()
                .await
                .unwrap();
            forward_response(upstream).unwrap()
        }));
        let proxy_server =
            tokio::spawn(async move { axum::serve(proxy_listener, proxy).await.unwrap() });
        let reply = tokio::time::timeout(
            Duration::from_secs(2),
            client
                .get(format!("http://{proxy_address}/v1/chat/completions"))
                .send(),
        )
        .await
        .unwrap()
        .unwrap();
        assert_eq!(reply.status(), StatusCode::OK);
        let mut stream = reply.bytes_stream();
        let first = tokio::time::timeout(Duration::from_secs(2), stream.next())
            .await
            .unwrap()
            .unwrap()
            .unwrap();
        assert_eq!(&first[..], b"data: first\n\n");
        proxy_server.abort();
        server.abort();
    }

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

    #[test]
    #[ignore = "subprocess fixture for drain regression"]
    fn sidecar_sleep_fixture() {
        std::thread::sleep(Duration::from_secs(30));
    }

    #[tokio::test]
    async fn maintenance_waits_for_response_ownership_and_model_download_before_stopping() {
        use std::sync::atomic::AtomicUsize;
        let root = std::env::temp_dir().join(format!("trailsnap-gateway-drain-{}", now_seconds()));
        fs::create_dir_all(&root).unwrap();
        let manager =
            AIExtensionManager::initialize(&root, &root.join("catalog.json"), String::new())
                .unwrap();
        let gateway = AIGateway::new(manager, root.clone(), std::process::id());
        let polls = Arc::new(AtomicUsize::new(0));
        let listener = tokio::net::TcpListener::bind(("127.0.0.1", 0))
            .await
            .unwrap();
        let port = listener.local_addr().unwrap().port();
        let count = polls.clone();
        let app = Router::new().route("/ai/models", get(move || {
            let count = count.clone();
            async move {
                let poll = count.fetch_add(1, Ordering::SeqCst);
                axum::Json(json!({"models":[{"status":if poll == 0 { "downloading" } else { "ready" }}]}))
            }
        }));
        let server = tokio::spawn(async move {
            axum::serve(listener, app).await.unwrap();
        });
        let mut command = Command::new(std::env::current_exe().unwrap());
        command
            .args([
                "--exact",
                "ai_gateway::tests::sidecar_sleep_fixture",
                "--ignored",
            ])
            .stdout(Stdio::null())
            .stderr(Stdio::null());
        #[cfg(windows)]
        command.creation_flags(0x08000000);
        let child = command.spawn().unwrap();
        *gateway.sidecar.lock().unwrap() = Some(SidecarProcess {
            child,
            port,
            extension_id: "core-ai".into(),
        });
        gateway.admission.lock().unwrap().1 = 1;
        let request = RequestGuard(gateway.admission.clone());
        let copy = gateway.clone();
        let draining = tokio::spawn(async move { copy.drain_for_extension().await });
        tokio::time::sleep(Duration::from_millis(50)).await;
        assert!(gateway.running_port().is_some());
        assert_eq!(polls.load(Ordering::SeqCst), 0);
        assert!(gateway
            .begin_request()
            .unwrap_err()
            .contains("等待 AI 扩展更新"));
        let observed = proxy_inner(
            &gateway,
            Method::GET,
            "/ai/models".parse().unwrap(),
            HeaderMap::new(),
            Body::empty(),
        )
        .await
        .unwrap();
        let observed: Value =
            serde_json::from_slice(&to_bytes(observed.into_body(), 1024 * 1024).await.unwrap())
                .unwrap();
        assert_eq!(observed["maintenance"], true);
        assert_eq!(observed["models"][0]["status"], "downloading");
        assert_eq!(gateway.admission.lock().unwrap().1, 1);
        assert!(proxy_inner(
            &gateway,
            Method::POST,
            "/ai/models/llm/download".parse().unwrap(),
            HeaderMap::new(),
            Body::empty()
        )
        .await
        .is_err());
        polls.store(0, Ordering::SeqCst);
        drop(request);
        tokio::time::timeout(Duration::from_secs(2), async {
            while polls.load(Ordering::SeqCst) == 0 {
                tokio::time::sleep(Duration::from_millis(10)).await;
            }
        })
        .await
        .unwrap();
        assert!(gateway.running_port().is_some());
        tokio::time::timeout(Duration::from_secs(3), draining)
            .await
            .unwrap()
            .unwrap()
            .unwrap();
        assert!(gateway.running_port().is_none());
        assert!(polls.load(Ordering::SeqCst) >= 2);
        let observed = proxy_inner(
            &gateway,
            Method::GET,
            "/ai/models".parse().unwrap(),
            HeaderMap::new(),
            Body::empty(),
        )
        .await
        .unwrap();
        assert_eq!(observed.status(), StatusCode::OK);
        assert!(gateway.running_port().is_none());
        server.abort();
        fs::remove_dir_all(root).unwrap();
    }
}
