use flate2::read::GzDecoder;
use futures_util::StreamExt;
use semver::Version;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{
    collections::{HashMap, HashSet},
    fs::{self, File, OpenOptions},
    io::{Read, Write},
    path::{Component, Path, PathBuf},
    sync::{
        atomic::{AtomicUsize, Ordering},
        Arc, Mutex,
    },
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
    #[serde(default)]
    releases: Vec<ExtensionRelease>,
}

#[derive(Clone, Default, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
struct ExtensionRelease {
    version: String,
    #[serde(default)]
    assets: HashMap<String, ExtensionAsset>,
}

/// The running Server is the sole authority for the minimum AI version.
#[derive(Clone, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ServerRequirements {
    pub server_version: String,
    #[serde(rename = "minimumAIExtensionVersion")]
    pub minimum_ai_extension_version: String,
}

#[derive(Default)]
struct Compatibility {
    status: &'static str,
    reason: String,
    target: Option<ExtensionRelease>,
    required: bool,
    runnable: bool,
}

fn version(value: &str) -> Option<Version> {
    Version::parse(value.trim_start_matches('v')).ok()
}

fn valid_asset(asset: &ExtensionAsset) -> bool {
    asset.url.starts_with("https://")
        && asset.sha256.len() == 64
        && asset.sha256.bytes().all(|c| c.is_ascii_hexdigit())
}

fn compatibility(
    extension: &ExtensionDefinition,
    installed: Option<&InstalledExtension>,
    requirements: Option<&ServerRequirements>,
    platform: &str,
    catalog_failed: bool,
) -> Compatibility {
    let unknown = |reason: &str| Compatibility {
        status: "unknown",
        reason: reason.into(),
        runnable: true,
        ..Default::default()
    };
    let Some(requirements) = requirements else {
        return unknown("等待 Server 提供最低支持的 AI 扩展版本");
    };
    let Some((server, minimum)) = version(&requirements.server_version)
        .zip(version(&requirements.minimum_ai_extension_version))
    else {
        return unknown("Server 的 AI 扩展版本要求格式无效");
    };
    if minimum.cmp_precedence(&server).is_gt() {
        return unknown("Server 最低支持的 AI 扩展版本不能高于 Server 版本");
    }
    let exact_release =
        if version(&extension.version).is_some_and(|v| v.cmp_precedence(&server).is_eq()) {
            Some(ExtensionRelease {
                version: extension.version.clone(),
                assets: extension.assets.clone(),
            })
        } else {
            extension
                .releases
                .iter()
                .find(|r| version(&r.version).is_some_and(|v| v.cmp_precedence(&server).is_eq()))
                .cloned()
        };
    let target = if catalog_failed {
        None
    } else {
        exact_release.filter(|r| r.assets.get(platform).is_some_and(valid_asset))
    };
    let Some(installed) = installed else {
        return Compatibility {
            status: "not_installed",
            target,
            runnable: false,
            ..Default::default()
        };
    };
    let Some(current) = version(&installed.version) else {
        return unknown("无法识别已安装扩展版本，保留当前运行能力");
    };
    if current.cmp_precedence(&minimum).is_ge() {
        // A newer catalog, network failure or remote rule cannot force an update.
        return Compatibility {
            status: "compatible",
            runnable: true,
            ..Default::default()
        };
    }
    let reason = format!(
        "Server {} 最低支持 AI 扩展 {}，当前为 {}，需更新到 {}{}",
        requirements.server_version,
        requirements.minimum_ai_extension_version,
        installed.version,
        requirements.server_version,
        if target.is_none() {
            "；同版本平台附件暂不可用，请重试或离线导入"
        } else {
            ""
        }
    );
    Compatibility {
        status: "required_update",
        reason,
        target,
        required: true,
        runnable: false,
    }
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
    auto_attempted: HashSet<String>,
    server_requirements: Option<ServerRequirements>,
}

#[derive(Clone)]
pub struct AIExtensionManager {
    root: PathBuf,
    download_dir: PathBuf,
    state_path: PathBuf,
    catalog_url: String,
    platform_key: String,
    data: Arc<Mutex<ManagerData>>,
    active_installs: Arc<AtomicUsize>,
    lifecycle: Arc<Mutex<Option<crate::extension_lifecycle::ExtensionLifecycle>>>,
    pause_signal: Arc<tokio::sync::Notify>,
}

struct InstallGuard(Arc<AtomicUsize>);
impl Drop for InstallGuard {
    fn drop(&mut self) {
        self.0.fetch_sub(1, Ordering::SeqCst);
    }
}

impl AIExtensionManager {
    pub fn runtime_view(&self) -> Self {
        let mut manager = self.clone();
        // Gateway only reads availability; avoid a manager/lifecycle/Gateway cycle.
        manager.lifecycle = Arc::new(Mutex::new(None));
        manager
    }
    pub fn configure_lifecycle(&self, lifecycle: crate::extension_lifecycle::ExtensionLifecycle) {
        *self.lifecycle.lock().expect("extension lifecycle poisoned") = Some(lifecycle);
    }

    fn lifecycle(&self) -> Option<crate::extension_lifecycle::ExtensionLifecycle> {
        self.lifecycle
            .lock()
            .expect("extension lifecycle poisoned")
            .clone()
    }

    fn acquire_operation(&self) -> Result<InstallGuard, String> {
        self.active_installs
            .compare_exchange(0, 1, Ordering::SeqCst, Ordering::SeqCst)
            .map_err(|_| "AI 扩展操作进行中，请等待完成后重试".to_string())?;
        Ok(InstallGuard(self.active_installs.clone()))
    }

    pub fn runtime_state(&self) -> &'static str {
        let data = self.data.lock().expect("AI extension manager poisoned");
        let Some(installed) = data.installed.values().next() else {
            return "missing";
        };
        let fallback = ExtensionDefinition {
            id: installed.id.clone(),
            ..Default::default()
        };
        let extension = data
            .catalog
            .extensions
            .iter()
            .find(|e| e.id == installed.id)
            .unwrap_or(&fallback);
        if compatibility(
            extension,
            Some(installed),
            data.server_requirements.as_ref(),
            &self.platform_key,
            data.catalog_error.is_some(),
        )
        .runnable
        {
            "ready"
        } else {
            "waiting_update"
        }
    }

    async fn finish_maintenance(&self) -> Result<(), String> {
        if let Some(lifecycle) = self.lifecycle() {
            lifecycle.finish(self.runtime_state()).await?;
        }
        Ok(())
    }

    pub async fn reconcile(&self) -> Result<(), String> {
        let Ok(guard) = self.acquire_operation() else {
            return Ok(());
        };
        self.finish_maintenance().await?;
        let candidates = {
            let mut data = self.data.lock().expect("AI extension manager poisoned");
            let candidates: Vec<_> = data
                .catalog
                .extensions
                .iter()
                .filter_map(|e| {
                    let result = compatibility(
                        e,
                        data.installed.get(&e.id),
                        data.server_requirements.as_ref(),
                        &self.platform_key,
                        data.catalog_error.is_some(),
                    );
                    if !result.required {
                        return None;
                    }
                    result.target.and_then(|r| {
                        r.assets.get(&self.platform_key).map(|asset| {
                            (
                                e.id.clone(),
                                format!("{}:{}:{}", e.id, r.version, asset.sha256),
                            )
                        })
                    })
                })
                .collect();
            candidates
                .into_iter()
                .filter(|(_, key)| data.auto_attempted.insert(key.clone()))
                .map(|(id, _)| id)
                .collect::<Vec<_>>()
        };
        drop(guard);
        for id in candidates {
            self.start_install(&id)?;
        }
        Ok(())
    }

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
        recover_transaction(&root, &state_path)?;
        let mut installed = read_json::<InstalledState>(&state_path)
            .map(|state| state.extensions)
            .unwrap_or_default();
        installed.retain(|id, item| {
            safe_child_path(&root, id)
                .ok()
                .and_then(|directory| safe_child_path(&directory, &item.entrypoint).ok())
                .is_some_and(|entry| entry.is_file())
        });
        Ok(Self {
            root,
            download_dir,
            state_path,
            catalog_url,
            platform_key: platform_key(),
            active_installs: Arc::new(AtomicUsize::new(0)),
            lifecycle: Arc::new(Mutex::new(None)),
            pause_signal: Arc::new(tokio::sync::Notify::new()),
            data: Arc::new(Mutex::new(ManagerData {
                catalog,
                catalog_error: None,
                installed,
                jobs: HashMap::new(),
                auto_attempted: HashSet::new(),
                server_requirements: None,
            })),
        })
    }

    pub async fn refresh_catalog(&self) -> Result<(), String> {
        if let Some(lifecycle) = self.lifecycle() {
            let requirements = lifecycle.requirements().await.map_err(|error| {
                self.data
                    .lock()
                    .expect("AI extension manager poisoned")
                    .catalog_error = Some(error.clone());
                error
            })?;
            if version(&requirements.server_version)
                .zip(version(&requirements.minimum_ai_extension_version))
                .is_none_or(|(server, minimum)| minimum.cmp_precedence(&server).is_gt())
            {
                let error = "Server AI 扩展版本要求无效".to_string();
                self.data
                    .lock()
                    .expect("AI extension manager poisoned")
                    .catalog_error = Some(error.clone());
                return Err(error);
            }
            self.data
                .lock()
                .expect("AI extension manager poisoned")
                .server_requirements = Some(requirements);
        }
        let catalog_url = if self.catalog_url.is_empty() {
            let data = self.data.lock().expect("AI extension manager poisoned");
            let server = data
                .server_requirements
                .as_ref()
                .map(|r| r.server_version.as_str())
                .unwrap_or(env!("CARGO_PKG_VERSION"));
            format!(
                "https://github.com/LC044/TrailSnap/releases/download/v{server}/ai-extensions.json"
            )
        } else {
            self.catalog_url.clone()
        };
        let result = async {
            let response = reqwest::Client::new()
                .get(&catalog_url)
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
            if catalog.schema_version > 2 {
                return Err("扩展包清单版本暂不支持".to_string());
            }
            let mut ids = HashSet::new();
            for extension in &catalog.extensions {
                validate_id(&extension.id)?;
                if !ids.insert(&extension.id) {
                    return Err("清单包含重复扩展 ID".into());
                }
                let mut releases = HashSet::new();
                if extension
                    .releases
                    .iter()
                    .any(|r| !releases.insert(&r.version))
                {
                    return Err("清单包含重复扩展版本".into());
                }
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
                let result = compatibility(extension, data.installed.get(&extension.id),
                    data.server_requirements.as_ref(), &self.platform_key, data.catalog_error.is_some());
                let asset = result.target.as_ref().and_then(|r| r.assets.get(&self.platform_key));
                let manual = compatibility(extension, None, data.server_requirements.as_ref(),
                    &self.platform_key, data.catalog_error.is_some()).target;
                let download_asset = asset.or_else(|| manual.as_ref().and_then(|r| r.assets.get(&self.platform_key)));
                json!({
                    "id": extension.id,
                    "name": extension.name,
                    "version": extension.version,
                    "description": extension.description,
                    "capabilities": extension.capabilities,
                    "requirements": extension.requirements,
                    "available": asset.is_some_and(valid_asset),
                    "compatibility": result.status,
                    "compatibilityReason": result.reason,
                    "updateVersion": result.target.as_ref().map(|r| &r.version),
                    "requiredUpdate": result.required,
                    "downloadUrl": download_asset.map(|a| &a.url),
                    "downloadFilename": download_asset.and_then(|a| a.filename.clone().or_else(|| a.url.rsplit('/').next().map(str::to_owned))),
                    "releasePageUrl": "https://github.com/LC044/TrailSnap/releases",
                    "downloadSize": download_asset.and_then(|item| item.size),
                    "installed": data.installed.get(&extension.id),
                    "job": data.jobs.get(&extension.id),
                })
            })
            .collect::<Vec<_>>();
        json!({
            "platform": self.platform_key,
            "clientVersion": env!("CARGO_PKG_VERSION"),
            "serverVersion": data.server_requirements.as_ref().map(|r| &r.server_version),
            "minimumAIExtensionVersion": data.server_requirements.as_ref().map(|r| &r.minimum_ai_extension_version),
            "operationBusy": self.has_active_installs(),
            "releasePageUrl": "https://github.com/LC044/TrailSnap/releases",
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
        validate_id(id)?;
        let install_guard = self.acquire_operation()?;
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
            let mut extension = data
                .catalog
                .extensions
                .iter()
                .find(|item| item.id == id)
                .cloned()
                .ok_or_else(|| format!("未知 AI 扩展包：{id}"))?;
            let result = compatibility(
                &extension,
                data.installed.get(id),
                data.server_requirements.as_ref(),
                &self.platform_key,
                data.catalog_error.is_some(),
            );
            let target = result
                .target
                .ok_or("没有可安装的兼容更新，请检查清单或使用离线导入")?;
            extension.version = target.version;
            extension.assets = target.assets;
            let asset = extension
                .assets
                .get(&self.platform_key)
                .cloned()
                .filter(valid_asset)
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
            let _guard = install_guard;
            if let Err(error) = manager.install_remote(&extension, &asset).await {
                manager.fail_job(&task_id, error);
            }
            if let Err(error) = manager.finish_maintenance().await {
                manager.fail_job(&task_id, error);
            }
        });
        Ok(self.job_value(id.as_str()))
    }

    pub fn has_active_installs(&self) -> bool {
        self.active_installs.load(Ordering::SeqCst) > 0
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
        self.pause_signal.notify_one();
        serde_json::to_value(job).map_err(|error| error.to_string())
    }

    pub fn retry(&self, id: &str) -> Result<Value, String> {
        {
            let data = self.data.lock().expect("AI extension manager poisoned");
            let status = data
                .jobs
                .get(id)
                .map(|job| job.status.clone())
                .ok_or_else(|| "找不到下载任务".to_string())?;
            if !matches!(status.as_str(), "paused" | "failed") {
                return Err("扩展包当前不可重试".into());
            }
        }
        self.start_install(id)
    }

    #[cfg(test)]
    pub fn import_archive(&self, archive: &Path) -> Result<InstalledExtension, String> {
        let _guard = self.acquire_operation()?;
        let (temp, manifest, checksum) = self.prepare_archive(archive)?;
        let result = self.activate_extracted(&manifest.id, &temp, &checksum);
        if result.is_err() {
            let _ = fs::remove_dir_all(&temp);
        }
        result
    }

    fn prepare_archive(
        &self,
        archive: &Path,
    ) -> Result<(PathBuf, ExtensionManifest, String), String> {
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
            safe_child_path(&self.root, &manifest.id)?;
            validate_id(&manifest.id)?;
            self.validate_manifest(&manifest, &temp)?;
            let data = self.data.lock().expect("AI extension manager poisoned");
            if let Some(extension) = data.catalog.extensions.iter().find(|e| e.id == manifest.id) {
                let expected = extension
                    .releases
                    .iter()
                    .find(|r| r.version == manifest.version)
                    .and_then(|r| r.assets.get(&self.platform_key))
                    .or_else(|| {
                        (extension.version == manifest.version)
                            .then(|| extension.assets.get(&self.platform_key))
                            .flatten()
                    });
                if expected.is_some_and(|asset| {
                    valid_asset(asset) && !asset.sha256.eq_ignore_ascii_case(&checksum)
                }) {
                    return Err("离线包 SHA-256 与发布清单不匹配".into());
                }
                let proposed = InstalledExtension {
                    id: manifest.id.clone(),
                    version: manifest.version.clone(),
                    platform: manifest.platform.clone(),
                    capabilities: manifest.capabilities.clone(),
                    entrypoint: manifest.entrypoint.clone(),
                    model_path: manifest.model_path.clone(),
                    checksum: checksum.clone(),
                    installed_at: now_string(),
                };
                let result = compatibility(
                    extension,
                    Some(&proposed),
                    data.server_requirements.as_ref(),
                    &self.platform_key,
                    data.catalog_error.is_some(),
                );
                if result.required {
                    return Err("离线包低于 Server 最低支持的扩展版本".into());
                }
            }
            Ok((temp.clone(), manifest, checksum))
        })();
        if result.is_err() {
            let _ = fs::remove_dir_all(&temp);
        }
        result
    }

    pub async fn import_archive_safely(
        &self,
        archive: PathBuf,
    ) -> Result<InstalledExtension, String> {
        let _guard = self.acquire_operation()?;
        let manager = self.clone();
        let (temp, manifest, checksum) =
            tauri::async_runtime::spawn_blocking(move || manager.prepare_archive(&archive))
                .await
                .map_err(|e| e.to_string())??;
        let result = async {
            if let Some(lifecycle) = self.lifecycle() {
                lifecycle.begin().await?;
            }
            let manager = self.clone();
            let directory = temp.clone();
            tauri::async_runtime::spawn_blocking(move || {
                manager.activate_extracted(&manifest.id, &directory, &checksum)
            })
            .await
            .map_err(|e| e.to_string())?
        }
        .await;
        if result.is_err() {
            let _ = fs::remove_dir_all(&temp);
        }
        let resumed = self.finish_maintenance().await;
        result.and_then(|installed| resumed.map(|_| installed))
    }

    pub async fn uninstall_safely(&self, id: &str) -> Result<(), String> {
        let _guard = self.acquire_operation()?;
        let result = async {
            if let Some(lifecycle) = self.lifecycle() {
                lifecycle.begin().await?;
            }
            self.uninstall(id)
        }
        .await;
        let resumed = self.finish_maintenance().await;
        result.and(resumed)
    }

    pub async fn install_llama_runtime(&self) -> Result<Value, String> {
        let _guard = self.acquire_operation()?;
        let result = async {
            if let Some(lifecycle) = self.lifecycle() {
                lifecycle.begin().await?;
            }
            crate::llama_runtime::install().await
        }
        .await;
        let resumed = self.finish_maintenance().await;
        result.and_then(|value| resumed.map(|_| value))
    }

    fn uninstall(&self, id: &str) -> Result<(), String> {
        validate_id(id)?;
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
        let previous = self
            .data
            .lock()
            .expect("AI extension manager poisoned")
            .installed
            .clone();
        let mut next = previous.clone();
        next.remove(id);
        let backup = self.root.join(format!("{id}.old"));
        let journal = self.root.join("transaction.json");
        if backup.exists() {
            fs::remove_dir_all(&backup).map_err(|e| e.to_string())?;
        }
        fs::write(
            &journal,
            serde_json::to_vec(&json!({ "id": id, "previous": previous,
            "hadDestination": target.exists() }))
            .map_err(|e| e.to_string())?,
        )
        .map_err(|e| e.to_string())?;
        let result = (|| {
            if target.exists() {
                fs::rename(&target, &backup).map_err(|e| e.to_string())?;
            }
            self.save_state(&next)?;
            fs::remove_file(&journal).map_err(|e| e.to_string())?;
            Ok::<_, String>(())
        })();
        if let Err(error) = result {
            recover_transaction(&self.root, &self.state_path)?;
            return Err(error);
        }
        let _ = fs::remove_dir_all(backup);
        let mut data = self.data.lock().expect("AI extension manager poisoned");
        data.installed = next;
        data.jobs.remove(id);
        Ok(())
    }

    async fn install_remote(
        &self,
        extension: &ExtensionDefinition,
        asset: &ExtensionAsset,
    ) -> Result<(), String> {
        // Explicitly incompatible installations must wait even during download.
        if self.runtime_state() == "waiting_update" {
            if let Some(lifecycle) = self.lifecycle() {
                lifecycle.gateway.finish_extension_maintenance(true);
                lifecycle.set_state("waiting_update").await?;
            }
        }
        let archive = self.download_dir.join(format!(
            "{}-{}-{}.tar.gz.part",
            extension.id,
            self.platform_key,
            asset.sha256.to_ascii_lowercase()
        ));
        let mut offset = fs::metadata(&archive).map(|item| item.len()).unwrap_or(0);
        if offset > 0
            && asset.size.map(|size| offset >= size).unwrap_or(true)
            && sha256_file(&archive)?.eq_ignore_ascii_case(&asset.sha256)
        {
            // A previous attempt may have failed while draining, after a full
            // download. Reuse the verified archive rather than requesting EOF.
            return self.install_downloaded(extension, asset, &archive).await;
        }
        let client = reqwest::Client::new();
        let mut request = client
            .get(&asset.url)
            .timeout(std::time::Duration::from_secs(30 * 60));
        if offset > 0 {
            request = request.header(reqwest::header::RANGE, format!("bytes={offset}-"));
        }
        let Some(response) = self.until_paused(&extension.id, request.send()).await else {
            return Ok(());
        };
        let response = response.map_err(|error| format!("下载 AI 扩展包失败：{error}"))?;
        if self.job_status(&extension.id).as_deref() == Some("paused") {
            return Ok(());
        }
        if !response.status().is_success() {
            if response.status() == reqwest::StatusCode::RANGE_NOT_SATISFIABLE {
                let _ = fs::remove_file(&archive);
            }
            return Err(format!("扩展包下载返回 HTTP {}", response.status()));
        }
        if offset > 0 && response.status() == reqwest::StatusCode::OK {
            offset = 0;
            let _ = fs::remove_file(&archive);
        }
        if offset > 0 && response.status() == reqwest::StatusCode::PARTIAL_CONTENT {
            let range = response
                .headers()
                .get(reqwest::header::CONTENT_RANGE)
                .and_then(|v| v.to_str().ok())
                .unwrap_or("");
            if !range.starts_with(&format!("bytes {offset}-")) {
                let _ = fs::remove_file(&archive);
                return Err("下载服务器返回错误的断点范围，请重试".into());
            }
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
        while let Some(chunk) = self
            .until_paused(&extension.id, stream.next())
            .await
            .flatten()
        {
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
        drop(output);
        if self.job_status(&extension.id).as_deref() == Some("paused") {
            return Ok(());
        }
        self.install_downloaded(extension, asset, &archive).await
    }

    async fn install_downloaded(
        &self,
        extension: &ExtensionDefinition,
        asset: &ExtensionAsset,
        archive: &Path,
    ) -> Result<(), String> {
        self.set_job_status(&extension.id, "verifying");
        let actual = sha256_file(&archive)?;
        if !actual.eq_ignore_ascii_case(&asset.sha256) {
            let _ = fs::remove_file(&archive);
            return Err(format!(
                "SHA-256 校验失败：期望 {}，实际 {actual}",
                asset.sha256
            ));
        }
        let temp = match self.extract_archive(archive) {
            Ok(temp) => temp,
            Err(error) => {
                let _ = fs::remove_file(archive);
                return Err(error);
            }
        };
        let validation = (|| {
            let manifest = read_json::<ExtensionManifest>(&temp.join("manifest.json"))?;
            if manifest.id != extension.id || manifest.version != extension.version {
                return Err("归档 ID 或版本与下载清单不匹配".into());
            }
            self.validate_manifest(&manifest, &temp)?;
            let data = self.data.lock().expect("AI extension manager poisoned");
            if let Some(current) = data
                .catalog
                .extensions
                .iter()
                .find(|e| e.id == extension.id)
            {
                let proposed = InstalledExtension {
                    id: manifest.id.clone(),
                    version: manifest.version.clone(),
                    platform: manifest.platform.clone(),
                    capabilities: manifest.capabilities.clone(),
                    entrypoint: manifest.entrypoint.clone(),
                    model_path: manifest.model_path.clone(),
                    checksum: actual.clone(),
                    installed_at: now_string(),
                };
                if compatibility(
                    current,
                    Some(&proposed),
                    data.server_requirements.as_ref(),
                    &self.platform_key,
                    data.catalog_error.is_some(),
                )
                .required
                {
                    return Err("下载的扩展低于 Server 最低支持版本".into());
                }
            }
            Ok::<_, String>(())
        })();
        if let Err(error) = validation {
            let _ = fs::remove_file(archive);
            let _ = fs::remove_dir_all(&temp);
            return Err(error);
        }
        let result = async {
            self.set_job_status(&extension.id, "draining");
            if let Some(lifecycle) = self.lifecycle() {
                lifecycle.begin().await?;
            }
            let manager = self.clone();
            let directory = temp.clone();
            let id = extension.id.clone();
            tauri::async_runtime::spawn_blocking(move || {
                manager.activate_extracted(&id, &directory, &actual)
            })
            .await
            .map_err(|e| e.to_string())?
        }
        .await;
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
            if let Some(link) = entry.link_name().map_err(|e| e.to_string())? {
                // PyInstaller uses relative links for shared libraries.
                if link.components().any(|part| {
                    matches!(
                        part,
                        Component::ParentDir | Component::RootDir | Component::Prefix(_)
                    )
                }) {
                    let _ = fs::remove_dir_all(&temp);
                    return Err("扩展包包含不安全链接".into());
                }
            }
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

    async fn until_paused<T>(
        &self,
        id: &str,
        future: impl std::future::Future<Output = T>,
    ) -> Option<T> {
        tokio::pin!(future);
        loop {
            if self.job_status(id).as_deref() == Some("paused") {
                return None;
            }
            tokio::select! {
                result = &mut future => return Some(result),
                _ = self.pause_signal.notified() => {},
            }
        }
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
        self.validate_manifest(&manifest, temp)?;
        safe_child_path(&self.root, id)?;
        let destination = self.root.join(id);
        let backup = self.root.join(format!("{id}.old"));
        let previous = self
            .data
            .lock()
            .expect("AI extension manager poisoned")
            .installed
            .clone();
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
        let mut next = previous.clone();
        next.insert(id.to_string(), installed.clone());
        // An interrupted replacement always rolls back on the next launch.
        let transaction = self.root.join("transaction.json");
        if backup.exists() {
            fs::remove_dir_all(&backup).map_err(|e| e.to_string())?;
        }
        fs::write(
            &transaction,
            serde_json::to_vec(&json!({ "id": id, "previous": previous,
            "hadDestination": destination.exists() }))
            .map_err(|e| e.to_string())?,
        )
        .map_err(|e| e.to_string())?;
        let result = (|| {
            if destination.exists() {
                fs::rename(&destination, &backup).map_err(|e| e.to_string())?;
            }
            fs::rename(temp, &destination).map_err(|e| format!("启用 AI 扩展包失败：{e}"))?;
            self.save_state(&next)?;
            fs::remove_file(&transaction).map_err(|e| e.to_string())?;
            Ok::<_, String>(())
        })();
        if let Err(error) = result {
            recover_transaction(&self.root, &self.state_path)?;
            return Err(error);
        }
        let _ = fs::remove_dir_all(backup);
        let mut data = self.data.lock().expect("AI extension manager poisoned");
        data.installed = next;
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
        Ok(installed)
    }

    fn validate_manifest(&self, manifest: &ExtensionManifest, temp: &Path) -> Result<(), String> {
        if manifest.platform != self.platform_key {
            return Err(format!("扩展包平台不匹配：{}", manifest.platform));
        }
        if version(&manifest.version).is_none() || manifest.capabilities.is_empty() {
            return Err("扩展包 manifest 缺少版本或能力列表".into());
        }
        let entrypoint = safe_child_path(temp, &manifest.entrypoint)?;
        if !entrypoint.is_file() {
            return Err("扩展包入口文件无效".into());
        }
        if let Some(model_path) = manifest.model_path.as_deref() {
            safe_child_path(temp, model_path)?;
            return Err("模型必须存储在独立模型目录，不能随扩展替换".into());
        }
        Ok(())
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

fn recover_transaction(root: &Path, state_path: &Path) -> Result<(), String> {
    let journal = root.join("transaction.json");
    if !journal.exists() {
        return Ok(());
    }
    let transaction: Value = read_json(&journal)?;
    let id = transaction["id"].as_str().ok_or("扩展恢复记录缺少 ID")?;
    validate_id(id)?;
    let target = safe_child_path(root, id)?;
    let backup = safe_child_path(root, &format!("{id}.old"))?;
    if backup.exists() {
        if target.exists() {
            fs::remove_dir_all(&target).map_err(|e| e.to_string())?;
        }
        fs::rename(backup, target).map_err(|e| e.to_string())?;
    } else if transaction["hadDestination"] == false && target.exists() {
        fs::remove_dir_all(target).map_err(|e| e.to_string())?;
    }
    fs::write(
        state_path,
        serde_json::to_vec_pretty(&json!({ "schemaVersion": 1,
        "extensions": transaction["previous"] }))
        .map_err(|e| e.to_string())?,
    )
    .map_err(|e| e.to_string())?;
    fs::remove_file(journal).map_err(|e| e.to_string())
}

fn validate_id(id: &str) -> Result<(), String> {
    if id.is_empty()
        || !id
            .bytes()
            .all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == b'-')
    {
        return Err("扩展包 ID 无效".into());
    }
    Ok(())
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

    fn installed(version: &str) -> InstalledExtension {
        InstalledExtension {
            id: "core-ai".into(),
            version: version.into(),
            platform: "win32-x64".into(),
            capabilities: vec!["ocr".into()],
            entrypoint: "runtime/ai".into(),
            model_path: None,
            checksum: String::new(),
            installed_at: String::new(),
        }
    }

    fn definition() -> ExtensionDefinition {
        serde_json::from_value(json!({"id":"core-ai", "name":"AI", "version":"0.18.0", "description":"test",
            "releases": [
                {"version":"0.17.2", "clientRange":">=0.17.0, <0.18.0", "assets":{}},
                {"version":"0.17.10", "clientRange":">=0.17.0, <0.18.0", "assets":{"win32-x64":{
                    "url":"https://github.com/LC044/TrailSnap/releases/download/ai-v0.17.10/ai.tar.gz", "sha256":"a".repeat(64)}}},
                {"version":"0.18.0", "clientRange":">=0.18.0, <0.19.0", "assets":{"win32-x64":{
                    "url":"https://github.com/LC044/TrailSnap/releases/download/ai-v0.18.0/ai.tar.gz", "sha256":"b".repeat(64)}}}
            ]})).unwrap()
    }

    fn requirements(server: &str, minimum: &str) -> ServerRequirements {
        ServerRequirements {
            server_version: server.into(),
            minimum_ai_extension_version: minimum.into(),
        }
    }

    #[test]
    fn installed_at_or_above_server_minimum_keeps_running_without_update() {
        let definition = definition();
        let requirement = requirements("0.17.10", "0.17.2");
        for current in [
            "0.17.2",
            "0.17.3",
            "0.17.10",
            "0.17.11",
            "0.18.0",
            "0.17.2+build.5",
        ] {
            for catalog_failed in [false, true] {
                let result = compatibility(
                    &definition,
                    Some(&installed(current)),
                    Some(&requirement),
                    "win32-x64",
                    catalog_failed,
                );
                assert_eq!(result.status, "compatible");
                assert!(result.runnable && !result.required && result.target.is_none());
            }
        }
        assert!(version("0.17.10")
            .unwrap()
            .cmp_precedence(&version("0.17.2").unwrap())
            .is_gt());
    }

    #[test]
    fn below_minimum_selects_exact_server_release_and_never_installs_for_missing_user() {
        let definition = definition();
        let requirement = requirements("0.17.10", "0.17.3");
        for current in ["0.17.2", "0.17.3-beta.1"] {
            let result = compatibility(
                &definition,
                Some(&installed(current)),
                Some(&requirement),
                "win32-x64",
                false,
            );
            assert!(result.required && !result.runnable);
            assert_eq!(result.target.unwrap().version, "0.17.10");
        }
        let missing = compatibility(&definition, None, Some(&requirement), "win32-x64", false);
        assert!(!missing.required);
        assert_eq!(missing.status, "not_installed");
        for (server, platform, failed) in [
            ("0.17.10", "linux-x64", false),
            ("0.17.4", "win32-x64", false),
            ("0.17.10", "win32-x64", true),
        ] {
            let result = compatibility(
                &definition,
                Some(&installed("0.17.2")),
                Some(&requirements(server, "0.17.3")),
                platform,
                failed,
            );
            assert!(result.required && !result.runnable && result.target.is_none());
        }
    }

    #[test]
    fn published_legacy_catalog_works_without_remote_compatibility_rules() {
        let mut definition = definition();
        definition.version = "0.17.10".into();
        definition.assets = definition.releases[1].assets.clone();
        definition.releases.clear();
        let requirement = requirements("0.17.10", "0.17.3");
        let result = compatibility(
            &definition,
            Some(&installed("0.17.2")),
            Some(&requirement),
            "win32-x64",
            false,
        );
        assert!(result.required);
        assert_eq!(result.target.unwrap().version, "0.17.10");
        let unknown = compatibility(
            &definition,
            Some(&installed("0.17.2")),
            None,
            "win32-x64",
            false,
        );
        assert!(unknown.runnable && !unknown.required && unknown.target.is_none());
        let metadata: ServerRequirements = serde_json::from_value(
            json!({"serverVersion":"0.17.10", "minimumAIExtensionVersion":"0.17.3"}),
        )
        .unwrap();
        assert_eq!(metadata.minimum_ai_extension_version, "0.17.3");
    }

    fn fixture(label: &str) -> (AIExtensionManager, PathBuf) {
        let root = std::env::temp_dir().join(format!(
            "trailsnap-extension-{label}-{}",
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        fs::create_dir_all(&root).unwrap();
        let catalog = root.join("catalog.json");
        fs::write(
            &catalog,
            serde_json::to_vec(&json!({"extensions":[{
                "id":"core-ai", "name":"AI", "version":"0.17.3", "description":"test"
            }]}))
            .unwrap(),
        )
        .unwrap();
        (
            AIExtensionManager::initialize(&root, &catalog, String::new()).unwrap(),
            root,
        )
    }

    fn archive_bytes(version: &str, runtime: &[u8]) -> Vec<u8> {
        let mut bundle = tar::Builder::new(GzEncoder::new(Vec::new(), Compression::default()));
        let manifest = serde_json::to_vec(&json!({"id":"core-ai", "version":version,
            "platform":platform_key(), "capabilities":["ocr"], "entrypoint":"runtime/ai"}))
        .unwrap();
        for (name, bytes) in [
            ("manifest.json", manifest.as_slice()),
            ("runtime/ai", runtime),
        ] {
            let mut header = tar::Header::new_gnu();
            header.set_size(bytes.len() as u64);
            header.set_mode(0o755);
            header.set_cksum();
            bundle.append_data(&mut header, name, bytes).unwrap();
        }
        bundle.into_inner().unwrap().finish().unwrap()
    }

    #[test]
    fn failed_state_write_rolls_back_files_and_installation_record() {
        let (manager, root) = fixture("rollback");
        let archive = root.join("ai.tar.gz");
        fs::write(&archive, archive_bytes("0.17.3", b"old")).unwrap();
        manager.import_archive(&archive).unwrap();
        fs::write(&archive, archive_bytes("0.17.4", b"new")).unwrap();
        fs::create_dir(manager.state_path.with_extension("json.tmp")).unwrap();
        assert!(manager.import_archive(&archive).is_err());
        assert_eq!(
            fs::read(manager.root.join("core-ai/runtime/ai")).unwrap(),
            b"old"
        );
        assert_eq!(manager.installed_for_ai().unwrap().0.version, "0.17.3");
        assert_eq!(
            read_json::<InstalledState>(&manager.state_path)
                .unwrap()
                .extensions["core-ai"]
                .version,
            "0.17.3"
        );
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn interrupted_replacement_recovers_previous_runtime_on_launch() {
        let (manager, root) = fixture("restart");
        let archive = root.join("ai.tar.gz");
        fs::write(&archive, archive_bytes("0.17.3", b"old")).unwrap();
        manager.import_archive(&archive).unwrap();
        let previous = manager.data.lock().unwrap().installed.clone();
        fs::write(
            manager.root.join("transaction.json"),
            serde_json::to_vec(&json!({
            "id":"core-ai", "previous":previous, "hadDestination":true}))
            .unwrap(),
        )
        .unwrap();
        fs::rename(
            manager.root.join("core-ai"),
            manager.root.join("core-ai.old"),
        )
        .unwrap();
        fs::create_dir_all(manager.root.join("core-ai/runtime")).unwrap();
        fs::write(
            manager.root.join("core-ai/runtime/ai"),
            b"partial new installation",
        )
        .unwrap();
        let restored =
            AIExtensionManager::initialize(&root, &root.join("catalog.json"), String::new())
                .unwrap();
        assert_eq!(restored.installed_for_ai().unwrap().0.version, "0.17.3");
        assert_eq!(
            fs::read(restored.root.join("core-ai/runtime/ai")).unwrap(),
            b"old"
        );
        assert!(!restored.root.join("transaction.json").exists());
        fs::remove_dir_all(root).unwrap();
    }

    #[tokio::test]
    async fn concurrent_mutations_are_rejected_before_touching_runtime() {
        let (manager, root) = fixture("mutex");
        let guard = manager.acquire_operation().unwrap();
        assert!(manager.start_install("core-ai").is_err());
        assert!(manager
            .import_archive_safely(root.join("ai.tar.gz"))
            .await
            .is_err());
        assert!(manager.uninstall_safely("core-ai").await.is_err());
        drop(guard);
        assert!(!manager.has_active_installs());
        fs::remove_dir_all(root).unwrap();
    }

    async fn download_server(bytes: Vec<u8>) -> (String, tokio::task::JoinHandle<()>) {
        let listener = tokio::net::TcpListener::bind(("127.0.0.1", 0))
            .await
            .unwrap();
        let address = listener.local_addr().unwrap();
        let app = axum::Router::new().fallback(axum::routing::get(move || {
            let bytes = bytes.clone();
            async move { bytes }
        }));
        let task = tokio::spawn(async move {
            axum::serve(listener, app).await.unwrap();
        });
        (format!("http://{address}/ai.tar.gz"), task)
    }

    #[tokio::test]
    async fn download_ignores_old_partial_and_checks_archive_version() {
        let (manager, root) = fixture("download");
        let bytes = archive_bytes("0.17.4", b"new");
        let (url, server) = download_server(bytes.clone()).await;
        let asset = ExtensionAsset {
            url,
            sha256: format!("{:x}", Sha256::digest(&bytes)),
            ..Default::default()
        };
        let extension = ExtensionDefinition {
            id: "core-ai".into(),
            version: "0.17.4".into(),
            ..Default::default()
        };
        fs::write(
            manager
                .download_dir
                .join(format!("core-ai-{}.tar.gz.part", platform_key())),
            b"old residual content",
        )
        .unwrap();
        let keyed = manager.download_dir.join(format!(
            "core-ai-{}-{}.tar.gz.part",
            platform_key(),
            asset.sha256
        ));
        fs::write(&keyed, &bytes[..bytes.len() / 2]).unwrap();
        manager.install_remote(&extension, &asset).await.unwrap();
        assert_eq!(manager.installed_for_ai().unwrap().0.version, "0.17.4");
        assert!(!keyed.exists());
        let incorrect = ExtensionDefinition {
            version: "0.17.5".into(),
            ..extension
        };
        assert!(manager
            .install_remote(&incorrect, &asset)
            .await
            .unwrap_err()
            .contains("版本"));
        assert_eq!(manager.installed_for_ai().unwrap().0.version, "0.17.4");
        server.abort();
        fs::remove_dir_all(root).unwrap();
    }

    #[tokio::test]
    async fn complete_verified_download_is_reused_without_requesting_eof_range() {
        let (manager, root) = fixture("cached-download");
        let bytes = archive_bytes("0.17.4", b"new");
        let asset = ExtensionAsset {
            url: "https://127.0.0.1:1/unreachable.tar.gz".into(),
            sha256: format!("{:x}", Sha256::digest(&bytes)),
            size: Some(bytes.len() as u64),
            ..Default::default()
        };
        let extension = ExtensionDefinition {
            id: "core-ai".into(),
            version: "0.17.4".into(),
            ..Default::default()
        };
        let cached = manager.download_dir.join(format!(
            "core-ai-{}-{}.tar.gz.part",
            platform_key(),
            asset.sha256
        ));
        fs::write(&cached, bytes).unwrap();
        manager.install_remote(&extension, &asset).await.unwrap();
        assert_eq!(manager.installed_for_ai().unwrap().0.version, "0.17.4");
        assert!(!cached.exists());
        fs::remove_dir_all(root).unwrap();
    }

    #[tokio::test]
    async fn corrupt_download_is_deleted_and_old_install_survives() {
        let (manager, root) = fixture("checksum");
        let archive = root.join("ai.tar.gz");
        fs::write(&archive, archive_bytes("0.17.3", b"old")).unwrap();
        manager.import_archive(&archive).unwrap();
        let (url, server) = download_server(b"corrupt bytes".to_vec()).await;
        let asset = ExtensionAsset {
            url,
            sha256: "a".repeat(64),
            ..Default::default()
        };
        let extension = ExtensionDefinition {
            id: "core-ai".into(),
            version: "0.17.4".into(),
            ..Default::default()
        };
        assert!(manager
            .install_remote(&extension, &asset)
            .await
            .unwrap_err()
            .contains("SHA-256"));
        let keyed = manager.download_dir.join(format!(
            "core-ai-{}-{}.tar.gz.part",
            platform_key(),
            asset.sha256
        ));
        assert!(!keyed.exists());
        assert_eq!(
            fs::read(manager.root.join("core-ai/runtime/ai")).unwrap(),
            b"old"
        );
        server.abort();
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn child_path_rejects_traversal_and_absolute_paths() {
        let root = Path::new("C:/safe");
        assert!(safe_child_path(root, "runtime/trailsnap-ai.exe").is_ok());
        assert!(safe_child_path(root, "../escape.exe").is_err());
        assert!(safe_child_path(root, "/escape.exe").is_err());
    }

    #[tokio::test]
    async fn stalled_download_pauses_without_waiting_for_another_chunk() {
        let (manager, root) = fixture("pause");
        manager.data.lock().unwrap().jobs.insert(
            "core-ai".into(),
            InstallJob {
                id: "core-ai".into(),
                status: "downloading".into(),
                received: 0,
                total: None,
                progress: 0,
                error: None,
                updated_at: now_string(),
            },
        );
        let copy = manager.clone();
        let waiting = tokio::spawn(async move {
            copy.until_paused("core-ai", std::future::pending::<()>())
                .await
        });
        tokio::task::yield_now().await;
        manager.pause("core-ai").unwrap();
        assert!(
            tokio::time::timeout(std::time::Duration::from_secs(1), waiting)
                .await
                .unwrap()
                .unwrap()
                .is_none()
        );
        fs::remove_dir_all(root).unwrap();
    }

    #[tokio::test]
    async fn server_minimum_is_the_only_auto_update_trigger_and_exact_target_is_attempted_once() {
        let (manager, root) = fixture("automatic");
        let mut extension = definition();
        // Refused loopback TLS connection fails deterministically without a live Release.
        extension.releases[1].assets.insert(
            platform_key(),
            ExtensionAsset {
                url: "https://127.0.0.1:1/unavailable".into(),
                sha256: "a".repeat(64),
                ..Default::default()
            },
        );
        {
            let mut data = manager.data.lock().unwrap();
            data.catalog.extensions = vec![extension];
            data.installed.insert("core-ai".into(), installed("0.17.2"));
            data.server_requirements = Some(requirements("0.17.10", "0.17.2"));
        }
        manager.reconcile().await.unwrap();
        assert!(manager.data.lock().unwrap().jobs.is_empty());
        manager.data.lock().unwrap().server_requirements = Some(requirements("0.17.10", "0.17.3"));
        manager.reconcile().await.unwrap();
        tokio::time::timeout(std::time::Duration::from_secs(3), async {
            while manager.has_active_installs() {
                tokio::time::sleep(std::time::Duration::from_millis(10)).await;
            }
        })
        .await
        .unwrap();
        assert_eq!(manager.job_status("core-ai").as_deref(), Some("failed"));
        let failed_at = manager.job_value("core-ai")["updatedAt"].clone();
        manager.reconcile().await.unwrap();
        assert_eq!(manager.job_value("core-ai")["updatedAt"], failed_at);
        assert_eq!(manager.data.lock().unwrap().auto_attempted.len(), 1);
        manager.data.lock().unwrap().installed.clear();
        manager.data.lock().unwrap().jobs.clear();
        manager.reconcile().await.unwrap();
        assert!(manager.data.lock().unwrap().jobs.is_empty());
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn installed_equal_version_keeps_manual_download_without_online_reinstall() {
        let (manager, root) = fixture("manual");
        let mut extension = definition();
        extension.releases[1].assets.insert(
            platform_key(),
            ExtensionAsset {
                url: "https://github.com/LC044/TrailSnap/releases/download/ai-v0.17.10/ai.tar.gz"
                    .into(),
                sha256: "a".repeat(64),
                ..Default::default()
            },
        );
        let mut data = manager.data.lock().unwrap();
        data.catalog.extensions = vec![extension];
        data.server_requirements = Some(requirements("0.17.10", "0.17.3"));
        data.installed
            .insert("core-ai".into(), installed("0.17.10"));
        drop(data);
        let snapshot = manager.list();
        assert_eq!(snapshot["extensions"][0]["compatibility"], "compatible");
        assert_eq!(snapshot["extensions"][0]["available"], false);
        assert!(snapshot["extensions"][0]["updateVersion"].is_null());
        assert!(snapshot["extensions"][0]["downloadUrl"].is_string());
        assert!(manager.start_install("core-ai").is_err());
        fs::remove_dir_all(root).unwrap();
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
                "version": "0.17.3",
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
                    "version": "0.17.3",
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
