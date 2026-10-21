//! Exercise the actual Windows launcher with harmless native child processes.
#![cfg(windows)]

use serde_json::json;
use std::{
    fs,
    path::Path,
    process::Command,
    thread,
    time::{Duration, Instant},
};

fn write_json(path: &Path, value: serde_json::Value) {
    fs::create_dir_all(path.parent().unwrap()).unwrap();
    fs::write(path, serde_json::to_vec(&value).unwrap()).unwrap();
}

fn fixture(root: &Path, stub: &Path, id: &str) {
    fs::create_dir_all(root.join("userdata")).unwrap();
    fs::create_dir_all(root.join("app/build")).unwrap();
    fs::copy(
        env!("CARGO_BIN_EXE_trailsnap-launcher"),
        root.join("TrailSnap.exe"),
    )
    .unwrap();
    fs::copy(stub, root.join("app/build/child.exe")).unwrap();
    write_json(
        &root.join("app/build/manifest.json"),
        json!({
            "schemaVersion":1,"buildId":"build","version":"1.0.0",
            "platform":format!("windows-{}",std::env::consts::ARCH),
            "minLauncherVersion":1,"executable":"child.exe"
        }),
    );
    write_json(
        &root.join("instance.json"),
        json!({
            "schemaVersion":1,"mode":"portable","instanceId":id,"displayName":id,
            "activeBuild":"build","previousBuild":null,
            "dataRoot":{"kind":"relative","path":"userdata"},"serverPort":null,"fixedPort":false
        }),
    );
    write_json(
        &root.join("portable.json"),
        json!({"schemaVersion":1,"activeBuild":"build"}),
    );
    // A prior installer/update left a complete older build beside the current one.
    fs::create_dir_all(root.join("app/old/server")).unwrap();
    fs::copy(stub, root.join("app/old/child.exe")).unwrap();
    fs::write(root.join("app/old/server/trailsnap-server.exe"), b"backend").unwrap();
    write_json(
        &root.join("app/old/manifest.json"),
        json!({
            "schemaVersion":1,"buildId":"old","version":"0.9.0",
            "platform":format!("windows-{}",std::env::consts::ARCH),
            "minLauncherVersion":1,"executable":"child.exe"
        }),
    );
}

fn wait_for(path: &Path) {
    let deadline = Instant::now() + Duration::from_secs(15);
    while !path.exists() {
        assert!(
            Instant::now() < deadline,
            "launcher did not open {}",
            path.display()
        );
        thread::sleep(Duration::from_millis(50));
    }
}

#[test]
fn normal_shortcut_opens_imported_library_and_explicit_switch_opens_retained_library() {
    let root = std::env::temp_dir().join(format!("trailsnap-activation-{}", uuid::Uuid::new_v4()));
    fs::create_dir_all(&root).unwrap();
    let source_code = root.join("child.rs");
    fs::write(
        &source_code,
        r#"fn main() {
            std::fs::create_dir_all("maintenance").unwrap();
            std::fs::write("maintenance/runtime-ready.json", format!("{{\"pid\":{},\"verified\":true}}", std::process::id())).unwrap();
            std::fs::write("opened.txt", b"ready").unwrap();
            std::thread::sleep(std::time::Duration::from_millis(500));
        }"#,
    )
    .unwrap();
    let stub = root.join("child.exe");
    assert!(Command::new("rustc")
        .arg(&source_code)
        .arg("-o")
        .arg(&stub)
        .status()
        .unwrap()
        .success());
    let source = root.join("installed");
    let target = root.join("imported");
    fixture(&source, &stub, "source");
    fixture(&target, &stub, "target");
    write_json(
        &source.join("maintenance/library-link.json"),
        json!({
            "target":target,"instanceId":"target","sourceBuild":"build"
        }),
    );
    let output = Command::new(source.join("TrailSnap.exe"))
        .env("TS_DESKTOP_TEST_HEADLESS", "1")
        .output()
        .unwrap();
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    wait_for(&target.join("opened.txt"));
    let deadline = Instant::now() + Duration::from_secs(15);
    while target.join("app/old").exists() {
        assert!(
            Instant::now() < deadline,
            "ready client did not retire old program"
        );
        thread::sleep(Duration::from_millis(50));
    }
    assert!(target.join("app/build/child.exe").is_file());
    assert!(
        source.join("app/old/child.exe").is_file(),
        "other instance must be untouched"
    );
    assert!(!source.join("opened.txt").exists());
    fs::remove_file(target.join("opened.txt")).unwrap();

    let output = Command::new(source.join("TrailSnap.exe"))
        .arg("--original-library")
        .env("TS_DESKTOP_TEST_HEADLESS", "1")
        .output()
        .unwrap();
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    assert!(source.join("opened.txt").is_file());
    assert!(!source.join("app/old").exists());
    assert!(!target.join("opened.txt").exists());
    fs::remove_file(source.join("opened.txt")).unwrap();

    // A replacement target at the same path cannot silently select a new library.
    let mut config: serde_json::Value =
        serde_json::from_slice(&fs::read(target.join("instance.json")).unwrap()).unwrap();
    config["instanceId"] = json!("replacement");
    write_json(&target.join("instance.json"), config);
    let output = Command::new(source.join("TrailSnap.exe"))
        .env("TS_DESKTOP_TEST_HEADLESS", "1")
        .output()
        .unwrap();
    assert!(!output.status.success());
    assert!(!source.join("opened.txt").exists());
    assert!(!target.join("opened.txt").exists());

    // The redirected launcher can take a moment to release its executable.
    let deadline = Instant::now() + Duration::from_secs(5);
    while let Err(error) = fs::remove_dir_all(&root) {
        assert!(Instant::now() < deadline, "fixture cleanup failed: {error}");
        thread::sleep(Duration::from_millis(50));
    }
}
