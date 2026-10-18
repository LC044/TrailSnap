//! Actual native coordinator processes, without opening a user's library.
#![cfg(windows)]
use std::os::windows::process::CommandExt;
use std::{
    fs,
    path::Path,
    process::{Child, Command, Stdio},
    thread,
    time::{Duration, Instant},
};
use windows_sys::{
    core::BOOL,
    Win32::{Foundation::*, UI::WindowsAndMessaging::*},
};

struct Running(Child);
impl Drop for Running {
    fn drop(&mut self) {
        let _ = self.0.kill();
        let _ = self.0.wait();
    }
}
fn launch(path: &Path) -> Running {
    Running(
        Command::new(path)
            .creation_flags(0x08000000)
            .env_remove("TS_DESKTOP_TEST_HEADLESS")
            .env("TS_DESKTOP_TEST_HIDE_WINDOW", "1")
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()
            .unwrap(),
    )
}
unsafe extern "system" fn find(hwnd: HWND, value: LPARAM) -> BOOL {
    let pair = &mut *(value as *mut (u32, HWND));
    let mut pid = 0;
    GetWindowThreadProcessId(hwnd, &mut pid);
    if pid == pair.0 && GetWindow(hwnd, GW_OWNER).is_null() {
        pair.1 = hwnd;
        return 0;
    }
    1
}
fn wait_window(process: &mut Running) -> HWND {
    let deadline = Instant::now() + Duration::from_secs(15);
    loop {
        assert!(
            process.0.try_wait().unwrap().is_none(),
            "coordinator exited before its native window"
        );
        let mut pair: (u32, HWND) = (process.0.id(), std::ptr::null_mut());
        unsafe {
            EnumWindows(Some(find), &mut pair as *mut _ as LPARAM);
        }
        if !pair.1.is_null() {
            let mut text = [0u16; 100];
            let len = unsafe { GetWindowTextW(GetDlgItem(pair.1, 1), text.as_mut_ptr(), 100) };
            if String::from_utf16_lossy(&text[..len as usize]).contains("暂时未能") {
                return pair.1;
            }
        }
        assert!(
            Instant::now() < deadline,
            "native failure UI did not appear"
        );
        thread::sleep(Duration::from_millis(50));
    }
}
fn wait_exit(process: &mut Running) {
    let deadline = Instant::now() + Duration::from_secs(10);
    loop {
        if let Some(status) = process.0.try_wait().unwrap() {
            assert!(status.success());
            return;
        }
        assert!(Instant::now() < deadline, "coordinator did not safely exit");
        thread::sleep(Duration::from_millis(50));
    }
}

#[test]
fn three_aliases_reuse_one_native_window_while_other_installations_stay_independent() {
    let cache = std::env::temp_dir().join(format!("trailsnap-startup-{}", uuid::Uuid::new_v4()));
    let first = cache.join("行影集");
    let second = cache.join("另一实例");
    for folder in [&first, &second] {
        fs::create_dir_all(folder).unwrap();
        // Fail closed before discovery, without prompting for a real legacy folder.
        fs::write(folder.join("instance.json"), b"{}").unwrap();
        for alias in [
            "TrailSnap.exe",
            "trailsnap-desktop.exe",
            "portable-launcher.exe",
        ] {
            fs::copy(env!("CARGO_BIN_EXE_trailsnap-launcher"), folder.join(alias)).unwrap();
        }
    }
    // Even an unusable log/progress directory must retain one retryable UI.
    fs::write(first.join("maintenance"), b"occupied by a file").unwrap();
    let mut primary = launch(&first.join("TrailSnap.exe"));
    let window = wait_window(&mut primary);
    for alias in [
        "trailsnap-desktop.exe",
        "portable-launcher.exe",
        "TrailSnap.exe",
    ] {
        let mut duplicate = launch(&first.join(alias));
        wait_exit(&mut duplicate);
        assert_eq!(wait_window(&mut primary), window);
    }
    let mut independent = launch(&second.join("TrailSnap.exe"));
    let other = wait_window(&mut independent);
    assert_ne!(window, other);
    assert_ne!(primary.0.id(), independent.0.id());
    unsafe {
        PostMessageW(window, WM_CLOSE, 0, 0);
        PostMessageW(other, WM_CLOSE, 0, 0);
    }
    wait_exit(&mut primary);
    wait_exit(&mut independent);
    fs::remove_dir_all(cache).unwrap();
}

#[test]
fn closing_the_client_before_readiness_exits_without_a_failure_dialog() {
    let cache =
        std::env::temp_dir().join(format!("trailsnap-startup-close-{}", uuid::Uuid::new_v4()));
    fs::create_dir_all(cache.join("userdata")).unwrap();
    fs::create_dir_all(cache.join("app/build")).unwrap();
    fs::copy(
        env!("CARGO_BIN_EXE_trailsnap-launcher"),
        cache.join("TrailSnap.exe"),
    )
    .unwrap();
    fs::write(cache.join("child.rs"), "fn main() {}").unwrap();
    assert!(Command::new("rustc")
        .arg(cache.join("child.rs"))
        .arg("-o")
        .arg(cache.join("app/build/child.exe"))
        .status()
        .unwrap()
        .success());
    fs::write(cache.join("instance.json"), serde_json::to_vec(&serde_json::json!({
        "schemaVersion":1,"mode":"portable","instanceId":"close-test","displayName":"close-test",
        "activeBuild":"build","previousBuild":null,"dataRoot":{"kind":"relative","path":"userdata"}
    })).unwrap()).unwrap();
    fs::write(
        cache.join("portable.json"),
        br#"{"schemaVersion":1,"activeBuild":"build"}"#,
    )
    .unwrap();
    fs::write(cache.join("app/build/manifest.json"), serde_json::to_vec(&serde_json::json!({
        "schemaVersion":1,"buildId":"build","version":"1.0.0","platform":format!("windows-{}",std::env::consts::ARCH),
        "minLauncherVersion":1,"executable":"child.exe"
    })).unwrap()).unwrap();
    let mut process = launch(&cache.join("TrailSnap.exe"));
    wait_exit(&mut process);
    assert!(!cache.join("maintenance/launcher-error.json").exists());
    assert!(!cache.join("maintenance/runtime-ready.json").exists());
    fs::remove_dir_all(cache).unwrap();
}
