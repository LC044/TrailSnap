use flate2::read::GzDecoder;
use futures_util::StreamExt;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{
    collections::HashMap,
    fs::{self, File, OpenOptions},
    io::{Read, Write},
    path::{Component, Path, PathBuf},
    sync::{Arc, Mutex},
    time::{SystemTime, UNIX_EPOCH},
};

#[derive(Clone, Default, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
struct ExtensionCatalog {
    #[serde(default = "schema_version")]
    schema_version: u32,
    #[serde(default)]
    extensions: Vec<ExtensionDefinition>,
}

fn schema_version() -> u32 {
    1
}

#[derive(Clone, Default, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
struct ExtensionDefinition {
    id: String,
    name: String,
    version: String,
    description: String,
    #[serde(default)]
    capabilities: Vec<String>,
    #[serde(default)]
    requirements: Value,
    #[serde(default)]
    assets: HashMap<String, ExtensionAsset>,
}

#[derive(Clone, Default, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
struct ExtensionAsset {
    url: String,
    sha256: String,
    #[serde(default)]
    size: Option<u64>,
    #[serde(default)]
    filename: Option<String>,
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct InstalledExtension {
    pub id: String,
    pub version: String,
    pub platform: String,
    pub capabilities: Vec<String>,
    pub entrypoint: String,
    #[serde(default)]
    pub model_path: Option<String>,
    pub checksum: String,
    pub installed_at: String,
}

#[derive(Default, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
struct InstalledState {
    #[serde(default = "schema_version")]
    schema_version: u32,
    #[serde(default)]
    extensions: HashMap<String, InstalledExtension>,
}

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct InstallJob {
    id: String,
    status: String,
    received: u64,
    total: Option<u64>,
    progress: u8,
    error: Option<String>,
    updated_at: String,
}

struct ManagerData {
    catalog: ExtensionCatalog,
    catalog_error: Option<String>,
    installed: HashMap<String, InstalledExtension>,
    jobs: HashMap<String, InstallJob>,
}

#[derive(Clone)]
pub struct AIExtensionManager {
    root: PathBuf,
    download_dir: PathBuf,
    state_path: PathBuf,
    catalog_url: String,
    platform_key: String,
    data: Arc<Mutex<ManagerData>>,
}

impl AIExtensionManager {
    pub fn initialize(
        app_root: &Path,
        catalog_path: &Path,
        catalog_url: String,
    ) -> Result<Self, String> {
        let root = app_root.join("ai-extensions");
        let download_dir = root.join(".downloads");
        fs::create_dir_all(&download_dir)
            .map_err(|error| format!("无法创建 AI 扩展目录：{error}"))?;
        let catalog = read_json::<ExtensionCatalog>(catalog_path).unwrap_or_default();
        let state_path = root.join("installed.json");
        let installed = read_json::<InstalledState>(&state_path)
            .map(|state| state.extensions)
            .unwrap_or_default();
        Ok(Self {
            root,
            download_dir,
            state_path,
            catalog_url,
            platform_key: platform_key(),
            data: Arc::new(Mutex::new(ManagerData {
                catalog,
                catalog_error: None,
                installed,
                jobs: HashMap::new(),
            })),
        })
    }

    pub async fn refresh_catalog(&self) -> Result<(), String> {
        if self.catalog_url.is_empty() {
            return Ok(());
        }
        let result = async {
            let response = reqwest::Client::new()
                .get(&self.catalog_url)
                .timeout(std::time::Duration::from_secs(15))
                .send()
                .await
                .map_err(|error| format!("下载扩展清单失败：{error}"))?;
            if !response.status().is_success() {
                return Err(format!("扩展包清单返回 HTTP {}", response.status()));
            }
            let catalog = response
                .json::<ExtensionCatalog>()
                .await
                .map_err(|error| format!("扩展包清单格式无效：{error}"))?;
            if catalog.extensions.is_empty() {
                return Err("扩展包清单缺少 extensions".to_string());
            }
            Ok(catalog)
        }
        .await;
        let mut data = self.data.lock().expect("AI extension manager poisoned");
        match result {
            Ok(catalog) => {
                data.catalog = catalog;
                data.catalog_error = None;
                Ok(())
            }
            Err(error) => {
                data.catalog_error = Some(error.clone());
                Err(error)
            }
        }
    }

    pub fn list(&self) -> Value {
        let data = self.data.lock().expect("AI extension manager poisoned");
        let extensions = data
            .catalog
            .extensions
            .iter()
            .map(|extension| {
                let asset = extension.assets.get(&self.platform_key);
                json!({
                    "id": extension.id,
                    "name": extension.name,
                    "version": extension.version,
                    "description": extension.description,
                    "capabilities": extension.capabilities,
                    "requirements": extension.requirements,
                    "available": asset.map(|item| !item.url.is_empty() && !item.sha256.is_empty()).unwrap_or(false),
                    "downloadSize": asset.and_then(|item| item.size),
                    "installed": data.installed.get(&extension.id),
                    "job": data.jobs.get(&extension.id),
                })
            })
            .collect::<Vec<_>>();
        json!({
            "platform": self.platform_key,
            "catalogError": data.catalog_error,
            "extensions": extensions,
        })
    }

    pub fn installed_for_ai(&self) -> Option<(InstalledExtension, PathBuf)> {
        let data = self.data.lock().expect("AI extension manager poisoned");
        data.installed
            .values()
            .find(|item| {
                item.capabilities.iter().any(|capability| {
                    matches!(capability.as_str(), "ocr" | "tickets" | "classification")
                })
            })
            .cloned()
            .map(|item| {
                let directory = self.root.join(&item.id);
                (item, directory)
            })
    }

    pub fn start_install(&self, id: &str) -> Result<Value, String> {
        let (extension, asset) = {
            let mut data = self.data.lock().expect("AI extension manager poisoned");
            if let Some(job) = data.jobs.get(id) {
                if matches!(
                    job.status.as_str(),
                    "downloading" | "verifying" | "installing"
                ) {
                    return serde_json::to_value(job).map_err(|error| error.to_string());
                }
            }
            let extension = data
                .catalog
                .extensions
                .iter()
                .find(|item| item.id == id)
                .cloned()
                .ok_or_else(|| format!("未知 AI 扩展包：{id}"))?;
            let asset = extension
                .assets
                .get(&self.platform_key)
                .cloned()
                .filter(|item| !item.url.is_empty() && !item.sha256.is_empty())
                .ok_or_else(|| {
                    "当前平台暂无可下载且带 SHA-256 的扩展包，请使用离线导入".to_string()
                })?;
            let job = InstallJob {
                id: id.to_string(),
                status: "downloading".into(),
                received: 0,
                total: asset.size,
                progress: 0,
                error: None,
                updated_at: now_string(),
            };
            data.jobs.insert(id.to_string(), job.clone());
            (extension, asset)
        };
        let manager = self.clone();
        let id = id.to_string();
        let task_id = id.clone();
        tauri::async_runtime::spawn(async move {
            if let Err(error) = manager.install_remote(&extension, &asset).await {
                manager.fail_job(&task_id, error);
            }
        });
        Ok(self.job_value(id.as_str()))
    }

    pub fn pause(&self, id: &str) -> Result<Value, String> {
        let mut data = self.data.lock().expect("AI extension manager poisoned");
        let job = data
            .jobs
            .get_mut(id)
            .ok_or_else(|| "找不到下载任务".to_string())?;
        if job.status != "downloading" {
            return Err("扩展包当前不在下载中".into());
        }
        job.status = "paused".into();
        job.updated_at = now_string();
        serde_json::to_value(job).map_err(|error| error.to_string())
    }

    pub fn retry(&self, id: &str) -> Result<Value, String> {
        {
            let mut data = self.data.lock().expect("AI extension manager poisoned");
            let status = data
                .jobs
                .get(id)
                .map(|job| job.status.clone())
                .ok_or_else(|| "找不到下载任务".to_string())?;
            if !matches!(status.as_str(), "paused" | "failed") {
                return Err("扩展包当前不可重试".into());
            }
            data.jobs.remove(id);
        }
        self.start_install(id)
    }

    pub fn import_archive(&self, archive: &Path) -> Result<InstalledExtension, String> {
        if !archive.is_file() {
            return Err("选择的 AI 扩展包不存在".into());
        }
        let checksum = sha256_file(archive)?;
        let temp = self.extract_archive(archive)?;
        let result = (|| {
            let manifest = read_json::<ExtensionManifest>(&temp.join("manifest.json"))
                .map_err(|error| format!("扩展包 manifest 无效：{error}"))?;
            let known = self
                .data
                .lock()
                .expect("AI extension manager poisoned")
                .catalog
                .extensions
                .iter()
                .any(|item| item.id == manifest.id);
            if !known {
                return Err(format!("离线包 ID 不在清单中：{}", manifest.id));
            }
            self.activate_extracted(&manifest.id, &temp, &checksum)
        })();
        if result.is_err() {
            let _ = fs::remove_dir_all(&temp);
        }
        result
    }

    pub fn uninstall(&self, id: &str) -> Result<(), String> {
        let target = self.root.join(id);
        if target.parent() != Some(self.root.as_path()) {
            return Err("扩展包路径越界".into());
        }
        {
            let data = self.data.lock().expect("AI extension manager poisoned");
            if !data.installed.contains_key(id) {
                return Err("扩展包尚未安装".into());
            }
        }
        fs::remove_dir_all(&target).map_err(|error| format!("删除扩展包失败：{error}"))?;
        let mut data = self.data.lock().expect("AI extension manager poisoned");
        data.installed.remove(id);
        data.jobs.remove(id);
        self.save_state(&data.installed)
    }

    async fn install_remote(
        &self,
        extension: &ExtensionDefinition,
        asset: &ExtensionAsset,
    ) -> Result<(), String> {
        let archive = self.download_dir.join(format!(
            "{}-{}.tar.gz.part",
            extension.id, self.platform_key
        ));
        let mut offset = fs::metadata(&archive).map(|item| item.len()).unwrap_or(0);
        let client = reqwest::Client::new();
        let mut request = client
            .get(&asset.url)
            .timeout(std::time::Duration::from_secs(30 * 60));
        if offset > 0 {
            request = request.header(reqwest::header::RANGE, format!("bytes={offset}-"));
        }
        let response = request
            .send()
            .await
            .map_err(|error| format!("下载 AI 扩展包失败：{error}"))?;
        if !response.status().is_success() {
            return Err(format!("扩展包下载返回 HTTP {}", response.status()));
        }
        if offset > 0 && response.status() == reqwest::StatusCode::OK {
            offset = 0;
            let _ = fs::remove_file(&archive);
        }
        let total = asset
            .size
            .or_else(|| response.content_length().map(|length| length + offset));
        let mut output = OpenOptions::new()
            .create(true)
            .append(offset > 0)
            .write(true)
            .truncate(offset == 0)
            .open(&archive)
            .map_err(|error| format!("无法写入 AI 扩展包：{error}"))?;
        let mut received = offset;
        let mut stream = response.bytes_stream();
        while let Some(chunk) = stream.next().await {
            if self.job_status(&extension.id).as_deref() == Some("paused") {
                return Ok(());
            }
            let chunk = chunk.map_err(|error| format!("下载 AI 扩展包失败：{error}"))?;
            output
                .write_all(&chunk)
                .map_err(|error| format!("无法写入 AI 扩展包：{error}"))?;
            received += chunk.len() as u64;
            self.update_progress(&extension.id, received, total);
        }
        output.flush().map_err(|error| error.to_string())?;
        self.set_job_status(&extension.id, "verifying");
        let actual = sha256_file(&archive)?;
        if !actual.eq_ignore_ascii_case(&asset.sha256) {
            return Err(format!(
                "SHA-256 校验失败：期望 {}，实际 {actual}",
                asset.sha256
            ));
        }
        let temp = self.extract_archive(&archive)?;
        let result = self.activate_extracted(&extension.id, &temp, &actual);
        if result.is_err() {
            let _ = fs::remove_dir_all(&temp);
        }
        result?;
        let _ = fs::remove_file(archive);
        Ok(())
    }

    fn extract_archive(&self, archive: &Path) -> Result<PathBuf, String> {
        let temp = self.root.join(format!(".install-{}", now_millis()));
        fs::create_dir_all(&temp).map_err(|error| error.to_string())?;
        let file = File::open(archive).map_err(|error| error.to_string())?;
        let mut bundle = tar::Archive::new(GzDecoder::new(file));
        let entries = bundle.entries().map_err(|error| error.to_string())?;
        for entry in entries {
            let mut entry = entry.map_err(|error| error.to_string())?;
            let path = entry.path().map_err(|error| error.to_string())?;
            if path.components().any(|part| {
                matches!(
                    part,
                    Component::ParentDir | Component::RootDir | Component::Prefix(_)
                )
            }) {
                let _ = fs::remove_dir_all(&temp);
                return Err(format!("扩展包包含不安全路径：{}", path.display()));
            }
            if !entry.unpack_in(&temp).map_err(|error| error.to_string())? {
                let _ = fs::remove_dir_all(&temp);
                return Err("扩展包包含越界路径".into());
            }
        }
        Ok(temp)
    }

    fn activate_extracted(
        &self,
        id: &str,
        temp: &Path,
        checksum: &str,
    ) -> Result<InstalledExtension, String> {
        self.set_job_status(id, "installing");
        let manifest = read_json::<ExtensionManifest>(&temp.join("manifest.json"))
            .map_err(|error| format!("扩展包 manifest 无效：{error}"))?;
        if manifest.id != id {
            return Err(format!("扩展包 ID 不匹配：{}", manifest.id));
        }
        if manifest.platform != self.platform_key {
            return Err(format!("扩展包平台不匹配：{}", manifest.platform));
        }
        if manifest.version.is_empty() || manifest.capabilities.is_empty() {
            return Err("扩展包 manifest 缺少版本或能力列表".into());
        }
        let entrypoint = safe_child_path(temp, &manifest.entrypoint)?;
        if !entrypoint.is_file() {
            return Err("扩展包入口文件无效".into());
        }
        if let Some(model_path) = manifest.model_path.as_deref() {
            safe_child_path(temp, model_path)?;
        }
        let destination = self.root.join(id);
        let backup = self.root.join(format!("{id}.old"));
        let _ = fs::remove_dir_all(&backup);
        if destination.exists() {
            fs::rename(&destination, &backup).map_err(|error| error.to_string())?;
        }
        if let Err(error) = fs::rename(temp, &destination) {
            let _ = fs::rename(&backup, &destination);
            return Err(format!("启用 AI 扩展包失败：{error}"));
        }
        let _ = fs::remove_dir_all(backup);
        let installed = InstalledExtension {
            id: id.to_string(),
            version: manifest.version,
            platform: manifest.platform,
            capabilities: manifest.capabilities,
            entrypoint: manifest.entrypoint,
            model_path: manifest.model_path,
            checksum: checksum.to_string(),
            installed_at: now_string(),
        };
        let mut data = self.data.lock().expect("AI extension manager poisoned");
        data.installed.insert(id.to_string(), installed.clone());
        data.jobs.insert(
            id.to_string(),
            InstallJob {
                id: id.to_string(),
                status: "installed".into(),
                received: 0,
                total: None,
                progress: 100,
                error: None,
                updated_at: now_string(),
            },
        );
        self.save_state(&data.installed)?;
        Ok(installed)
    }

    fn save_state(&self, installed: &HashMap<String, InstalledExtension>) -> Result<(), String> {
        let temp = self.state_path.with_extension("json.tmp");
        let bytes = serde_json::to_vec_pretty(&InstalledState {
            schema_version: 1,
            extensions: installed.clone(),
        })
        .map_err(|error| error.to_string())?;
        fs::write(&temp, bytes).map_err(|error| error.to_string())?;
        if self.state_path.exists() {
            fs::remove_file(&self.state_path).map_err(|error| error.to_string())?;
        }
        fs::rename(temp, &self.state_path).map_err(|error| error.to_string())
    }

    fn job_value(&self, id: &str) -> Value {
        self.data
            .lock()
            .expect("AI extension manager poisoned")
            .jobs
            .get(id)
            .and_then(|job| serde_json::to_value(job).ok())
            .unwrap_or(Value::Null)
    }

    fn job_status(&self, id: &str) -> Option<String> {
        self.data
            .lock()
            .expect("AI extension manager poisoned")
            .jobs
            .get(id)
            .map(|job| job.status.clone())
    }

    fn set_job_status(&self, id: &str, status: &str) {
        if let Some(job) = self
            .data
            .lock()
            .expect("AI extension manager poisoned")
            .jobs
            .get_mut(id)
        {
            job.status = status.into();
            job.updated_at = now_string();
        }
    }

    fn update_progress(&self, id: &str, received: u64, total: Option<u64>) {
        if let Some(job) = self
            .data
            .lock()
            .expect("AI extension manager poisoned")
            .jobs
            .get_mut(id)
        {
            job.received = received;
            job.total = total;
            job.progress = total
                .filter(|value| *value > 0)
                .map(|value| ((received.saturating_mul(100) / value).min(100)) as u8)
                .unwrap_or(0);
            job.updated_at = now_string();
        }
    }

    fn fail_job(&self, id: &str, error: String) {
        if let Some(job) = self
            .data
            .lock()
            .expect("AI extension manager poisoned")
            .jobs
            .get_mut(id)
        {
            if job.status != "paused" {
                job.status = "failed".into();
                job.error = Some(error);
                job.updated_at = now_string();
            }
        }
    }
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct ExtensionManifest {
    id: String,
    version: String,
    platform: String,
    #[serde(default)]
    capabilities: Vec<String>,
    entrypoint: String,
    #[serde(default)]
    model_path: Option<String>,
}

fn read_json<T: for<'de> Deserialize<'de>>(path: &Path) -> Result<T, String> {
    let bytes = fs::read(path).map_err(|error| error.to_string())?;
    serde_json::from_slice(&bytes).map_err(|error| error.to_string())
}

fn sha256_file(path: &Path) -> Result<String, String> {
    let mut file = File::open(path).map_err(|error| error.to_string())?;
    let mut digest = Sha256::new();
    let mut buffer = [0_u8; 1024 * 1024];
    loop {
        let count = file.read(&mut buffer).map_err(|error| error.to_string())?;
        if count == 0 {
            break;
        }
        digest.update(&buffer[..count]);
    }
    Ok(format!("{:x}", digest.finalize()))
}

fn safe_child_path(root: &Path, relative: &str) -> Result<PathBuf, String> {
    let relative = Path::new(relative);
    if relative.as_os_str().is_empty()
        || relative.components().any(|part| {
            matches!(
                part,
                Component::ParentDir | Component::RootDir | Component::Prefix(_)
            )
        })
    {
        return Err("扩展包入口路径无效".into());
    }
    Ok(root.join(relative))
}

fn platform_key() -> String {
    match (std::env::consts::OS, std::env::consts::ARCH) {
        ("windows", "x86_64") => "win32-x64".into(),
        ("macos", "aarch64") => "darwin-arm64".into(),
        ("macos", "x86_64") => "darwin-x64".into(),
        ("linux", "x86_64") => "linux-x64".into(),
        (os, arch) => format!("{os}-{arch}"),
    }
}

fn now_millis() -> u128 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis()
}

fn now_string() -> String {
    now_millis().to_string()
}

#[cfg(test)]
mod tests {
    use super::*;
    use flate2::{write::GzEncoder, Compression};

    #[test]
    fn child_path_rejects_traversal_and_absolute_paths() {
        let root = Path::new("C:/safe");
        assert!(safe_child_path(root, "runtime/trailsnap-ai.exe").is_ok());
        assert!(safe_child_path(root, "../escape.exe").is_err());
        assert!(safe_child_path(root, "/escape.exe").is_err());
    }

    #[test]
    fn imports_platform_extension_and_persists_state() {
        let test_root = std::env::temp_dir().join(format!("trailsnap-ai-import-{}", now_millis()));
        let staging = test_root.join("staging");
        fs::create_dir_all(staging.join("runtime")).unwrap();
        let entrypoint = if cfg!(windows) {
            "runtime/trailsnap-ai.exe"
        } else {
            "runtime/trailsnap-ai"
        };
        fs::write(staging.join(entrypoint), b"test-sidecar").unwrap();
        fs::write(
            staging.join("manifest.json"),
            serde_json::to_vec(&json!({
                "schemaVersion": 1,
                "id": "core-ai",
                "version": "0.9.2",
                "platform": platform_key(),
                "capabilities": ["ocr", "tickets", "classification"],
                "entrypoint": entrypoint,
            }))
            .unwrap(),
        )
        .unwrap();
        let catalog_path = test_root.join("ai-extensions.json");
        fs::write(
            &catalog_path,
            serde_json::to_vec(&json!({
                "schemaVersion": 1,
                "extensions": [{
                    "id": "core-ai",
                    "name": "TrailSnap AI 基础扩展",
                    "version": "0.9.2",
                    "description": "test",
                    "capabilities": ["ocr", "tickets", "classification"],
                    "requirements": {},
                    "assets": {}
                }]
            }))
            .unwrap(),
        )
        .unwrap();
        let archive_path = test_root.join("core-ai.tar.gz");
        let archive_file = File::create(&archive_path).unwrap();
        let encoder = GzEncoder::new(archive_file, Compression::default());
        let mut archive = tar::Builder::new(encoder);
        archive.append_dir_all(".", &staging).unwrap();
        archive.into_inner().unwrap().finish().unwrap();

        let manager =
            AIExtensionManager::initialize(&test_root, &catalog_path, String::new()).unwrap();
        let installed = manager.import_archive(&archive_path).unwrap();

        assert_eq!(installed.id, "core-ai");
        assert!(test_root
            .join("ai-extensions")
            .join("core-ai")
            .join(entrypoint)
            .is_file());
        assert!(test_root
            .join("ai-extensions")
            .join("installed.json")
            .is_file());
        fs::remove_dir_all(test_root).unwrap();
    }
}
