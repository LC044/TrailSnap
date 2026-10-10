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
}

pub struct DataDirectory {
    #[cfg(windows)]
    _lock: fs::File,
    config_path: PathBuf,
    default_root: PathBuf,
    config: Mutex<DirectoryConfig>,
}

impl DataDirectory {
    pub fn load(app: &tauri::AppHandle) -> Result<Self, String> {
        #[cfg(windows)]
        let default_root = std::env::var_os("LOCALAPPDATA")
            .map(|path| PathBuf::from(path).join("TrailSnap"))
            .ok_or_else(|| "无法读取 LOCALAPPDATA".to_string())?;
        #[cfg(not(windows))]
        let default_root = app
            .path()
            .app_local_data_dir()
            .map_err(|err| err.to_string())?;
        let _ = app;
        // This small pointer stays outside the directory being migrated.
        let config_path = default_root.with_file_name("TrailSnap-desktop.json");
        #[cfg(windows)]
        let directory_lock = {
            use std::os::windows::fs::OpenOptionsExt;
            let parent = config_path.parent().ok_or("无法确定配置目录")?;
            fs::create_dir_all(parent).map_err(|err| err.to_string())?;
            let mut attempts = 0;
            loop {
                match fs::OpenOptions::new()
                    .read(true)
                    .write(true)
                    .create(true)
                    .truncate(false)
                    .share_mode(0)
                    .open(config_path.with_extension("lock"))
                {
                    Ok(file) => break file,
                    // Relaunch spawns the replacement just before the old process exits.
                    Err(err) if err.raw_os_error() == Some(32) && attempts < 20 => {
                        attempts += 1;
                        std::thread::sleep(std::time::Duration::from_millis(100));
                    }
                    Err(err) => {
                        return Err(format!(
                            "无法锁定桌面数据目录，请确认其他行影集窗口已关闭：{err}"
                        ))
                    }
                }
            }
        };
        let config = if config_path.exists() {
            let config: DirectoryConfig =
                serde_json::from_slice(&fs::read(&config_path).map_err(|err| err.to_string())?)
                    .map_err(|err| format!("数据目录配置损坏：{err}"))?;
            if !config.root.is_absolute() || !config.root.is_dir() {
                return Err(format!(
                    "数据目录不可用，请检查磁盘：{}",
                    config.root.display()
                ));
            }
            config
        } else {
            DirectoryConfig {
                root: default_root.clone(),
                ..Default::default()
            }
        };
        Ok(Self {
            #[cfg(windows)]
            _lock: directory_lock,
            config_path,
            default_root,
            config: Mutex::new(config),
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

    pub fn server_port(&self) -> Result<u16, String> {
        let mut config = self.config.lock().expect("data directory poisoned");
        if let Some(port) = config.server_port.filter(|port| *port > 0) {
            std::net::TcpListener::bind(("0.0.0.0", port)).map_err(|err| {
                format!("手机连接端口 {port} 被占用，请关闭占用程序后重试：{err}")
            })?;
            return Ok(port);
        }
        let listener =
            std::net::TcpListener::bind(("0.0.0.0", 0)).map_err(|err| err.to_string())?;
        let port = listener.local_addr().map_err(|err| err.to_string())?.port();
        let mut next = config.clone();
        next.server_port = Some(port);
        self.save(&next)?;
        *config = next;
        Ok(port)
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
        let temp = self.config_path.with_extension("json.tmp");
        let bytes = serde_json::to_vec_pretty(config).map_err(|err| err.to_string())?;
        fs::write(&temp, bytes).map_err(|err| format!("保存数据目录配置失败：{err}"))?;
        replace_config_file(&temp, &self.config_path)
            .map_err(|err| format!("保存数据目录配置失败：{err}"))
    }

    pub fn finish_migration(&self, result: Result<(), String>) -> Result<(), String> {
        let mut config = self.config.lock().expect("data directory poisoned");
        let mut next = config.clone();
        if let Some(target) = next.pending_root.take() {
            match result {
                Ok(()) => {
                    next.previous_root = Some(next.root.clone());
                    next.root = target;
                    next.migration_error = None;
                }
                Err(err) => next.migration_error = Some(err),
            }
            self.save(&next)?;
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

fn validate_target(source: &Path, target: &Path) -> Result<PathBuf, String> {
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
        let state = DataDirectory {
            #[cfg(windows)]
            _lock: fs::File::create(root.join("config.lock")).unwrap(),
            config_path: root.join("config.json"),
            default_root: source.clone(),
            config: Mutex::new(DirectoryConfig {
                root: source,
                pending_root: Some(root.join("target")),
                ..Default::default()
            }),
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
    fn server_port_is_persisted_and_never_changed_when_occupied() {
        let (_root, state) = fixture();
        let port = state.server_port().unwrap();
        let saved: DirectoryConfig =
            serde_json::from_slice(&fs::read(&state.config_path).unwrap()).unwrap();
        assert_eq!(saved.server_port, Some(port));
        let occupied = std::net::TcpListener::bind(("0.0.0.0", port)).unwrap();
        assert!(state.server_port().is_err());
        assert_eq!(state.config.lock().unwrap().server_port, Some(port));
        drop(occupied);
        assert_eq!(state.server_port().unwrap(), port);
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
pub fn desktop_data_directory(state: tauri::State<'_, DataDirectory>) -> serde_json::Value {
    let config = state.config.lock().expect("data directory poisoned");
    serde_json::json!({
        "root": config.root,
        "defaultRoot": state.default_root,
        "pendingRoot": config.pending_root,
        "previousRoot": config.previous_root,
        "migrationError": config.migration_error,
    })
}

#[tauri::command]
pub async fn desktop_set_data_directory(
    path: Option<String>,
    app: tauri::AppHandle,
) -> Result<(), String> {
    let _activity = crate::begin_activity(&app)?;
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
