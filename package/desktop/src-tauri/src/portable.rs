//! Filesystem/instance primitives shared by the desktop shell and stable launcher.
use serde::{Deserialize, Serialize};
use std::{
    fs,
    io::{Read, Write},
    path::{Component, Path, PathBuf},
    time::Duration,
};

pub const LAUNCHER_VERSION: u32 = 2;

/// The executable layout is the only discovery mechanism. Ambient variables,
/// working directories and per-user OS configuration never select a library.
pub fn instance_root_for_executable(executable: &Path) -> Result<PathBuf, String> {
    let parent = executable.parent().ok_or("程序目录无效")?;
    let root = if parent
        .parent()
        .and_then(Path::file_name)
        .is_some_and(|name| name == "app")
    {
        parent
            .parent()
            .and_then(Path::parent)
            .ok_or("实例布局无效")?
    } else {
        parent
    };
    Ok(clean_path(root.canonicalize().map_err(|e| e.to_string())?))
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct DataRoot {
    pub kind: String,
    pub path: PathBuf,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct InstanceConfig {
    pub schema_version: u32,
    pub mode: String,
    pub instance_id: String,
    pub display_name: String,
    pub active_build: String,
    pub previous_build: Option<String>,
    pub data_root: DataRoot,
    #[serde(default)]
    pub server_port: Option<u16>,
    #[serde(default)]
    pub fixed_port: bool,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct BuildManifest {
    pub schema_version: u32,
    pub version: String,
    pub build_id: String,
    pub platform: String,
    pub min_launcher_version: u32,
    pub executable: String,
    #[serde(default, rename = "bundledAI")]
    pub bundled_ai: bool,
}

pub fn relative_path(value: &Path) -> Result<(), String> {
    if value.as_os_str().is_empty()
        || value.is_absolute()
        || value
            .components()
            .any(|part| !matches!(part, Component::Normal(_)))
    {
        return Err("路径必须是实例内的相对路径，不能包含 ..".into());
    }
    // Reject Windows prefixes even when validating on a Unix CI runner.
    if value.to_string_lossy().contains(':') || value.to_string_lossy().starts_with(['/', '\\']) {
        return Err("路径不能包含驱动器或网络根目录".into());
    }
    Ok(())
}

pub fn read_json<T: for<'de> Deserialize<'de>>(path: &Path) -> Result<T, String> {
    serde_json::from_slice(&fs::read(path).map_err(|e| format!("{}：{e}", path.display()))?)
        .map_err(|e| format!("配置损坏 {}：{e}", path.display()))
}

pub fn write_json<T: Serialize>(path: &Path, value: &T) -> Result<(), String> {
    let parent = path.parent().ok_or("配置路径无效")?;
    fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    let temp = path.with_extension("json.tmp");
    let mut file = fs::File::create(&temp).map_err(|e| e.to_string())?;
    file.write_all(&serde_json::to_vec_pretty(value).map_err(|e| e.to_string())?)
        .map_err(|e| e.to_string())?;
    file.sync_all().map_err(|e| e.to_string())?;
    replace_file(&temp, path)
}

pub fn replace_file(source: &Path, target: &Path) -> Result<(), String> {
    #[cfg(windows)]
    {
        use std::os::windows::ffi::OsStrExt;
        #[link(name = "kernel32")]
        unsafe extern "system" {
            fn MoveFileExW(a: *const u16, b: *const u16, flags: u32) -> i32;
        }
        let a: Vec<u16> = source.as_os_str().encode_wide().chain(Some(0)).collect();
        let b: Vec<u16> = target.as_os_str().encode_wide().chain(Some(0)).collect();
        if unsafe { MoveFileExW(a.as_ptr(), b.as_ptr(), 1 | 8) } == 0 {
            return Err(std::io::Error::last_os_error().to_string());
        }
        Ok(())
    }
    #[cfg(not(windows))]
    {
        fs::rename(source, target).map_err(|e| e.to_string())
    }
}

pub fn load_instance(root: &Path) -> Result<InstanceConfig, String> {
    let config: InstanceConfig = read_json(&root.join("instance.json"))?;
    if config.schema_version != 1 || config.mode != "portable" || config.instance_id.is_empty() {
        return Err("实例配置版本或发行模式不受支持".into());
    }
    relative_path(Path::new(&config.active_build))?;
    if Path::new(&config.active_build).components().count() != 1 {
        return Err("程序版本标识无效".into());
    }
    if config.data_root.kind == "relative" {
        relative_path(&config.data_root.path)?;
    } else if config.data_root.kind != "absolute" || !config.data_root.path.is_absolute() {
        return Err("数据目录配置无效".into());
    }
    Ok(config)
}

pub fn data_root(root: &Path, config: &InstanceConfig) -> Result<PathBuf, String> {
    let path = if config.data_root.kind == "relative" {
        root.join(&config.data_root.path)
    } else {
        config.data_root.path.clone()
    };
    if !path.is_dir() {
        return Err(format!("数据目录不可用，请检查磁盘：{}", path.display()));
    }
    let canonical = path.canonicalize().map_err(|e| e.to_string())?;
    if config.data_root.kind == "relative"
        && !canonical.starts_with(root.canonicalize().map_err(|e| e.to_string())?)
    {
        return Err("数据目录链接指向了实例外部".into());
    }
    Ok(clean_path(canonical))
}

pub fn clean_path(path: PathBuf) -> PathBuf {
    #[cfg(windows)]
    {
        let text = path.to_string_lossy();
        if let Some(unc) = text.strip_prefix(r"\\?\UNC\") {
            PathBuf::from(format!(r"\\{unc}"))
        } else {
            PathBuf::from(text.trim_start_matches(r"\\?\"))
        }
    }
    #[cfg(not(windows))]
    {
        path
    }
}

pub fn lock_directory(root: &Path) -> Result<fs::File, String> {
    let mut options = fs::OpenOptions::new();
    options.read(true).write(true).create(true).truncate(false);
    #[cfg(windows)]
    {
        use std::os::windows::fs::OpenOptionsExt;
        options.share_mode(0);
    }
    let path = root.join(".instance.lock");
    for attempt in 0..21 {
        match options.open(&path) {
            Ok(file) => {
                #[cfg(not(windows))]
                {
                    file.try_lock()
                        .map_err(|e| format!("图库正在被其他实例使用：{e}"))?;
                }
                return Ok(file);
            }
            Err(e) if attempt < 20 && e.raw_os_error() == Some(32) => {
                std::thread::sleep(Duration::from_millis(100))
            }
            Err(e) => return Err(format!("图库正在被其他实例使用或不可写：{e}")),
        }
    }
    unreachable!()
}

pub fn verify_launcher(root: &Path) -> Result<bool, String> {
    let Ok(port) = std::env::var("TS_LAUNCHER_LEASE_PORT") else {
        return Ok(false);
    };
    let token = std::env::var("TS_LAUNCHER_LEASE_TOKEN").map_err(|_| "启动器租约缺失")?;
    let port: u16 = port.parse().map_err(|_| "启动器租约端口无效")?;
    let mut socket = std::net::TcpStream::connect_timeout(
        &std::net::SocketAddr::from(([127, 0, 0, 1], port)),
        Duration::from_secs(2),
    )
    .map_err(|e| e.to_string())?;
    socket
        .set_read_timeout(Some(Duration::from_secs(2)))
        .map_err(|e| e.to_string())?;
    socket
        .write_all(format!("{token}\n").as_bytes())
        .map_err(|e| e.to_string())?;
    socket
        .shutdown(std::net::Shutdown::Write)
        .map_err(|e| e.to_string())?;
    let mut response = String::new();
    socket
        .take(32768)
        .read_to_string(&mut response)
        .map_err(|e| e.to_string())?;
    if PathBuf::from(response)
        .canonicalize()
        .map_err(|e| e.to_string())?
        != root.canonicalize().map_err(|e| e.to_string())?
    {
        return Err("启动器租约不属于当前图库".into());
    }
    Ok(true)
}

pub fn webview_directory(root: &Path) -> Result<PathBuf, String> {
    let directory = root.join("webview");
    let context_path = root.join("webview-context.json");
    let context = serde_json::json!({"computer":std::env::var("COMPUTERNAME").unwrap_or_default(),
        "user":std::env::var("USERNAME").unwrap_or_default(),"profile":std::env::var("USERPROFILE").unwrap_or_default()});
    if directory.exists() && context_path.exists() {
        let previous: serde_json::Value = read_json(&context_path)?;
        if previous != context {
            // Browser state may be tied to Windows encryption. Business data is
            // in SQLite; preserve this profile and create a fresh authenticated UI.
            fs::rename(
                &directory,
                root.join(format!("webview-backup-{}", uuid::Uuid::new_v4())),
            )
            .map_err(|e| e.to_string())?;
        }
    }
    fs::create_dir_all(&directory).map_err(|e| e.to_string())?;
    write_json(&context_path, &context)?;
    Ok(directory)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn resolves_installer_and_version_binary_to_the_same_local_config() {
        let root = std::env::temp_dir().join(uuid::Uuid::new_v4().to_string());
        fs::create_dir_all(root.join("app/build")).unwrap();
        assert_eq!(
            instance_root_for_executable(&root.join("TrailSnap.exe")).unwrap(),
            clean_path(root.canonicalize().unwrap())
        );
        assert_eq!(
            instance_root_for_executable(&root.join("app/build/trailsnap-desktop.exe")).unwrap(),
            clean_path(root.canonicalize().unwrap())
        );
        let moved = root.with_extension("moved");
        fs::rename(&root, &moved).unwrap();
        assert_eq!(
            instance_root_for_executable(&moved.join("app/build/trailsnap-desktop.exe")).unwrap(),
            clean_path(moved.canonicalize().unwrap())
        );
        fs::remove_dir_all(moved).unwrap();
    }

    #[test]
    fn instance_data_follows_its_local_config_after_move() {
        let root = std::env::temp_dir().join(uuid::Uuid::new_v4().to_string());
        fs::create_dir_all(root.join("userdata")).unwrap();
        write_json(
            &root.join("instance.json"),
            &InstanceConfig {
                schema_version: 1,
                mode: "portable".into(),
                instance_id: uuid::Uuid::new_v4().to_string(),
                display_name: "test".into(),
                active_build: "build".into(),
                previous_build: None,
                data_root: DataRoot {
                    kind: "relative".into(),
                    path: "userdata".into(),
                },
                server_port: None,
                fixed_port: false,
            },
        )
        .unwrap();
        let moved = root.with_extension("moved");
        fs::rename(&root, &moved).unwrap();
        assert_eq!(
            data_root(&moved, &load_instance(&moved).unwrap()).unwrap(),
            clean_path(moved.join("userdata").canonicalize().unwrap())
        );
        fs::write(moved.join("instance.json"), b"broken").unwrap();
        assert!(load_instance(&moved).is_err());
        fs::remove_dir_all(moved).unwrap();
    }
    #[test]
    fn rejects_escaping_and_windows_paths() {
        for path in ["../other", "/tmp/data", "C:\\data", "", "data/../../other"] {
            assert!(relative_path(Path::new(path)).is_err());
        }
        assert!(relative_path(Path::new("userdata/data")).is_ok());
    }
    #[test]
    fn same_library_cannot_be_opened_twice() {
        let root = std::env::temp_dir().join(uuid::Uuid::new_v4().to_string());
        fs::create_dir(&root).unwrap();
        let first = lock_directory(&root).unwrap();
        assert!(lock_directory(&root).is_err());
        drop(first);
        assert!(lock_directory(&root).is_ok());
        fs::remove_dir_all(root).unwrap();
    }
}
