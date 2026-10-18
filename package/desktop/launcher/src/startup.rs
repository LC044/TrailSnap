//! A native startup window and per-installation coordinator, before WebView/server startup.
#[cfg(windows)]
mod native;

pub fn coordinate(run: fn() -> Result<(), String>) -> Result<(), String> {
    #[cfg(windows)]
    {
        native::coordinate(run)
    }
    #[cfg(not(windows))]
    {
        run()
    }
}

pub fn stage(name: &str) {
    #[cfg(windows)]
    native::stage(name);
    #[cfg(not(windows))]
    let _ = name;
}

pub fn session() -> Option<String> {
    #[cfg(windows)]
    {
        native::session()
    }
    #[cfg(not(windows))]
    {
        None
    }
}

pub fn child(pid: u32) {
    #[cfg(windows)]
    native::child(pid);
    #[cfg(not(windows))]
    let _ = pid;
}

pub fn ready() {
    #[cfg(windows)]
    native::ready();
}

pub fn identity(root: &std::path::Path) -> String {
    use sha2::{Digest, Sha256};
    // All three executable names share the same installation identity.
    let normalized = root.to_string_lossy().replace('/', "\\").to_lowercase();
    format!(
        "TrailSnap.Startup.{:x}",
        Sha256::digest(normalized.as_bytes())
    )
}

pub fn label(stage: &str) -> &'static str {
    match stage {
        "checking" => "正在检查旧版本数据…",
        "inventory" => "正在检查旧数据文件…",
        "baseline" => "正在记录原照片校验信息…",
        "copying" => "正在复制并校验数据…",
        "checking_source" => "正在确认旧数据未发生变化…",
        "database" => "正在升级相册和照片记录…",
        "verifying" => "正在校验照片…",
        "publishing" => "正在完成数据切换，请勿退出…",
        "validating" => "正在验证升级后的行影集…",
        _ => "正在启动行影集…",
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn aliases_share_identity_but_other_directories_do_not() {
        assert_eq!(
            identity(std::path::Path::new("C:/Photo/TrailSnap")),
            identity(std::path::Path::new("c:\\photo\\trailsnap"))
        );
        assert_ne!(
            identity(std::path::Path::new("C:/A")),
            identity(std::path::Path::new("C:/B"))
        );
    }
}
