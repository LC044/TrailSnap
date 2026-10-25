//! Real process handoff and rollback with harmless native shell/helper fixtures.
#![cfg(windows)]
use serde_json::{json, Value};
use std::{
    fs,
    path::Path,
    process::Command,
    thread,
    time::{Duration, Instant},
};

fn write_json(path: &Path, value: Value) {
    fs::create_dir_all(path.parent().unwrap()).unwrap();
    fs::write(path, serde_json::to_vec(&value).unwrap()).unwrap();
}

#[test]
fn versioned_launcher_handoff_commits_only_after_ready_and_restores_failed_normal_start() {
    let cache = std::env::temp_dir().join(format!("trailsnap-update-{}", uuid::Uuid::new_v4()));
    fs::create_dir_all(&cache).unwrap();
    let code = cache.join("stub.rs");
    fs::write(&code, r#"
use std::{fs, path::PathBuf, time::Duration};
fn main() {
    let args: Vec<_> = std::env::args().collect();
    if args.len() > 1 {
        let data = PathBuf::from(&args[2]); let backup = PathBuf::from(&args[3]);
        if args[1] == "--snapshot-data" {
            fs::create_dir_all(&backup).unwrap();
            fs::copy(data.join("database"), backup.join("database")).unwrap();
            fs::write(backup.join("snapshot.json"), b"{}").unwrap();
        } else if args[1] == "--restore-data" {
            fs::copy(backup.join("database"), data.join("database")).unwrap();
        }
        return;
    }
    let root = PathBuf::from(std::env::var("TS_INSTANCE_ROOT").unwrap());
    let build = std::env::current_exe().unwrap().parent().unwrap().file_name().unwrap().to_string_lossy().to_string();
    if std::env::var("TS_DESKTOP_VERIFY").is_ok() {
        fs::write(root.join("userdata/database"), b"migrated").unwrap();
        let nonce = std::env::var("TS_UPDATE_NONCE").unwrap();
        fs::write(root.join("maintenance/validated.json"), format!("{{\"nonce\":\"{nonce}\",\"verified\":true}}")).unwrap();
        std::thread::sleep(Duration::from_secs(10)); return;
    }
    if build == "new" && root.join("fail-new").exists() { std::process::exit(7); }
    // Prove the transaction has not committed before the real shell is ready.
    let journal = fs::read_to_string(root.join("maintenance/update.json")).unwrap();
    fs::write(root.join(format!("phase-before-ready-{build}")), journal).unwrap();
    fs::write(root.join("maintenance/runtime-ready.json"), format!("{{\"pid\":{},\"verified\":true}}", std::process::id())).unwrap();
    std::thread::sleep(Duration::from_millis(700));
    if build == "old" && root.join("request-update.json").exists() {
        fs::copy(root.join("request-update.json"),root.join("maintenance/update.json")).unwrap();
        fs::remove_file(root.join("request-update.json")).unwrap();
        return;
    }
    fs::write(root.join("finished"), build).unwrap();
}"#).unwrap();
    let stub = cache.join("stub.exe");
    assert!(Command::new("rustc")
        .arg(&code)
        .arg("-o")
        .arg(&stub)
        .status()
        .unwrap()
        .success());
    for scenario in [
        "success",
        "online",
        "failure",
        "interrupted",
        "interrupted-missing-launcher",
    ] {
        let fail = !matches!(scenario, "success" | "online");
        let root = cache.join(scenario);
        fs::create_dir_all(root.join("userdata")).unwrap();
        fs::write(root.join("userdata/database"), b"original").unwrap();
        if fail {
            fs::write(root.join("fail-new"), b"fail").unwrap();
        }
        fs::copy(
            env!("CARGO_BIN_EXE_trailsnap-launcher"),
            root.join("TrailSnap.exe"),
        )
        .unwrap();
        for (id, version) in [("old", "1.0.0"), ("new", "1.1.0")] {
            let program = root.join("app").join(id);
            fs::create_dir_all(program.join("server")).unwrap();
            fs::copy(&stub, program.join("child.exe")).unwrap();
            fs::copy(&stub, program.join("server/trailsnap-server.exe")).unwrap();
            fs::copy(
                env!("CARGO_BIN_EXE_trailsnap-launcher"),
                program.join("portable-launcher.exe"),
            )
            .unwrap();
            write_json(
                &program.join("manifest.json"),
                json!({"schemaVersion":1,"buildId":id,"version":version,
                "platform":format!("windows-{}",std::env::consts::ARCH),"minLauncherVersion":2,"executable":"child.exe"}),
            );
        }
        write_json(
            &root.join("instance.json"),
            json!({"schemaVersion":1,"mode":"portable","instanceId":"test","displayName":"test",
            "activeBuild":"old","previousBuild":null,"dataRoot":{"kind":"relative","path":"userdata"}}),
        );
        write_json(
            &root.join("portable.json"),
            json!({"schemaVersion":1,"activeBuild":if scenario == "online" {"old"} else {"new"}}),
        );
        if scenario == "online" {
            let mut tx = json!({"schemaVersion":1,"id":"online","phase":"verified",
                "oldBuild":"old","newBuild":"new","version":"1.1.0","nonce":"online","error":null});
            write_json(&root.join("maintenance/update.json"), tx.clone());
            tx["phase"] = json!("apply_requested");
            write_json(&root.join("request-update.json"), tx);
        }
        if scenario.starts_with("interrupted") {
            let config_path = root.join("instance.json");
            let mut config: Value =
                serde_json::from_slice(&fs::read(&config_path).unwrap()).unwrap();
            config["activeBuild"] = json!("new");
            config["previousBuild"] = json!("old");
            write_json(&config_path, config);
            fs::create_dir_all(root.join("userdata/backups/interrupted")).unwrap();
            fs::write(
                root.join("userdata/backups/interrupted/database"),
                b"original",
            )
            .unwrap();
            fs::write(root.join("userdata/database"), b"migrated").unwrap();
            write_json(
                &root.join("userdata/backups/interrupted/snapshot.json"),
                json!({}),
            );
            write_json(
                &root.join("maintenance/update.json"),
                json!({"schemaVersion":1,"id":"interrupted","phase":"awaiting_ready",
                "oldBuild":"old","newBuild":"new","version":"1.1.0","nonce":"interrupted","error":null}),
            );
            if scenario == "interrupted-missing-launcher" {
                fs::remove_file(root.join("app/new/portable-launcher.exe")).unwrap();
            }
        }
        let mut launcher = Command::new(root.join("TrailSnap.exe"))
            .env("TS_DESKTOP_TEST_HEADLESS", "1")
            .spawn()
            .unwrap();
        let deadline = Instant::now() + Duration::from_secs(30);
        while !root.join("finished").is_file() {
            assert!(
                Instant::now() < deadline,
                "handoff/upgrade did not finish: {}",
                root.display()
            );
            thread::sleep(Duration::from_millis(50));
        }
        assert!(launcher.wait().unwrap().success());
        let tx: Value =
            serde_json::from_slice(&fs::read(root.join("maintenance/update.json")).unwrap())
                .unwrap();
        let config: Value =
            serde_json::from_slice(&fs::read(root.join("instance.json")).unwrap()).unwrap();
        if fail {
            assert_eq!(tx["phase"], "rolled_back");
            assert_eq!(config["activeBuild"], "old");
            assert_eq!(
                fs::read(root.join("userdata/database")).unwrap(),
                b"original"
            );
            assert_eq!(fs::read_to_string(root.join("finished")).unwrap(), "old");
        } else {
            assert_eq!(tx["phase"], "committed");
            assert_eq!(config["activeBuild"], "new");
            let before: Value =
                serde_json::from_slice(&fs::read(root.join("phase-before-ready-new")).unwrap())
                    .unwrap();
            assert_eq!(before["phase"], "awaiting_ready");
            assert_eq!(
                fs::read(root.join("userdata/database")).unwrap(),
                b"migrated"
            );
            let deadline = Instant::now() + Duration::from_secs(15);
            while root.join("app/old").exists() {
                assert!(
                    Instant::now() < deadline,
                    "ready build did not finish cleanup"
                );
                thread::sleep(Duration::from_millis(50));
            }
        }
    }
    let deadline = Instant::now() + Duration::from_secs(10);
    while let Err(error) = fs::remove_dir_all(&cache) {
        assert!(Instant::now() < deadline, "test cleanup: {error}");
        thread::sleep(Duration::from_millis(50));
    }
}
