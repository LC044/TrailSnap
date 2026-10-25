//! Root aliases are stable bootstraps. Update orchestration runs from the build
//! being installed, so later fixes do not depend on replacing a running EXE.
use crate::{portable, update_transaction};
use std::{
    path::{Path, PathBuf},
    process::Command,
};

pub fn target(root: &Path, build: &str, executable: &Path) -> Result<Option<PathBuf>, String> {
    portable::relative_path(Path::new(build))?;
    if Path::new(build).components().count() != 1 {
        return Err("启动器版本目录无效".into());
    }
    let program = root.join("app").join(build);
    let manifest: portable::BuildManifest = portable::read_json(&program.join("manifest.json"))?;
    if manifest.build_id != build || manifest.platform != update_transaction::platform() {
        return Err("启动器程序身份不一致".into());
    }
    let launcher = program.join("portable-launcher.exe");
    // Historical fixtures/builds did not require a versioned launcher.
    if manifest.min_launcher_version < 2 {
        return Ok(None);
    }
    let launcher = launcher
        .canonicalize()
        .map_err(|e| format!("版本启动器缺失，请重新安装完整程序：{e}"))?;
    if !launcher.starts_with(root.canonicalize().map_err(|e| e.to_string())?.join("app")) {
        return Err("版本启动器不能链接到实例外部".into());
    }
    if launcher == executable.canonicalize().map_err(|e| e.to_string())? {
        return Ok(None);
    }
    Ok(Some(launcher))
}

pub fn launch(root: &Path, build: &str, transaction: Option<&str>) -> Result<bool, String> {
    let executable = std::env::current_exe().map_err(|e| e.to_string())?;
    let Some(target) = target(root, build, &executable)? else {
        return Ok(false);
    };
    let mut command = Command::new(target);
    // Preserve only public startup flags, never a previous parent PID/transaction.
    for flag in [
        "--original-library",
        "--validate-only",
        "--prepare-reinstall",
    ] {
        if std::env::args().any(|arg| arg == flag) {
            command.arg(flag);
        }
    }
    command
        .arg("--wait-launcher")
        .arg(std::process::id().to_string());
    if let Some(id) = transaction {
        command.arg("--apply-staged").arg(id);
    }
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000);
    }
    command
        .spawn()
        .map_err(|e| format!("新版启动器启动失败，旧程序和备份已保留：{e}"))?;
    Ok(true)
}

pub fn wait_parent() -> Result<(), String> {
    let args: Vec<_> = std::env::args().collect();
    let Some(index) = args.iter().position(|arg| arg == "--wait-launcher") else {
        return Ok(());
    };
    let pid: u32 = args
        .get(index + 1)
        .ok_or("启动器交接进程缺失")?
        .parse()
        .map_err(|_| "启动器交接进程无效")?;
    #[cfg(windows)]
    unsafe {
        use windows_sys::Win32::{Foundation::*, System::Threading::*};
        let process = OpenProcess(0x00100000 /* SYNCHRONIZE */, 0, pid);
        if process.is_null() {
            if GetLastError() == ERROR_INVALID_PARAMETER {
                return Ok(());
            }
            return Err(std::io::Error::last_os_error().to_string());
        }
        let result = WaitForSingleObject(process, 30_000);
        CloseHandle(process);
        if result != WAIT_OBJECT_0 {
            return Err("等待旧启动器退出超时，请重启行影集".into());
        }
    }
    #[cfg(not(windows))]
    let _ = pid;
    Ok(())
}

pub fn bootstrap() -> Result<bool, String> {
    wait_parent()?;
    // The installer explicitly repairs a retained instance whose old program
    // may already have been uninstalled. Do not resolve that missing build.
    if std::env::args().any(|arg| arg == "--prepare-reinstall") {
        return Ok(false);
    }
    let exe = std::env::current_exe().map_err(|e| e.to_string())?;
    let root = portable::instance_root_for_executable(&exe)?;
    // A versioned launcher owns this session; do not dispatch back to the old
    // active build while applying a candidate or recovering a failed update.
    if exe
        .parent()
        .ok_or("启动器目录无效")?
        .canonicalize()
        .map_err(|e| e.to_string())?
        != root.canonicalize().map_err(|e| e.to_string())?
    {
        return Ok(false);
    }
    if !root.join("instance.json").is_file() {
        return Ok(false);
    }
    let config = match portable::load_instance(&root) {
        Ok(config) => config,
        // Let run() surface corrupt configuration inside the coordinated,
        // retryable native failure window shared by all root aliases.
        Err(_) => return Ok(false),
    };
    let build = config.active_build;
    match launch(&root, &build, None) {
        Ok(delegated) => Ok(delegated),
        Err(error) => {
            // A damaged candidate launcher must not prevent the root bootstrap
            // from restoring an interrupted update using its retained snapshot.
            let pending: Option<update_transaction::UpdateTransaction> =
                portable::read_json(&update_transaction::journal_path(&root)).ok();
            if pending.is_some_and(|tx| {
                !matches!(tx.phase.as_str(), "verified" | "committed" | "rolled_back")
            }) {
                Ok(false)
            } else {
                Err(error)
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    #[test]
    fn root_alias_dispatches_to_build_launcher_and_versioned_entry_does_not_loop() {
        let root = std::env::temp_dir().join(uuid::Uuid::new_v4().to_string());
        let app = root.join("app/new");
        fs::create_dir_all(&app).unwrap();
        fs::write(root.join("TrailSnap.exe"), b"bootstrap").unwrap();
        fs::write(app.join("portable-launcher.exe"), b"new launcher").unwrap();
        portable::write_json(&app.join("manifest.json"), &serde_json::json!({
            "schemaVersion":1,"buildId":"new","version":"1.0.0","platform":update_transaction::platform(),
            "minLauncherVersion":2,"executable":"shell.exe"
        })).unwrap();
        let launcher = target(&root, "new", &root.join("TrailSnap.exe"))
            .unwrap()
            .unwrap();
        assert_eq!(fs::read(&launcher).unwrap(), b"new launcher");
        assert!(target(&root, "new", &launcher).unwrap().is_none());
        fs::remove_file(&launcher).unwrap();
        assert!(target(&root, "new", &root.join("TrailSnap.exe")).is_err());
        assert!(target(&root, "../elsewhere", &root.join("TrailSnap.exe")).is_err());
        fs::remove_dir_all(root).unwrap();
    }
}
