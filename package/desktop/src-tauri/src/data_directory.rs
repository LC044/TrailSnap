use serde::{Deserialize, Serialize};
use std::{
    fs,
    path::{Component, Path, PathBuf},
    sync::Mutex,
};
use tauri::Manager;

#[derive(Clone, Default, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
struct DirectoryConfig {
    root: PathBuf,
    pending_root: Option<PathBuf>,
    previous_root: Option<PathBuf>,
    migration_error: Option<String>,
    #[serde(default)]
    server_port: Option<u16>,
    #[serde(default)]
    fixed_port: bool,
}

#[derive(Default, Serialize)]
#[serde(rename_all = "camelCase")]
struct PortRuntime {
    active_port: Option<u16>,
    error: Option<String>,
    notice: Option<String>,
}

pub fn port_error(port: u16, error: &std::io::Error) -> String {
    let reason = match error.kind() {
        std::io::ErrorKind::AddrInUse => "已被其他程序占用",
        std::io::ErrorKind::PermissionDenied => "被系统拒绝访问，可能属于保留端口或受到权限限制",
        _ => "无法监听",
    };
    format!("手机连接端口 {port} {reason}：{error}。请修改端口或切换为自动选择。")
}

pub fn retry_port_start(fixed: bool, attempt: usize, code: Option<&str>) -> bool {
    !fixed && attempt < 2 && code == Some("port_bind_failed")
}

pub struct DataDirectory {
    #[cfg(windows)]
    _lock: Option<fs::File>,
    data_lock: Mutex<Option<fs::File>>,
    pub instance_root: Option<PathBuf>,
    config_path: PathBuf,
    default_root: PathBuf,
    config: Mutex<DirectoryConfig>,
    port_runtime: Mutex<PortRuntime>,
}

impl DataDirectory {
    pub fn load(app: &tauri::AppHandle) -> Result<Self, String> {
        #[cfg(windows)]
        let executable = std::env::current_exe().map_err(|e| e.to_string())?;
        #[cfg(windows)]
        let installation = crate::portable::instance_root_for_executable(&executable)?;
        #[cfg(not(windows))]
        let installation = app
            .path()
            .app_local_data_dir()
            .map_err(|e| e.to_string())?;
        let _ = app;
        Self::load_from_directory(installation, cfg!(windows))
    }

    fn load_from_directory(installation: PathBuf, windows_layout: bool) -> Result<Self, String> {
        let instance_root = (windows_layout && installation.join("instance.json").is_file())
            .then_some(installation.clone());
        let (config_path, default_root, config) = if let Some(root) = &instance_root {
            let instance = crate::portable::load_instance(root)?;
            let data = crate::portable::data_root(root, &instance)?;
            (
                root.join("instance.json"),
                data.clone(),
                DirectoryConfig {
                    root: data,
                    server_port: instance.server_port,
                    fixed_port: instance.fixed_port,
                    ..Default::default()
                },
            )
        } else {
            if windows_layout
                && (installation.join("portable.json").exists()
                    || installation.join("maintenance/initialized.json").exists())
            {
                return Err("当前安装目录缺少 instance.json，请恢复该配置文件后通过 TrailSnap.exe 启动，避免打开空图库".into());
            }
            // Only Windows uses the program-local layout. macOS/Linux retain
            // their existing OS user-data directory and sibling pointer.
            let pointer = if windows_layout {
                installation.join("TrailSnap-desktop.json")
            } else {
                installation.with_file_name("TrailSnap-desktop.json")
            };
            let default = if windows_layout {
                installation.join("userdata")
            } else {
                installation.clone()
            };
            let config = if pointer.exists() {
                let mut value: DirectoryConfig = crate::portable::read_json(&pointer)?;
                if value.root.is_relative() {
                    value.root = installation.join(&value.root);
                }
                if !value.root.is_dir() {
                    return Err("配置中的数据目录不可用，请检查磁盘".into());
                }
                value
            } else {
                fs::create_dir_all(&default)
                    .map_err(|e| format!("安装目录不可写，请移动到可写文件夹：{e}"))?;
                DirectoryConfig {
                    root: default.clone(),
                    ..Default::default()
                }
            };
            (pointer, default, config)
        };
        let data_lock =
            if instance_root.is_some() && crate::portable::verify_launcher(&config.root)? {
                None
            } else {
                Some(crate::portable::lock_directory(&config.root)?)
            };
        Ok(Self {
            #[cfg(windows)]
            _lock: None,
            data_lock: Mutex::new(data_lock),
            instance_root,
            config_path,
            default_root,
            config: Mutex::new(config),
            port_runtime: Mutex::new(PortRuntime::default()),
        })
    }

    pub fn root(&self) -> PathBuf {
        self.config
            .lock()
            .expect("data directory poisoned")
            .root
            .clone()
    }

    pub fn pending(&self) -> Option<PathBuf> {
        self.config
            .lock()
            .expect("data directory poisoned")
            .pending_root
            .clone()
    }

    pub fn server_port(&self, fresh: bool) -> Result<u16, String> {
        let result = self.select_server_port(fresh);
        self.port_runtime.lock().unwrap().error = result.as_ref().err().cloned();
        result
    }

    fn select_server_port(&self, fresh: bool) -> Result<u16, String> {
        let config = self.config.lock().expect("data directory poisoned");
        if let Some(port) = config.server_port.filter(|port| *port > 0) {
            if !fresh || config.fixed_port {
                match std::net::TcpListener::bind(("0.0.0.0", port)) {
                    Ok(_) => return Ok(port),
                    Err(error) if config.fixed_port => return Err(port_error(port, &error)),
                    Err(error) if matches!(error.kind(), std::io::ErrorKind::AddrInUse | std::io::ErrorKind::PermissionDenied) => {},
                    Err(error) => return Err(port_error(port, &error)),
                }
            }
        }
        let listener =
            std::net::TcpListener::bind(("0.0.0.0", 0)).map_err(|err| port_error(0, &err))?;
        let port = listener.local_addr().map_err(|err| err.to_string())?.port();
        Ok(port)
    }

    pub fn fixed_port(&self) -> bool {
        self.config.lock().unwrap().fixed_port
    }

    pub fn mark_port_error(&self, message: String) {
        self.port_runtime.lock().unwrap().error = Some(message);
    }

    pub fn commit_server_port(&self, port: u16) -> Result<(), String> {
        let mut config = self.config.lock().unwrap();
        let mut next = config.clone();
        next.server_port = Some(port);
        self.save(&next)?;
        let mut runtime = self.port_runtime.lock().unwrap();
        runtime.notice = config.server_port.filter(|old| *old != port).map(|old|
            format!("原连接端口 {old} 不可用，已切换为 {port}，手机请重新扫码连接。"));
        runtime.active_port = Some(port);
        runtime.error = None;
        *config = next;
        Ok(())
    }

    fn configure_port(&self, port: Option<u16>) -> Result<(), String> {
        if port == Some(0) { return Err("端口必须是 1–65535 的整数".into()); }
        let mut config = self.config.lock().unwrap();
        if let Some(port) = port {
            if self.port_runtime.lock().unwrap().active_port != Some(port) {
                std::net::TcpListener::bind(("0.0.0.0", port)).map_err(|e| port_error(port, &e))?;
            }
        }
        let mut next = config.clone();
        next.fixed_port = port.is_some();
        if port.is_some() { next.server_port = port; }
        self.save(&next)?;
        *config = next;
        Ok(())
    }

    pub fn authorize_migration(&self, target: &Path) -> Result<(), String> {
        let config = self.config.lock().expect("data directory poisoned");
        if config.pending_root.as_deref() != Some(target) {
            return Err("迁移目标已改变，请重新准备迁移".into());
        }
        fs::write(
            config.root.join(".desktop-migration-ready"),
            target.to_string_lossy().as_bytes(),
        )
        .map_err(|err| err.to_string())
    }

    pub fn consume_migration_authorization(&self) -> Result<bool, String> {
        let config = self.config.lock().expect("data directory poisoned");
        let marker = config.root.join(".desktop-migration-ready");
        let expected = config
            .pending_root
            .as_ref()
            .map(|path| path.to_string_lossy());
        let authorized = expected
            .as_deref()
            .is_some_and(|target| fs::read_to_string(&marker).ok().as_deref() == Some(target));
        if marker.exists() {
            fs::remove_file(marker).map_err(|err| err.to_string())?;
        }
        Ok(authorized)
    }

    fn save(&self, config: &DirectoryConfig) -> Result<(), String> {
        if let Some(root) = &self.instance_root {
            let mut instance = crate::portable::load_instance(root)?;
            instance.server_port = config.server_port;
            instance.fixed_port = config.fixed_port;
            instance.data_root = if let Ok(relative) = config.root.strip_prefix(root) {
                crate::portable::DataRoot {
                    kind: "relative".into(),
                    path: relative.to_path_buf(),
                }
            } else {
                crate::portable::DataRoot {
                    kind: "absolute".into(),
                    path: config.root.clone(),
                }
            };
            crate::portable::write_json(&root.join("instance.json"), &instance)?;
            return Ok(());
        }
        let temp = self.config_path.with_extension("json.tmp");
        let bytes = serde_json::to_vec_pretty(config).map_err(|err| err.to_string())?;
        fs::write(&temp, bytes).map_err(|err| format!("保存数据目录配置失败：{err}"))?;
        replace_config_file(&temp, &self.config_path)
            .map_err(|err| format!("保存数据目录配置失败：{err}"))
    }

    pub fn finish_migration(&self, result: Result<(), String>) -> Result<(), String> {
        let mut config = self.config.lock().expect("data directory poisoned");
        let mut next = config.clone();
        let mut next_lock = None;
        if let Some(target) = next.pending_root.take() {
            match result {
                Ok(()) => {
                    // Acquire the new library before publishing its pointer.
                    let lock = crate::portable::lock_directory(&target)?;
                    next_lock = Some(lock);
                    next.previous_root = Some(next.root.clone());
                    next.root = target;
                    next.migration_error = None;
                }
                Err(err) => next.migration_error = Some(err),
            }
            self.save(&next)?;
            if let Some(lock) = next_lock {
                *self.data_lock.lock().expect("data lock poisoned") = Some(lock);
            }
            *config = next;
        }
        Ok(())
    }
}

fn replace_config_file(source: &Path, target: &Path) -> std::io::Result<()> {
    match fs::rename(source, target) {
        Ok(()) => Ok(()),
        #[cfg(windows)]
        Err(err) if err.raw_os_error() == Some(17) => {
            use std::os::windows::ffi::OsStrExt;
            #[link(name = "kernel32")]
            extern "system" {
                fn MoveFileExW(source: *const u16, target: *const u16, flags: u32) -> i32;
            }
            let source: Vec<u16> = source.as_os_str().encode_wide().chain(Some(0)).collect();
            let target: Vec<u16> = target.as_os_str().encode_wide().chain(Some(0)).collect();
            // Encrypted AppData can report ERROR_NOT_SAME_DEVICE even for sibling
            // files. Let Windows copy when needed and flush before removing the
            // prepared file; other rename errors still fail without a fallback.
            let moved = unsafe { MoveFileExW(source.as_ptr(), target.as_ptr(), 1 | 2 | 8) };
            if moved == 0 {
                Err(std::io::Error::last_os_error())
            } else {
                Ok(())
            }
        }
        Err(err) => Err(err),
    }
}

fn canonical_directory(path: &Path) -> Result<PathBuf, String> {
    let path = path
        .canonicalize()
        .map_err(|err| format!("无法访问目录：{err}"))?;
    #[cfg(windows)]
    let path = {
        let value = path.to_string_lossy();
        if let Some(unc) = value.strip_prefix(r"\\?\UNC\") {
            PathBuf::from(format!(r"\\{unc}"))
        } else {
            PathBuf::from(value.trim_start_matches(r"\\?\"))
        }
    };
    Ok(path)
}

pub(crate) fn validate_target(source: &Path, target: &Path) -> Result<PathBuf, String> {
    if !target.is_absolute()
        || target
            .components()
            .any(|part| matches!(part, Component::ParentDir))
    {
        return Err("请输入不含 .. 的绝对目录路径".into());
    }
    let source = canonical_directory(source)?;
    let mut ancestor = target;
    let mut suffix = Vec::new();
    while !ancestor.exists() {
        suffix.push(ancestor.file_name().ok_or("目标目录无效")?.to_os_string());
        ancestor = ancestor.parent().ok_or("目标目录无效")?;
    }
    let mut target = canonical_directory(ancestor)?;
    for component in suffix.into_iter().rev() {
        target.push(component);
    }
    #[cfg(windows)]
    let (compare_source, compare_target) = (
        PathBuf::from(source.to_string_lossy().to_lowercase()),
        PathBuf::from(target.to_string_lossy().to_lowercase()),
    );
    #[cfg(not(windows))]
    let (compare_source, compare_target) = (source, target.clone());
    if compare_source.starts_with(&compare_target) || compare_target.starts_with(&compare_source) {
        return Err("新旧数据目录不能相同或互相包含".into());
    }
    fs::create_dir_all(&target).map_err(|err| format!("无法创建目标目录：{err}"))?;
    if fs::read_dir(&target)
        .map_err(|err| err.to_string())?
        .next()
        .is_some()
    {
        return Err("请选择空文件夹，避免覆盖已有文件".into());
    }
    let probe = target.join(".trailsnap-write-test");
    fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&probe)
        .map_err(|err| format!("目标目录不可写：{err}"))?;
    fs::remove_file(probe).map_err(|err| err.to_string())?;
    Ok(target)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::{SystemTime, UNIX_EPOCH};

    #[test]
    fn non_windows_keeps_user_data_and_existing_custom_pointer() {
        let root = std::env::temp_dir().join(uuid::Uuid::new_v4().to_string());
        let local_data = root.join("com.trailsnap.desktop");
        let state = DataDirectory::load_from_directory(local_data.clone(), false).unwrap();
        assert_eq!(state.root(), local_data);
        assert_eq!(state.config_path, root.join("TrailSnap-desktop.json"));
        assert!(state.instance_root.is_none());
        assert!(!local_data.join("userdata").exists());
        drop(state);
        let custom = root.join("custom-library");
        fs::create_dir_all(&custom).unwrap();
        crate::portable::write_json(
            &root.join("TrailSnap-desktop.json"),
            &DirectoryConfig {
                root: custom.clone(),
                server_port: Some(18900),
                ..Default::default()
            },
        ).unwrap();
        let state = DataDirectory::load_from_directory(local_data, false).unwrap();
        assert_eq!(state.root(), custom);
        assert_eq!(state.config.lock().unwrap().server_port, Some(18900));
        drop(state);
        fs::remove_dir_all(root).unwrap();
    }

    fn fixture() -> (PathBuf, DataDirectory) {
        let root = std::env::temp_dir().join(format!(
            "trailsnap-data-directory-{}",
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        let source = root.join("source");
        fs::create_dir_all(&source).unwrap();
        fs::create_dir_all(root.join("target")).unwrap();
        let state = DataDirectory {
            #[cfg(windows)]
            _lock: Some(fs::File::create(root.join("config.lock")).unwrap()),
            data_lock: Mutex::new(None),
            instance_root: None,
            config_path: root.join("config.json"),
            default_root: source.clone(),
            config: Mutex::new(DirectoryConfig {
                root: source,
                pending_root: Some(root.join("target")),
                ..Default::default()
            }),
            port_runtime: Mutex::new(PortRuntime::default()),
        };
        (root, state)
    }

    #[test]
    fn reject_overlap_relative_and_nonempty_without_overwriting() {
        let (root, state) = fixture();
        let source = state.root();
        assert!(validate_target(&source, &source).is_err());
        assert!(validate_target(&source, &source.join("child")).is_err());
        assert!(!source.join("child").exists());
        assert!(validate_target(&source, &root).is_err());
        assert!(validate_target(&source, Path::new("relative")).is_err());
        let target = root.join("target");
        fs::create_dir_all(&target).unwrap();
        fs::write(target.join("keep"), b"keep").unwrap();
        assert!(validate_target(&source, &target).is_err());
        assert_eq!(fs::read(target.join("keep")).unwrap(), b"keep");
    }

    #[test]
    fn accept_new_writable_directory() {
        let (root, state) = fixture();
        let target = validate_target(&state.root(), &root.join("new/target")).unwrap();
        assert!(target.is_dir());
        assert_eq!(fs::read_dir(target).unwrap().count(), 0);
    }

    #[test]
    fn success_persists_new_root_and_backup_in_existing_config() {
        let (root, state) = fixture();
        state.save(&state.config.lock().unwrap()).unwrap();
        state.finish_migration(Ok(())).unwrap();
        let saved: DirectoryConfig =
            serde_json::from_slice(&fs::read(&state.config_path).unwrap()).unwrap();
        assert_eq!(saved.root, root.join("target"));
        assert_eq!(saved.previous_root, Some(root.join("source")));
        assert!(saved.pending_root.is_none());
        assert_eq!(state.root(), saved.root);
    }

    #[test]
    fn failed_migration_retains_old_root_and_records_error() {
        let (root, state) = fixture();
        state.finish_migration(Err("disk full".into())).unwrap();
        assert_eq!(state.root(), root.join("source"));
        assert!(state.pending().is_none());
        assert_eq!(
            state.config.lock().unwrap().migration_error.as_deref(),
            Some("disk full")
        );
    }

    #[test]
    fn failed_config_save_does_not_switch_in_memory_root() {
        let (root, state) = fixture();
        fs::create_dir(&state.config_path).unwrap();
        assert!(state.finish_migration(Ok(())).is_err());
        assert_eq!(state.root(), root.join("source"));
        assert_eq!(state.pending(), Some(root.join("target")));
    }

    #[test]
    fn automatic_port_is_committed_only_after_health_check_and_recovers_conflicts() {
        let (_root, state) = fixture();
        let port = state.server_port(false).unwrap();
        assert!(!state.config_path.exists());
        assert_eq!(state.config.lock().unwrap().server_port, None);
        state.commit_server_port(port).unwrap();
        let saved: DirectoryConfig =
            serde_json::from_slice(&fs::read(&state.config_path).unwrap()).unwrap();
        assert_eq!(saved.server_port, Some(port));
        let occupied = std::net::TcpListener::bind(("0.0.0.0", port)).unwrap();
        let replacement = state.server_port(false).unwrap();
        assert_ne!(replacement, port);
        assert_eq!(state.config.lock().unwrap().server_port, Some(port));
        state.commit_server_port(replacement).unwrap();
        assert!(state.port_runtime.lock().unwrap().notice.is_some());
        drop(occupied);
        assert_eq!(state.server_port(false).unwrap(), replacement);
    }

    #[test]
    fn fixed_port_conflict_can_be_recovered_without_server() {
        let (_root, state) = fixture();
        let port = state.server_port(false).unwrap();
        state.configure_port(Some(port)).unwrap();
        let occupied = std::net::TcpListener::bind(("0.0.0.0", port)).unwrap();
        assert!(state.server_port(false).unwrap_err().contains("占用"));
        assert!(state.port_runtime.lock().unwrap().error.is_some());
        assert!(state.configure_port(Some(0)).is_err());
        state.configure_port(None).unwrap();
        assert_ne!(state.server_port(false).unwrap(), port);
        let saved: DirectoryConfig = crate::portable::read_json(&state.config_path).unwrap();
        assert!(!saved.fixed_port);
        drop(occupied);
    }

    #[test]
    fn portable_port_preferences_survive_reload_without_changing_library_identity() {
        let (root, mut state) = fixture();
        crate::portable::write_json(&root.join("instance.json"), &serde_json::json!({
            "schemaVersion":1,"mode":"portable","instanceId":"port-test","displayName":"test",
            "activeBuild":"original","previousBuild":null,
            "dataRoot":{"kind":"relative","path":"source"},"serverPort":null,"fixedPort":false
        })).unwrap();
        state.instance_root = Some(root.clone());
        let port = state.server_port(false).unwrap();
        state.configure_port(Some(port)).unwrap();
        let saved = crate::portable::load_instance(&root).unwrap();
        assert!(saved.fixed_port);
        assert_eq!(saved.server_port, Some(port));
        assert_eq!(saved.instance_id, "port-test");
        assert_eq!(saved.active_build, "original");
        drop(state);
        let reloaded = DataDirectory::load_from_directory(root.clone(), true).unwrap();
        assert!(reloaded.fixed_port());
        assert_eq!(reloaded.server_port(false).unwrap(), port);
        reloaded.configure_port(None).unwrap();
        assert!(!crate::portable::load_instance(&root).unwrap().fixed_port);
        drop(reloaded);
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn port_error_and_retry_policy_distinguish_permission_and_non_port_failures() {
        assert!(port_error(2688, &std::io::Error::from(std::io::ErrorKind::PermissionDenied)).contains("保留端口"));
        assert!(port_error(2688, &std::io::Error::from(std::io::ErrorKind::AddrInUse)).contains("占用"));
        assert!(retry_port_start(false, 0, Some("port_bind_failed")));
        assert!(retry_port_start(false, 1, Some("port_bind_failed")));
        assert!(!retry_port_start(false, 2, Some("port_bind_failed")));
        assert!(!retry_port_start(true, 0, Some("port_bind_failed")));
        assert!(!retry_port_start(false, 0, None));
        assert!(!retry_port_start(false, 0, Some("database_failed")));
    }

    #[test]
    fn migration_requires_single_use_authorization_for_the_saved_target() {
        let (root, state) = fixture();
        assert!(!state.consume_migration_authorization().unwrap());
        assert!(state.authorize_migration(&root.join("other")).is_err());
        state.authorize_migration(&root.join("target")).unwrap();
        assert!(state.consume_migration_authorization().unwrap());
        assert!(!state.consume_migration_authorization().unwrap());
        state.authorize_migration(&root.join("target")).unwrap();
        state.config.lock().unwrap().pending_root = Some(root.join("other"));
        assert!(!state.consume_migration_authorization().unwrap());
    }
}

#[tauri::command]
pub fn desktop_port_config(state: tauri::State<'_, DataDirectory>) -> serde_json::Value {
    let config = state.config.lock().unwrap();
    let runtime = state.port_runtime.lock().unwrap();
    serde_json::json!({"port":config.server_port,"fixed":config.fixed_port,
        "activePort":runtime.active_port,"error":runtime.error,"notice":runtime.notice})
}

#[tauri::command]
pub fn desktop_set_port(port: Option<u16>, app: tauri::AppHandle) -> Result<(), String> {
    let _activity = crate::begin_activity(&app)?;
    app.state::<DataDirectory>().configure_port(port)
}

#[tauri::command]
pub fn desktop_data_directory(state: tauri::State<'_, DataDirectory>) -> serde_json::Value {
    let config = state.config.lock().expect("data directory poisoned");
    serde_json::json!({
        "root": config.root,
        "defaultRoot": state.default_root,
        "pendingRoot": config.pending_root,
        "previousRoot": config.previous_root,
        "migrationError": config.migration_error,
        "mode": if state.instance_root.is_some() { "portable" } else { "legacy-installed" },
        "instanceRoot": state.instance_root,
        "portableSupported": cfg!(windows),
    })
}

#[tauri::command]
pub async fn desktop_set_data_directory(
    path: Option<String>,
    app: tauri::AppHandle,
) -> Result<(), String> {
    let _activity = crate::begin_activity(&app)?;
    if app.state::<DataDirectory>().instance_root.is_some() && path.is_some() {
        return Err("便携实例请安全退出后移动整个文件夹；数据位置将随文件夹自动更新".into());
    }
    tauri::async_runtime::spawn_blocking(move || {
        let state = app.state::<DataDirectory>();
        let mut config = state.config.lock().expect("data directory poisoned");
        let mut next = config.clone();
        next.pending_root = match path {
            Some(path) => Some(validate_target(&config.root, Path::new(path.trim()))?),
            None => None,
        };
        next.migration_error = None;
        // A changed destination invalidates any previous successful drain.
        let marker = config.root.join(".desktop-migration-ready");
        if marker.exists() {
            fs::remove_file(marker).map_err(|err| err.to_string())?;
        }
        state.save(&next)?;
        *config = next;
        Ok(())
    })
    .await
    .map_err(|err| err.to_string())?
}
