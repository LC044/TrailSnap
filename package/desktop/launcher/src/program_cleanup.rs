//! Retire old immutable builds only after a normal client reports readiness.
use crate::{portable, update_transaction};
use crate::legacy_ai::cleanup_legacy_ai;
use portable::{BuildManifest, InstanceConfig};
use std::{fs, path::Path};

fn plain_tree(path: &Path) -> Result<(), String> {
    let metadata = fs::symlink_metadata(path).map_err(|e| e.to_string())?;
    #[cfg(windows)]
    {
        use std::os::windows::fs::MetadataExt;
        if metadata.file_attributes() & 0x400 != 0 {
            return Err(format!("程序目录含链接，已保留：{}", path.display()));
        }
    }
    if metadata.is_symlink() {
        return Err(format!("程序目录含链接，已保留：{}", path.display()));
    }
    if metadata.is_dir() {
        for entry in fs::read_dir(path).map_err(|e| e.to_string())? {
            plain_tree(&entry.map_err(|e| e.to_string())?.path())?;
        }
    } else if path.file_name().is_some_and(|name| name == "library.json")
        || path
            .extension()
            .is_some_and(|ext| matches!(ext.to_str(), Some("sqlite" | "sqlite3" | "db")))
    {
        return Err(format!("程序目录含图库数据，已保留：{}", path.display()));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn legacy_ai_cleanup_preserves_models_and_unknown_files() {
        let data = std::env::temp_dir().join(uuid::Uuid::new_v4().to_string());
        let legacy = data.join("ai-extensions/core-ai");
        fs::create_dir_all(legacy.join("runtime")).unwrap();
        fs::create_dir_all(data.join("models")).unwrap();
        fs::write(data.join("models/keep"), b"model").unwrap();
        fs::write(legacy.join("runtime/ai.exe"), b"old").unwrap();
        portable::write_json(&legacy.join("manifest.json"), &json!({"id":"core-ai"})).unwrap();
        fs::write(legacy.join("unknown"), b"preserve").unwrap();
        cleanup_legacy_ai(&data).unwrap();
        assert!(legacy.join("unknown").exists());
        fs::remove_file(legacy.join("unknown")).unwrap();
        cleanup_legacy_ai(&data).unwrap();
        assert!(!legacy.exists());
        assert_eq!(fs::read(data.join("models/keep")).unwrap(), b"model");
        fs::remove_dir_all(data).unwrap();
    }
    use std::path::PathBuf;

    struct Fixture(PathBuf);
    impl Drop for Fixture {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.0);
        }
    }
    fn build(root: &Path, id: &str, version: &str) {
        let path = root.join("app").join(id);
        fs::create_dir_all(path.join("server")).unwrap();
        fs::write(path.join("trailsnap-desktop.exe"), b"shell").unwrap();
        fs::write(path.join("server/trailsnap-server.exe"), b"backend").unwrap();
        portable::write_json(
            &path.join("manifest.json"),
            &json!({
                "schemaVersion":1,"buildId":id,"version":version,"platform":"windows-x86_64",
                "minLauncherVersion":1,"executable":"trailsnap-desktop.exe"
            }),
        )
        .unwrap();
    }
    fn fixture() -> (Fixture, InstanceConfig) {
        let root = std::env::temp_dir().join(format!(
            "trailsnap-program-cleanup-{}",
            uuid::Uuid::new_v4()
        ));
        fs::create_dir_all(root.join("userdata/backups")).unwrap();
        fs::write(root.join("userdata/backups/keep"), b"backup").unwrap();
        build(&root, "old", "1.0.0");
        build(&root, "current", "2.0.0");
        portable::write_json(&root.join("instance.json"), &json!({
            "schemaVersion":1,"mode":"portable","instanceId":"fixture","displayName":"fixture",
            "activeBuild":"current","previousBuild":"old","dataRoot":{"kind":"relative","path":"userdata"}
        })).unwrap();
        portable::write_json(
            &root.join("portable.json"),
            &json!({"schemaVersion":1,"activeBuild":"old"}),
        )
        .unwrap();
        let config = portable::load_instance(&root).unwrap();
        (Fixture(root), config)
    }
    fn phase(root: &Path, name: &str) {
        portable::write_json(
            &update_transaction::journal_path(root),
            &json!({
                "schemaVersion":1,"id":"update","phase":name,"oldBuild":"old","newBuild":"current",
                "version":"2.0.0","nonce":"test","error":null
            }),
        )
        .unwrap();
    }

    #[test]
    fn repeated_install_and_online_update_keep_one_build_and_valid_pointers() {
        let (f, mut config) = fixture();
        phase(&f.0, "committed");
        for (id, version) in [
            ("current", "2.0.0"),
            ("third", "3.0.0"),
            ("fourth", "4.0.0"),
        ] {
            build(&f.0, id, version);
            config.active_build = id.into();
            portable::write_json(&f.0.join("instance.json"), &config).unwrap();
            after_ready(&f.0, &mut config).unwrap();
            assert_eq!(fs::read_dir(f.0.join("app")).unwrap().count(), 1);
            let distribution: serde_json::Value =
                portable::read_json(&f.0.join("portable.json")).unwrap();
            assert_eq!(distribution["activeBuild"], id);
            assert!(portable::load_instance(&f.0)
                .unwrap()
                .previous_build
                .is_none());
            assert_eq!(
                fs::read(f.0.join("userdata/backups/keep")).unwrap(),
                b"backup"
            );
            after_ready(&f.0, &mut config).unwrap(); // Same-version reinstall / next launch is idempotent.
        }
    }

    #[test]
    fn unfinished_updates_retain_both_builds() {
        let (f, mut config) = fixture();
        for name in ["verified", "apply_requested", "backed_up", "validating", "awaiting_ready"] {
            phase(&f.0, name);
            after_ready(&f.0, &mut config).unwrap();
            assert!(f.0.join("app/old/server/trailsnap-server.exe").exists());
            assert_eq!(config.previous_build.as_deref(), Some("old"));
        }
    }

    #[test]
    fn a_new_installer_waiting_for_validation_is_preserved() {
        let (f, mut config) = fixture();
        build(&f.0, "pending", "3.0.0");
        portable::write_json(
            &f.0.join("portable.json"),
            &json!({"activeBuild":"pending"}),
        )
        .unwrap();
        after_ready(&f.0, &mut config).unwrap();
        assert_eq!(fs::read_dir(f.0.join("app")).unwrap().count(), 3);
    }

    #[test]
    fn unknown_directories_are_preserved_and_library_markers_block_cleanup() {
        let (f, mut config) = fixture();
        fs::create_dir_all(f.0.join("app/personal")).unwrap();
        fs::write(f.0.join("app/personal/photo.jpg"), b"photo").unwrap();
        fs::write(f.0.join("app/old/server/library.json"), b"library").unwrap();
        assert!(after_ready(&f.0, &mut config).is_err());
        assert!(f.0.join("app/old/trailsnap-desktop.exe").exists());
        fs::remove_file(f.0.join("app/old/server/library.json")).unwrap();
        after_ready(&f.0, &mut config).unwrap();
        assert!(!f.0.join("app/old").exists());
        assert_eq!(
            fs::read(f.0.join("app/personal/photo.jpg")).unwrap(),
            b"photo"
        );
    }

    #[test]
    fn configured_data_inside_a_retired_program_is_preserved() {
        let (f, mut config) = fixture();
        fs::create_dir_all(f.0.join("app/old/custom-library")).unwrap();
        config.data_root.path = "app/old/custom-library".into();
        portable::write_json(&f.0.join("instance.json"), &config).unwrap();
        assert!(after_ready(&f.0, &mut config).is_err());
        assert!(f.0.join("app/old/server/trailsnap-server.exe").exists());
    }

    #[test]
    fn interrupted_deletion_resumes_even_if_manifest_and_executable_were_removed() {
        let (f, mut config) = fixture();
        portable::write_json(
            &f.0.join("maintenance/program-cleanup.json"),
            &json!({
                "instanceId":"fixture","builds":["old"]
            }),
        )
        .unwrap();
        fs::remove_file(f.0.join("app/old/manifest.json")).unwrap();
        fs::remove_file(f.0.join("app/old/trailsnap-desktop.exe")).unwrap();
        after_ready(&f.0, &mut config).unwrap();
        assert!(!f.0.join("app/old").exists());
        assert!(!f.0.join("maintenance/program-cleanup.json").exists());
    }

    #[test]
    fn successful_rollback_keeps_the_working_build_and_retires_failed_candidate() {
        let (f, mut config) = fixture();
        phase(&f.0, "rolled_back");
        config.active_build = "old".into();
        portable::write_json(&f.0.join("instance.json"), &config).unwrap();
        portable::write_json(
            &f.0.join("portable.json"),
            &json!({"activeBuild":"current"}),
        )
        .unwrap();
        after_ready(&f.0, &mut config).unwrap();
        assert!(f.0.join("app/old/server/trailsnap-server.exe").exists());
        assert!(!f.0.join("app/current").exists());
        let distribution: serde_json::Value =
            portable::read_json(&f.0.join("portable.json")).unwrap();
        assert_eq!(distribution["activeBuild"], "old");
    }

    #[cfg(windows)]
    #[test]
    fn current_build_is_kept_even_when_directory_case_differs_from_config() {
        let (f, mut config) = fixture();
        fs::rename(f.0.join("app/current"), f.0.join("app/renaming")).unwrap();
        fs::rename(f.0.join("app/renaming"), f.0.join("app/CURRENT")).unwrap();
        after_ready(&f.0, &mut config).unwrap();
        assert!(f.0.join("app/CURRENT/trailsnap-desktop.exe").exists());
        assert!(!f.0.join("app/old").exists());
    }

    #[cfg(windows)]
    #[test]
    fn windows_junction_never_authorizes_removing_external_files() {
        let (f, mut config) = fixture();
        let external = f.0.join("external");
        fs::create_dir_all(&external).unwrap();
        fs::write(external.join("photo.jpg"), b"original").unwrap();
        let script = f.0.join("junction.ps1");
        fs::write(&script, "param($Link, $Target)\nNew-Item -ItemType Junction -Path $Link -Target $Target -ErrorAction Stop | Out-Null").unwrap();
        assert!(std::process::Command::new("powershell.exe")
            .args([
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File"
            ])
            .arg(&script)
            .arg("-Link")
            .arg(f.0.join("app/old/linked"))
            .arg("-Target")
            .arg(&external)
            .output()
            .unwrap()
            .status
            .success());
        assert!(after_ready(&f.0, &mut config).is_err());
        assert_eq!(fs::read(external.join("photo.jpg")).unwrap(), b"original");
        assert!(f.0.join("app/old/trailsnap-desktop.exe").exists());
    }

    #[cfg(windows)]
    #[test]
    fn locked_runtime_is_recorded_and_cleanup_retries_after_unlock() {
        use std::os::windows::fs::OpenOptionsExt;
        let (f, mut config) = fixture();
        let locked = fs::OpenOptions::new()
            .read(true)
            .share_mode(0)
            .open(f.0.join("app/old/server/trailsnap-server.exe"))
            .unwrap();
        assert!(after_ready(&f.0, &mut config).is_err());
        assert!(f.0.join("maintenance/program-cleanup.json").exists());
        drop(locked);
        after_ready(&f.0, &mut config).unwrap();
        assert!(!f.0.join("app/old").exists());
        assert!(f.0.join("app/current/server/trailsnap-server.exe").exists());
    }
}

pub fn after_ready(root: &Path, config: &mut InstanceConfig) -> Result<(), String> {
    portable::relative_path(Path::new(&config.active_build))?;
    if Path::new(&config.active_build).components().count() != 1 {
        return Err("当前版本目录必须位于 app 下一级".into());
    }
    let journal = update_transaction::journal_path(root);
    let transaction = if journal.exists() {
        let tx: update_transaction::UpdateTransaction = portable::read_json(&journal)?;
        if !matches!(tx.phase.as_str(), "committed" | "rolled_back") {
            return Ok(()); // A staged candidate or interrupted transaction still needs both builds.
        }
        Some(tx)
    } else {
        None
    };
    // Do not trust cached configuration after a child requested a switch.
    let saved = portable::load_instance(root)?;
    if saved.instance_id != config.instance_id || saved.active_build != config.active_build {
        return Ok(());
    }
    let app = root.join("app");
    let metadata = fs::symlink_metadata(&app).map_err(|e| e.to_string())?;
    #[cfg(windows)]
    {
        use std::os::windows::fs::MetadataExt;
        if metadata.file_attributes() & 0x400 != 0 {
            return Err("程序根目录含链接，已停止清理".into());
        }
    }
    if metadata.is_symlink() || !metadata.is_dir() {
        return Err("程序根目录无效，已停止清理".into());
    }
    let app = app.canonicalize().map_err(|e| e.to_string())?;
    let active = app.join(&config.active_build);
    plain_tree(&active)?;
    let active = active.canonicalize().map_err(|e| e.to_string())?;
    if active.parent() != Some(app.as_path()) {
        return Err("当前程序目录越界，已停止清理".into());
    }
    let current: BuildManifest = portable::read_json(&active.join("manifest.json"))?;
    if current.build_id != config.active_build {
        return Err("当前程序版本身份不一致，已停止清理".into());
    }
    let pending_path = root.join("maintenance/program-cleanup.json");
    let pending: serde_json::Value = if pending_path.exists() {
        portable::read_json(&pending_path)?
    } else {
        serde_json::json!({"instanceId": config.instance_id, "builds": []})
    };
    if pending["instanceId"] != config.instance_id {
        return Err("程序清理记录不属于当前实例".into());
    }
    let mut distribution: serde_json::Value = portable::read_json(&root.join("portable.json"))?;
    let offered = distribution["activeBuild"].as_str().ok_or("发行版本缺失")?;
    if offered != config.active_build {
        portable::relative_path(Path::new(offered))?;
        let failed = transaction.as_ref().is_some_and(|tx| {
            tx.phase == "rolled_back"
                && tx.old_build == config.active_build
                && tx.new_build == offered
        });
        // Preserve a newly installed distribution awaiting validation.
        let retiring = pending["builds"]
            .as_array()
            .is_some_and(|builds| builds.iter().any(|build| build.as_str() == Some(offered)));
        if !failed && !retiring {
            let candidate: BuildManifest =
                portable::read_json(&app.join(offered).join("manifest.json"))?;
            if semver::Version::parse(&candidate.version).map_err(|e| e.to_string())?
                > semver::Version::parse(&current.version).map_err(|e| e.to_string())?
            {
                return Ok(());
            }
        }
    }
    let data = portable::data_root(root, config)?
        .canonicalize()
        .map_err(|e| e.to_string())?;
    let mut retired = Vec::new();
    for entry in fs::read_dir(&app).map_err(|e| e.to_string())? {
        let path = entry.map_err(|e| e.to_string())?.path();
        if path == active || !path.is_dir() {
            continue;
        }
        let name = path
            .file_name()
            .and_then(|name| name.to_str())
            .ok_or("版本目录名无效")?;
        let retry = pending["builds"]
            .as_array()
            .is_some_and(|builds| builds.iter().any(|build| build.as_str() == Some(name)));
        if !retry {
            // A manifest alone never authorizes deletion of an arbitrary directory.
            let Ok(build) = portable::read_json::<BuildManifest>(&path.join("manifest.json"))
            else {
                continue;
            };
            if name != build.build_id
                || build.schema_version != 1
                || build.platform != current.platform
                || Path::new(&build.executable).components().count() != 1
                || portable::relative_path(Path::new(&build.executable)).is_err()
                || !path.join(&build.executable).is_file()
                || !path.join("server/trailsnap-server.exe").is_file()
            {
                continue;
            }
        }
        plain_tree(&path)?;
        let resolved = path.canonicalize().map_err(|e| e.to_string())?;
        if resolved == active {
            continue;
        }
        if resolved.parent() != Some(app.as_path()) || data.starts_with(&resolved) {
            return Err("旧程序目录越界或包含当前图库，已停止清理".into());
        }
        retired.push(resolved);
    }
    // Publish valid pointers first. A crash partway through deletion can only
    // leave extra files, never a descriptor pointing to a deleted build.
    distribution["activeBuild"] = config.active_build.clone().into();
    portable::write_json(&root.join("portable.json"), &distribution)?;
    config.previous_build = None;
    portable::write_json(&root.join("instance.json"), config)?;
    portable::write_json(
        &pending_path,
        &serde_json::json!({
            "instanceId": config.instance_id,
            "builds": retired.iter().map(|path| path.file_name().unwrap().to_string_lossy()).collect::<Vec<_>>()
        }),
    )?;
    for path in retired {
        fs::remove_dir_all(&path)
            .map_err(|e| format!("旧程序清理未完成 {}：{e}", path.display()))?;
    }
    fs::remove_file(pending_path).map_err(|e| e.to_string())?;
    if current.bundled_ai {
        cleanup_legacy_ai(&data)?;
    }
    Ok(())
}
