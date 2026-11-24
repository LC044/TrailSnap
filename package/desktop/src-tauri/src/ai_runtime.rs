//! Optional, signed AI sidecars. Models and the bundled CPU runtime are immutable here.
use crate::{ai_gateway::AIGateway, portable, update_network, update_transaction};
use futures_util::StreamExt;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::{fs, io::Write, path::{Path, PathBuf}, sync::Mutex, time::Duration};
use tauri::{Emitter, Manager};

pub const VERSION: &str = env!("CARGO_PKG_VERSION");
const MAX_SIZE: u64 = 12 * 1024 * 1024 * 1024;

#[derive(Clone, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Selection {
    pub backend: String,
    pub device: String,
    pub error: Option<String>,
}
impl Default for Selection {
    fn default() -> Self { Self { backend: "cpu".into(), device: "CPU".into(), error: None } }
}
pub fn validate_selection(backend: &str, device: &str) -> Result<(), String> {
    if !matches!(backend, "cpu" | "cuda" | "openvino") { return Err("未知 AI 后端".into()); }
    if backend == "openvino" && !(matches!(device, "CPU" | "GPU" | "NPU")
        || ["GPU.", "NPU."].iter().any(|prefix| device.strip_prefix(prefix).is_some_and(|s| !s.is_empty() && s.bytes().all(|b| b.is_ascii_digit())))) {
        return Err("请选择 CPU、GPU 或 NPU 设备".into());
    }
    Ok(())
}
pub fn load(root: &Path) -> Result<Selection, String> {
    let path = root.join("ai-runtime.json");
    if !path.exists() { return Ok(Selection::default()); }
    let config: Selection = portable::read_json(&path)?;
    validate_selection(&config.backend, &config.device)?;
    Ok(config)
}
pub fn save(root: &Path, selection: &Selection) -> Result<(), String> {
    portable::write_json(&root.join("ai-runtime.json"), selection)
}
pub fn installed_path(root: &Path, backend: &str) -> PathBuf {
    root.join("runtime/ai").join(VERSION).join(backend)
}
pub fn validate_runtime(path: &Path, backend: &str) -> Result<(), String> {
    let meta: Value = portable::read_json(&path.join("runtime-version.json"))
        .map_err(|_| "当前版本的加速包尚未安装或文件不完整，请重新下载".to_string())?;
    if meta["schemaVersion"] != 1 || meta["version"] != VERSION || meta["backend"] != backend
        || meta["platform"] != update_transaction::platform() || !path.join("trailsnap-ai.exe").is_file() {
        return Err("加速包版本或平台不兼容，请下载当前版本的加速包".into());
    }
    Ok(())
}

#[derive(Default)]
pub struct RuntimeState {
    operation: tokio::sync::Mutex<()>,
    progress: Mutex<Value>,
}
fn progress(app: &tauri::AppHandle, backend: &str, phase: &str, downloaded: u64, size: u64, error: Option<&str>) {
    let value = json!({"backend": backend, "phase": phase, "downloaded": downloaded, "size": size, "error": error});
    *app.state::<RuntimeState>().progress.lock().expect("AI progress poisoned") = value.clone();
    let _ = app.emit("desktop-ai-runtime-progress", value);
}

#[tauri::command]
pub async fn desktop_ai_runtime_status(app: tauri::AppHandle) -> Result<Value, String> {
    let gateway = app.try_state::<AIGateway>().ok_or("本地 AI 尚未就绪")?.inner().clone();
    let root = gateway.runtime_root();
    let selection = load(&root)?;
    let mut snapshot = json!({"selected": selection.backend, "device": selection.device, "error": selection.error,
        "supported": cfg!(all(windows, target_arch = "x86_64")), "version": VERSION,
        "packages": (["cuda", "openvino"].map(|backend| json!({"backend": backend,
            "installed": validate_runtime(&installed_path(&root, backend), backend).is_ok()}))),
        "progress": app.state::<RuntimeState>().progress.lock().expect("AI progress poisoned").clone()});
    // Polling must not restart an idle sidecar or contend with a switch.
    snapshot["runtime"] = gateway.device_status().await.unwrap_or_else(|error| json!({"backend": null, "deviceName": "等待 AI 服务", "error": error}));
    Ok(snapshot)
}

#[derive(Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
struct Package {
    version: String,
    backend: String,
    platform: String,
    filename: String,
    size: u64,
    sha256: String,
    signature: String,
}
fn filename(backend: &str) -> String { format!("TrailSnap-{VERSION}-ai-{backend}-windows-x64.zip") }
fn validate_package(package: &Package, backend: &str) -> Result<(), String> {
    if package.version != VERSION || package.backend != backend || package.platform != update_transaction::platform()
        || package.filename != filename(backend) || package.size == 0 || package.size > MAX_SIZE
        || package.sha256.len() != 64 || !package.sha256.bytes().all(|b| b.is_ascii_hexdigit()) || package.signature.is_empty() {
        return Err("加速包清单不匹配或不完整".into());
    }
    Ok(())
}

#[tauri::command]
pub async fn desktop_ai_runtime_download(app: tauri::AppHandle, backend: String) -> Result<(), String> {
    let _activity = crate::begin_activity(&app)?;
    let state = app.state::<RuntimeState>();
    let _lock = state.operation.try_lock().map_err(|_| "正在下载或切换 AI 运行时")?;
    if !cfg!(all(windows, target_arch = "x86_64")) || !matches!(backend.as_str(), "cuda" | "openvino") {
        return Err("加速包目前支持 Windows x64 的 CUDA 和 OpenVINO".into());
    }
    let root = app.state::<AIGateway>().runtime_root();
    if validate_runtime(&installed_path(&root, &backend), &backend).is_ok() { return Ok(()); }
    progress(&app, &backend, "checking", 0, 0, None);
    let result = download(&app, &root, &backend).await;
    match &result {
        Ok(_) => progress(&app, &backend, "ready", 0, 0, None),
        Err(error) => progress(&app, &backend, "error", 0, 0, Some(error)),
    }
    result
}

#[tauri::command]
pub async fn desktop_ai_runtime_auto(app: tauri::AppHandle) -> Result<(), String> {
    let _activity = crate::begin_activity(&app)?;
    let state = app.state::<RuntimeState>();
    let _lock = state.operation.try_lock().map_err(|_| "正在下载或切换 AI 运行时")?;
    let gateway = app.state::<AIGateway>().inner().clone();
    let root = gateway.runtime_root();
    progress(&app, "cpu", "detecting", 0, 0, None);
    let mut failures = Vec::new();
    let mut failed_download = None;
    for (backend, device) in runtime_candidates().await {
        if failed_download == Some(backend) {
            continue;
        }
        if backend != "cpu" && validate_runtime(&installed_path(&root, backend), backend).is_err() {
            progress(&app, backend, "checking", 0, 0, None);
            if let Err(error) = download(&app, &root, backend).await {
                failed_download = Some(backend);
                failures.push(format!("{backend}：{error}"));
                continue;
            }
        }
        progress(&app, backend, "switching", 0, 0, None);
        let result = gateway.switch_runtime(Selection { backend: backend.into(), device: device.into(), error: None }).await;
        match result {
            Ok(()) => {
                let fallback = (!failures.is_empty() && backend == "cpu")
                    .then(|| format!("已使用内置 CPU（{}）", failures.join("；")));
                progress(&app, backend, "ready", 0, 0, fallback.as_deref());
                return Ok(());
            }
            Err(error) => failures.push(format!("{backend} {device}：{error}")),
        }
    }
    let error = failures.join("；");
    progress(&app, "cpu", "error", 0, 0, Some(&error));
    Err(error)
}

async fn runtime_candidates() -> Vec<(&'static str, &'static str)> {
    #[cfg(all(windows, target_arch = "x86_64"))]
    {
        let (nvidia, devices) = tokio::join!(
            crate::hardware::cuda_devices(),
            crate::hardware::display_devices(),
        );
        let value = serde_json::from_str::<Value>(&devices).unwrap_or(Value::Null);
        let devices = value.as_array().map(Vec::as_slice).unwrap_or_else(|| std::slice::from_ref(&value));
        let cuda = nvidia.as_deref().is_some_and(|info| crate::hardware::cuda_compatible(info, 528, (6, 0)));
        windows_runtime_candidates(cuda, devices)
    }
    #[cfg(not(all(windows, target_arch = "x86_64")))]
    vec![("cpu", "CPU")]
}

#[cfg(any(all(windows, target_arch = "x86_64"), test))]
fn windows_runtime_candidates(cuda: bool, devices: &[Value]) -> Vec<(&'static str, &'static str)> {
    let mut candidates = Vec::new();
    if cuda {
        candidates.push(("cuda", "0"));
    }
    let intel = |device: &&Value| device["PNPDeviceID"].as_str().is_some_and(|id| id.contains("VEN_8086"));
    if devices.iter().filter(intel).any(|device| device["PNPClass"] == "Display") {
        candidates.push(("openvino", "GPU"));
    }
    if devices.iter().filter(intel).any(|device| {
        let name = device["Name"].as_str().unwrap_or_default().to_ascii_lowercase();
        device["PNPClass"] == "ComputeAccelerator" || name.contains("ai boost") || name.contains("npu")
    }) {
        candidates.push(("openvino", "NPU"));
    }
    candidates.push(("cpu", "CPU"));
    candidates
}

async fn download(app: &tauri::AppHandle, root: &Path, backend: &str) -> Result<(), String> {
    let base = format!("https://github.com/LC044/TrailSnap/releases/download/v{VERSION}/");
    let sources = update_network::candidates(&format!("{base}ai-runtimes.json"));
    let package = update_network::first_valid(&sources, |url| async move {
        let response = update_network::client()?.get(url).timeout(update_network::CATALOG_TIMEOUT)
            .send().await.map_err(|e| e.to_string())?.error_for_status().map_err(|e| e.to_string())?;
        let bytes = response.bytes().await.map_err(|e| e.to_string())?;
        if bytes.len() > 64 * 1024 { return Err("加速包清单过大".into()); }
        let catalog: Value = serde_json::from_slice(&bytes).map_err(|e| e.to_string())?;
        if catalog["schemaVersion"] != 1 { return Err("加速包清单版本不支持".into()); }
        let package: Package = serde_json::from_value(catalog["packages"][backend].clone()).map_err(|_| "当前版本尚未提供此加速包，请稍后重试")?;
        validate_package(&package, backend)?;
        Ok(package)
    }).await?;
    let parent = root.join("runtime/ai").join(VERSION);
    fs::create_dir_all(&parent).map_err(|e| e.to_string())?;
    let temp = parent.join(format!(".download-{}", uuid::Uuid::new_v4()));
    fs::create_dir(&temp).map_err(|e| e.to_string())?;
    let result = download_into(app, backend, &base, &package, &temp, &parent.join(backend)).await;
    // The only cleanup target is the fresh UUID directory created above.
    let _ = fs::remove_dir_all(&temp);
    result
}
async fn download_into(app: &tauri::AppHandle, backend: &str, base: &str, package: &Package, temp: &Path, destination: &Path) -> Result<(), String> {
    let sources = update_network::rank(update_network::candidates(&format!("{base}{}", package.filename))).await;
    let archive = temp.join("runtime.zip");
    let mut last_error = String::new();
    for round in 0..update_network::ROUNDS {
        update_network::backoff(round).await;
        for source in &sources {
            let attempt = async {
                progress(app, backend, "downloading", 0, package.size, None);
                fetch_archive(source, &archive, package.size, |downloaded| progress(app, backend, "downloading", downloaded, package.size, None)).await?;
                progress(app, backend, "verifying", package.size, package.size, None);
                let archive = archive.clone();
                let package = package.clone();
                tauri::async_runtime::spawn_blocking(move || update_transaction::verify_archive(&archive, &package.signature, &package.sha256))
                    .await.map_err(|e| e.to_string())??;
                Ok::<(), String>(())
            }.await;
            match attempt {
                Ok(()) => {
                    progress(app, backend, "installing", package.size, package.size, None);
                    let archive = archive.clone();
                    let staging = temp.join("unpacked");
                    let destination = destination.to_path_buf();
                    let backend = backend.to_owned();
                    return tauri::async_runtime::spawn_blocking(move || {
                        unpack(&archive, &staging, &backend)?;
                        // Preserve an invalid prior install until the replacement
                        // is verified and published. Windows refuses in-use files.
                        let previous = destination.with_file_name(format!(".previous-{backend}-{}", uuid::Uuid::new_v4()));
                        let replacing = destination.exists();
                        if replacing { fs::rename(&destination, &previous).map_err(|e| format!("旧加速包正在使用，请切回 CPU 后重试：{e}"))?; }
                        if let Err(error) = fs::rename(staging, &destination) {
                            if replacing { let _ = fs::rename(&previous, &destination); }
                            return Err(error.to_string());
                        }
                        Ok(())
                    }).await.map_err(|e| e.to_string())?;
                },
                Err(error) => last_error = error,
            }
        }
    }
    Err(format!("所有加速源均失败（已自动重试）：{last_error}"))
}

async fn fetch_archive(source: &str, archive: &Path, size: u64, on_progress: impl Fn(u64)) -> Result<(), String> {
    let response = update_network::client()?.get(source).send().await.map_err(|e| e.to_string())?
        .error_for_status().map_err(|e| e.to_string())?;
    let mut stream = response.bytes_stream();
    let mut file = fs::File::create(archive).map_err(|e| e.to_string())?;
    let mut downloaded = 0;
    let mut tick = std::time::Instant::now();
    while let Some(bytes) = stream.next().await {
        let bytes = bytes.map_err(|e| e.to_string())?;
        downloaded += bytes.len() as u64;
        if downloaded > size { return Err("加速包大小超过清单限制".into()); }
        file.write_all(&bytes).map_err(|e| e.to_string())?;
        if tick.elapsed() > Duration::from_millis(150) {
            on_progress(downloaded);
            tick = std::time::Instant::now();
        }
    }
    file.sync_all().map_err(|e| e.to_string())?;
    if downloaded != size { return Err("加速包下载不完整".into()); }
    on_progress(downloaded);
    Ok(())
}

fn unpack(archive: &Path, staging: &Path, backend: &str) -> Result<(), String> {
    let mut zip = zip::ZipArchive::new(fs::File::open(archive).map_err(|e| e.to_string())?).map_err(|e| e.to_string())?;
    if zip.len() > 100_000 { return Err("加速包文件过多".into()); }
    let mut total = 0u64;
    let mut paths = std::collections::HashSet::new();
    for index in 0..zip.len() {
        let mut entry = zip.by_index(index).map_err(|e| e.to_string())?;
        let name = entry.name().trim_end_matches('/');
        portable::relative_path(Path::new(name))?;
        if name.split('/').any(|part| part.ends_with(['.', ' '])) || name.contains('\\') || !paths.insert(name.to_lowercase()) || entry.unix_mode().is_some_and(|mode| mode & 0o170000 == 0o120000) {
            return Err("加速包包含无效路径或链接".into());
        }
        total = total.checked_add(entry.size()).ok_or("加速包过大")?;
        if total > MAX_SIZE { return Err("加速包解压大小超限".into()); }
        let path = staging.join(name);
        if entry.is_dir() { fs::create_dir_all(&path).map_err(|e| e.to_string())?; }
        else {
            fs::create_dir_all(path.parent().ok_or("加速包路径无效")?).map_err(|e| e.to_string())?;
            let mut file = fs::OpenOptions::new().write(true).create_new(true).open(&path).map_err(|e| e.to_string())?;
            std::io::copy(&mut entry, &mut file).map_err(|e| e.to_string())?;
        }
    }
    validate_runtime(staging, backend)
}

#[tauri::command]
pub async fn desktop_ai_runtime_select(app: tauri::AppHandle, backend: String, device: String) -> Result<(), String> {
    let _activity = crate::begin_activity(&app)?;
    let state = app.state::<RuntimeState>();
    let _lock = state.operation.try_lock().map_err(|_| "正在下载或切换 AI 运行时")?;
    validate_selection(&backend, &device)?;
    let gateway = app.state::<AIGateway>().inner().clone();
    let root = gateway.runtime_root();
    if backend != "cpu" {
        if !cfg!(all(windows, target_arch = "x86_64")) { return Err("加速包目前仅支持 Windows x64".into()); }
        validate_runtime(&installed_path(&root, &backend), &backend)?;
    }
    progress(&app, &backend, "switching", 0, 0, None);
    let result = gateway.switch_runtime(Selection { backend: backend.clone(), device, error: None }).await;
    match &result {
        Ok(_) => progress(&app, &backend, "ready", 0, 0, None),
        Err(error) => progress(&app, &backend, "error", 0, 0, Some(error)),
    }
    result
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn automatic_selection_only_offers_matching_hardware() {
        let devices = [
            json!({"PNPDeviceID": "PCI\\VEN_1002", "PNPClass": "Display"}),
            json!({"PNPDeviceID": "PCI\\VEN_8086", "PNPClass": "Display"}),
            json!({"PNPDeviceID": "PCI\\VEN_8086", "Name": "Intel(R) AI Boost"}),
        ];
        assert_eq!(windows_runtime_candidates(true, &devices), [
            ("cuda", "0"), ("openvino", "GPU"), ("openvino", "NPU"), ("cpu", "CPU")
        ]);
        assert_eq!(windows_runtime_candidates(false, &devices[..1]), [("cpu", "CPU")]);
    }

    #[test]
    fn selection_rejects_unknown_backends_and_invalid_devices() {
        assert!(validate_selection("openvino", "GPU.1").is_ok());
        for (backend, device) in [("evil", "CPU"), ("openvino", "AUTO"), ("openvino", "../GPU"), ("openvino", "GPU.")] {
            assert!(validate_selection(backend, device).is_err());
        }
    }
    #[test]
    fn catalog_rejects_other_versions_platforms_and_paths() {
        let mut package = Package { version: VERSION.into(), backend: "cuda".into(), platform: update_transaction::platform(),
            filename: filename("cuda"), size: 1, sha256: "a".repeat(64), signature: "signature".into() };
        assert!(validate_package(&package, "cuda").is_ok());
        package.version = "0.0.0".into();
        assert!(validate_package(&package, "cuda").is_err());
        package.version = VERSION.into();
        package.filename = "../evil.zip".into();
        assert!(validate_package(&package, "cuda").is_err());
        package.filename = filename("cuda");
        assert!(validate_package(&package, "openvino").is_err());
    }

    fn temporary() -> PathBuf {
        let root = std::env::temp_dir().join(format!("ai-runtime-{}", uuid::Uuid::new_v4()));
        fs::create_dir_all(&root).unwrap(); root
    }

    fn write_zip(path: &Path, files: &[(&str, &[u8])]) {
        let mut zip = zip::ZipWriter::new(fs::File::create(path).unwrap());
        for (name, bytes) in files {
            zip.start_file(*name, zip::write::SimpleFileOptions::default()).unwrap();
            zip.write_all(bytes).unwrap();
        }
        zip.finish().unwrap();
    }

    #[test]
    fn extraction_rejects_traversal_and_other_runtime_versions() {
        let root = temporary();
        let archive = root.join("runtime.zip");
        write_zip(&archive, &[("../escaped.exe", b"bad")]);
        assert!(unpack(&archive, &root.join("staging"), "cuda").is_err());
        assert!(!root.join("escaped.exe").exists());
        let metadata = json!({"schemaVersion": 1, "version": "0.0.0", "backend": "cuda", "platform": update_transaction::platform()}).to_string();
        write_zip(&archive, &[("runtime-version.json", metadata.as_bytes()), ("trailsnap-ai.exe", b"exe")]);
        assert!(unpack(&archive, &root.join("staging2"), "cuda").is_err());
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn compatible_install_and_selection_survive_restart_without_touching_models() {
        let root = temporary();
        let target = installed_path(&root, "cuda");
        fs::create_dir_all(root.join("models")).unwrap();
        fs::write(root.join("models/keep.onnx"), b"model").unwrap();
        let metadata = json!({"schemaVersion": 1, "version": VERSION, "backend": "cuda", "platform": update_transaction::platform()}).to_string();
        let archive = root.join("runtime.zip");
        write_zip(&archive, &[("runtime-version.json", metadata.as_bytes()), ("trailsnap-ai.exe", b"exe")]);
        unpack(&archive, &target, "cuda").unwrap();
        save(&root, &Selection { backend: "cuda".into(), device: "CPU".into(), error: None }).unwrap();
        assert_eq!(load(&root).unwrap().backend, "cuda");
        assert!(validate_runtime(&target, "cuda").is_ok());
        assert!(validate_runtime(&target, "openvino").is_err());
        assert_eq!(fs::read(root.join("models/keep.onnx")).unwrap(), b"model");
        fs::remove_dir_all(root).unwrap();
    }

    #[tokio::test]
    async fn download_rejects_truncation_and_excess_then_can_retry() {
        let root = temporary();
        let archive = root.join("download.zip");
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = listener.local_addr().unwrap();
        let server = tokio::spawn(async move {
            axum::serve(listener, axum::Router::new().route("/runtime", axum::routing::get(|| async { "abc" }))).await.unwrap();
        });
        let url = format!("http://{address}/runtime");
        assert!(fetch_archive(&url, &archive, 4, |_| {}).await.unwrap_err().contains("不完整"));
        assert!(fetch_archive(&url, &archive, 2, |_| {}).await.unwrap_err().contains("超过"));
        fetch_archive(&url, &archive, 3, |_| {}).await.unwrap();
        assert_eq!(fs::read(&archive).unwrap(), b"abc");
        server.abort();
        fs::remove_dir_all(root).unwrap();
    }
}
