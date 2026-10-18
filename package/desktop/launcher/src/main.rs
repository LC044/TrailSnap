#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]
#[path = "../../src-tauri/src/library_link.rs"]
mod library_link;
mod link_recovery;
#[path = "../../src-tauri/src/portable.rs"]
mod portable;
mod startup;
#[path = "../../src-tauri/src/update_transaction.rs"]
mod update_transaction;
use portable::{BuildManifest, InstanceConfig};
#[cfg(windows)]
use std::os::windows::process::CommandExt;
use std::{
    fs,
    io::{Read, Write},
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    time::{Duration, Instant},
};
use update_transaction::UpdateTransaction;

#[cfg(windows)]
struct ProcessJob(windows_sys::Win32::Foundation::HANDLE);
#[cfg(windows)]
impl ProcessJob {
    fn attach(child: &Child) -> Result<Self, String> {
        use std::os::windows::io::AsRawHandle;
        use windows_sys::Win32::System::JobObjects::*;
        unsafe {
            let job = CreateJobObjectW(std::ptr::null(), std::ptr::null());
            if job.is_null() {
                return Err(std::io::Error::last_os_error().to_string());
            }
            let mut info: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = std::mem::zeroed();
            info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
            if SetInformationJobObject(
                job,
                JobObjectExtendedLimitInformation,
                &info as *const _ as *const _,
                std::mem::size_of_val(&info) as u32,
            ) == 0
                || AssignProcessToJobObject(job, child.as_raw_handle() as _) == 0
            {
                windows_sys::Win32::Foundation::CloseHandle(job);
                return Err(std::io::Error::last_os_error().to_string());
            }
            Ok(Self(job))
        }
    }
}
#[cfg(windows)]
impl Drop for ProcessJob {
    fn drop(&mut self) {
        unsafe {
            use windows_sys::Win32::System::JobObjects::*;
            // Job termination is asynchronous. Wait for sidecars to release
            // SQLite handles before snapshotting or restoring the library.
            TerminateJobObject(self.0, 0);
            let deadline = Instant::now() + Duration::from_secs(15);
            loop {
                let mut info: JOBOBJECT_BASIC_ACCOUNTING_INFORMATION = std::mem::zeroed();
                if QueryInformationJobObject(
                    self.0,
                    JobObjectBasicAccountingInformation,
                    &mut info as *mut _ as *mut _,
                    std::mem::size_of_val(&info) as u32,
                    std::ptr::null_mut(),
                ) == 0
                    || info.ActiveProcesses == 0
                    || Instant::now() >= deadline
                {
                    break;
                }
                std::thread::sleep(Duration::from_millis(50));
            }
            windows_sys::Win32::Foundation::CloseHandle(self.0);
        }
    }
}
#[cfg(not(windows))]
struct ProcessJob;
#[cfg(not(windows))]
impl ProcessJob {
    fn attach(_: &Child) -> Result<Self, String> {
        Ok(Self)
    }
}

fn manifest(root: &Path, build: &str) -> Result<BuildManifest, String> {
    portable::relative_path(Path::new(build))?;
    let program = root.join("app").join(build);
    if !program
        .canonicalize()
        .map_err(|e| e.to_string())?
        .starts_with(root.join("app").canonicalize().map_err(|e| e.to_string())?)
    {
        return Err("程序目录不能链接到实例外部".into());
    }
    let value: BuildManifest = portable::read_json(&program.join("manifest.json"))?;
    portable::relative_path(Path::new(&value.executable))?;
    if value.schema_version != 1
        || value.build_id != build
        || value.platform != update_transaction::platform()
        || value.min_launcher_version > portable::LAUNCHER_VERSION
    {
        return Err("程序清单不兼容".into());
    }
    Ok(value)
}

fn should_apply_distribution(
    current: &BuildManifest,
    offered: &BuildManifest,
) -> Result<bool, String> {
    let current_version = semver::Version::parse(&current.version).map_err(|e| e.to_string())?;
    let offered_version = semver::Version::parse(&offered.version).map_err(|e| e.to_string())?;
    // Installing a refreshed preview may keep the product version but publish
    // different immutable program files. Validate it like any other upgrade.
    Ok(offered_version > current_version
        || (offered_version == current_version && offered.build_id != current.build_id))
}

fn helper(
    root: &Path,
    build: &str,
    action: &str,
    data: &Path,
    snapshot: &Path,
) -> Result<(), String> {
    let executable = root
        .join("app")
        .join(build)
        .join("server/trailsnap-server.exe");
    let mut command = Command::new(executable);
    command
        .args([action])
        .arg(data)
        .arg(snapshot)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::piped());
    #[cfg(windows)]
    command.creation_flags(0x08000000);
    let child = command.spawn().map_err(|e| e.to_string())?;
    let _job = ProcessJob::attach(&child)?;
    let output = child.wait_with_output().map_err(|e| e.to_string())?;
    if !output.status.success() {
        return Err(String::from_utf8_lossy(&output.stderr).into_owned());
    }
    Ok(())
}

fn lease_server(data: PathBuf) -> Result<(u16, String), String> {
    let listener = std::net::TcpListener::bind(("127.0.0.1", 0)).map_err(|e| e.to_string())?;
    let port = listener.local_addr().map_err(|e| e.to_string())?.port();
    let token = uuid::Uuid::new_v4().to_string();
    let expected = token.clone();
    std::thread::spawn(move || {
        for socket in listener.incoming() {
            let Ok(mut socket) = socket else {
                break;
            };
            let _ = socket.set_read_timeout(Some(Duration::from_secs(2)));
            let mut text = String::new();
            if (&mut socket).take(1024).read_to_string(&mut text).is_ok() && text.trim() == expected
            {
                let _ = socket.write_all(data.to_string_lossy().as_bytes());
            }
        }
    });
    Ok((port, token))
}

fn spawn(
    root: &Path,
    config: &InstanceConfig,
    lease: &(u16, String),
    verify: Option<&UpdateTransaction>,
) -> Result<(Child, ProcessJob), String> {
    let build = manifest(root, &config.active_build)?;
    let mut command = Command::new(
        root.join("app")
            .join(&config.active_build)
            .join(build.executable),
    );
    command
        .current_dir(root)
        .env("TS_INSTANCE_ROOT", root)
        .env("TS_LAUNCHER_LEASE_PORT", lease.0.to_string())
        .env("TS_LAUNCHER_LEASE_TOKEN", &lease.1);
    if let Some(tx) = verify {
        command
            .env("TS_DESKTOP_VERIFY", "1")
            .env("TS_UPDATE_NONCE", &tx.nonce)
            .env(
                "TS_UPDATE_BASELINE",
                root.join("maintenance/validation-baseline.json"),
            );
    } else {
        command
            .env_remove("TS_DESKTOP_VERIFY")
            .env_remove("TS_UPDATE_NONCE")
            .env_remove("TS_UPDATE_BASELINE");
    }
    #[cfg(windows)]
    command.creation_flags(0x08000000);
    let mut child = command.spawn().map_err(|e| e.to_string())?;
    let job = match ProcessJob::attach(&child) {
        Ok(job) => job,
        Err(e) => {
            let _ = child.kill();
            return Err(e);
        }
    };
    Ok((child, job))
}

fn rollback(
    root: &Path,
    data: &Path,
    config: &mut InstanceConfig,
    tx: &mut UpdateTransaction,
) -> Result<(), String> {
    tx.phase = "rolling_back".into();
    update_transaction::publish(root, tx)?;
    let snapshot = data.join("backups").join(&tx.id);
    if snapshot.join("snapshot.json").is_file() {
        helper(root, &tx.new_build, "--restore-data", data, &snapshot).map_err(|error| {
            format!("升级恢复未完成，已停止启动以保护图库。请保留当前目录和备份 {}，修复磁盘或权限后重试。{error}", snapshot.display())
        })?;
    }
    config.active_build = tx.old_build.clone();
    config.previous_build = None;
    portable::write_json(&root.join("instance.json"), config)?;
    tx.phase = "rolled_back".into();
    update_transaction::publish(root, tx)
}

fn apply(
    root: &Path,
    data: &Path,
    config: &mut InstanceConfig,
    tx: &mut UpdateTransaction,
    lease: &(u16, String),
) -> Result<(), String> {
    let snapshot = data.join("backups").join(&tx.id);
    helper(root, &tx.new_build, "--snapshot-data", data, &snapshot)?;
    fs::copy(
        snapshot.join("snapshot.json"),
        root.join("maintenance/validation-baseline.json"),
    )
    .map_err(|e| e.to_string())?;
    tx.phase = "backed_up".into();
    update_transaction::publish(root, tx)?;
    config.previous_build = Some(tx.old_build.clone());
    config.active_build = tx.new_build.clone();
    portable::write_json(&root.join("instance.json"), config)?;
    tx.phase = "validating".into();
    update_transaction::publish(root, tx)?;
    validate(root, config, tx, lease)?;
    tx.phase = "committed".into();
    update_transaction::publish(root, tx)
}

fn validate(
    root: &Path,
    config: &InstanceConfig,
    tx: &UpdateTransaction,
    lease: &(u16, String),
) -> Result<(), String> {
    let marker = root.join("maintenance/validated.json");
    let failure = root.join("maintenance/validation-error.json");
    if failure.exists() {
        fs::remove_file(&failure).map_err(|e| e.to_string())?;
    }
    if marker.exists() {
        fs::remove_file(&marker).map_err(|e| e.to_string())?;
    }
    startup::stage("validating");
    let (mut candidate, job) = spawn(root, config, lease, Some(tx))?;
    let start = Instant::now();
    let validation = (|| loop {
        if candidate.try_wait().map_err(|e| e.to_string())?.is_some() {
            return Err("候选程序验证期间退出".to_string());
        }
        if let Ok(value) = portable::read_json::<serde_json::Value>(&failure) {
            if value["nonce"] == tx.nonce {
                return Err(value["error"]
                    .as_str()
                    .unwrap_or("候选程序启动失败")
                    .to_string());
            }
        }
        if let Ok(value) = portable::read_json::<serde_json::Value>(&marker) {
            if value["nonce"] == tx.nonce && value["verified"] == true {
                return Ok(());
            }
        }
        if start.elapsed() > Duration::from_secs(30 * 60) {
            return Err("更新验证超时，请检查日志".into());
        }
        std::thread::sleep(Duration::from_millis(200));
    })();
    // Dropping this job kills the verifier and all its writers before commit/restore.
    let _ = candidate.kill();
    let _ = candidate.wait();
    drop(job);
    validation
}

// Installing over the original shortcut location must also update the active
// imported library, via its own normal backup/validation transaction.
fn sync_linked_distribution(source: &Path, target: &Path) -> Result<(), String> {
    let descriptor: serde_json::Value = match portable::read_json(&source.join("portable.json")) {
        Ok(value) => value,
        Err(_) => return Ok(()),
    };
    let offered = descriptor["activeBuild"]
        .as_str()
        .ok_or("安装包程序版本缺失")?;
    let marker = source.join("maintenance/library-link.json");
    let mut link: library_link::LibraryLink = portable::read_json(&marker)?;
    if link.source_build.as_deref() == Some(offered) {
        return Ok(());
    }
    let offered_manifest = manifest(source, offered)?;
    let current = portable::load_instance(target)?;
    let current_manifest = manifest(target, &current.active_build)?;
    if should_apply_distribution(&current_manifest, &offered_manifest)? {
        let destination = target.join("app").join(offered);
        if !destination.exists() {
            let stage = target
                .join("maintenance")
                .join(format!("installer-{}", uuid::Uuid::new_v4()));
            fn copy_tree(source: &Path, target: &Path) -> Result<(), String> {
                let metadata = fs::symlink_metadata(source).map_err(|e| e.to_string())?;
                #[cfg(windows)]
                {
                    use std::os::windows::fs::MetadataExt;
                    if metadata.file_attributes() & 0x400 != 0 {
                        return Err("程序资源包含链接，已停止复制".into());
                    }
                }
                if metadata.file_type().is_symlink() {
                    return Err("程序资源包含链接，已停止复制".into());
                }
                if metadata.is_dir() {
                    fs::create_dir_all(target).map_err(|e| e.to_string())?;
                    for entry in fs::read_dir(source).map_err(|e| e.to_string())? {
                        let entry = entry.map_err(|e| e.to_string())?;
                        copy_tree(&entry.path(), &target.join(entry.file_name()))?;
                    }
                } else {
                    fs::copy(source, target).map_err(|e| e.to_string())?;
                }
                Ok(())
            }
            let copy = copy_tree(&source.join("app").join(offered), &stage)
                .and_then(|_| fs::rename(&stage, &destination).map_err(|e| e.to_string()));
            if stage.exists() {
                let _ = fs::remove_dir_all(&stage);
            }
            copy.map_err(|e| format!("无法将已安装的新程序复制到图库目录 {}：{e}。数据未更改，请检查空间和权限后重试。", target.display()))?;
        }
        manifest(target, offered)?;
        portable::write_json(&target.join("portable.json"), &descriptor)?;
    }
    link.source_build = Some(offered.into());
    portable::write_json(&marker, &link)
}

fn automatic_upgrade(root: &Path, action: &str) -> Result<(), String> {
    let descriptor: serde_json::Value = portable::read_json(&root.join("portable.json"))?;
    let build = descriptor["activeBuild"].as_str().ok_or("程序版本缺失")?;
    manifest(root, build)?;
    let mut command = Command::new(
        root.join("app")
            .join(build)
            .join("server/trailsnap-server.exe"),
    );
    command
        .arg("--automatic-upgrade")
        .arg(root)
        .arg(action)
        .env("PYTHONIOENCODING", "utf-8")
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::piped());
    if let Some(session) = startup::session() {
        command.env("TS_AUTOMATIC_UPGRADE_SESSION", session);
    }
    #[cfg(windows)]
    command.creation_flags(0x08000000);
    let child = command.spawn().map_err(|e| e.to_string())?;
    let _job = ProcessJob::attach(&child)?;
    let output = child.wait_with_output().map_err(|e| e.to_string())?;
    if !output.status.success() {
        return Err(String::from_utf8_lossy(&output.stderr).into_owned());
    }
    Ok(())
}

fn run() -> Result<(), String> {
    let root = portable::clean_path(
        std::env::current_exe()
            .map_err(|e| e.to_string())?
            .parent()
            .ok_or("启动器路径无效")?
            .canonicalize()
            .map_err(|e| e.to_string())?,
    );
    // Only an explicit installer invocation can authorize replacing a removed
    // program build. A normal launch with missing files still fails closed.
    if std::env::args().any(|arg| arg == "--prepare-reinstall") {
        if root.join("instance.json").is_file() {
            let config = portable::load_instance(&root)?;
            if !root
                .join("app")
                .join(&config.active_build)
                .join("manifest.json")
                .is_file()
            {
                portable::data_root(&root, &config)?;
                let distribution: serde_json::Value =
                    portable::read_json(&root.join("portable.json"))?;
                let build = distribution["activeBuild"]
                    .as_str()
                    .ok_or("重装程序版本缺失")?;
                manifest(&root, build)?;
                portable::write_json(
                    &root.join("maintenance/reinstall.json"),
                    &serde_json::json!({"originalConfig": config, "newBuild": build}),
                )?;
            }
        }
        return Ok(());
    }
    let original_library = std::env::args().any(|arg| arg == "--original-library");
    if let Some(target) = if original_library {
        None
    } else {
        match library_link::resolve(&root) {
            Ok(target) => target,
            Err(error) => {
                #[cfg(windows)]
                if std::env::var("TS_DESKTOP_TEST_HEADLESS").as_deref() != Ok("1")
                    && !std::env::args().any(|arg| arg == "--validate-only")
                {
                    let mut failure = error;
                    loop {
                        let Some(selected) = link_recovery::choose_moved_library(&failure) else {
                            return Ok(());
                        };
                        match library_link::relink(&root, &selected) {
                            Ok(_) => break,
                            Err(error) => failure = error,
                        }
                    }
                    return run();
                }
                return Err(error);
            }
        }
    } {
        sync_linked_distribution(&root, &target)?;
        let mut command = Command::new(target.join("TrailSnap.exe"));
        #[cfg(windows)]
        command.creation_flags(0x08000000);
        command
            .spawn()
            .map_err(|e| format!("无法打开导入后的图库 {}：{e}", target.display()))?;
        return Ok(());
    }
    if !root.join("instance.json").exists() {
        fs::create_dir_all(root.join("maintenance")).map_err(|e| e.to_string())?;
        let _initialization_lock = portable::lock_directory(&root.join("maintenance"))?;
        if !root.join("instance.json").exists() {
            startup::stage("checking");
            let mut migration = automatic_upgrade(&root, "prepare");
            #[cfg(windows)]
            while let Err(ref error) = migration {
                if error.contains("TRAILSNAP_UPGRADE_PAUSED:")
                    || root.join("maintenance/automatic-upgrade.json").exists()
                    || std::env::var("TS_DESKTOP_TEST_HEADLESS").as_deref() == Ok("1")
                    || std::env::args().any(|arg| arg == "--validate-only")
                {
                    break;
                }
                let Some(source) = link_recovery::choose_legacy_library(error) else {
                    return Ok(());
                };
                portable::write_json(
                    &root.join("maintenance/automatic-upgrade-source.json"),
                    &serde_json::json!({"source": source}),
                )?;
                migration = automatic_upgrade(&root, "prepare");
            }
            migration?;
        }
        if !root.join("instance.json").exists() {
            if root.join("userdata/library.json").exists()
                || root.join("userdata/data/trailsnap.sqlite").exists()
                || root.join("maintenance/initialized.json").exists()
            {
                return Err(
                    "实例配置缺失但已有图库，请恢复 instance.json，不能自动创建新图库".into(),
                );
            }
            let descriptor: serde_json::Value = portable::read_json(&root.join("portable.json"))?;
            let build = descriptor["activeBuild"]
                .as_str()
                .ok_or("便携发行清单缺失版本")?;
            manifest(&root, build)?;
            fs::create_dir_all(root.join("userdata")).map_err(|e| e.to_string())?;
            let initial = InstanceConfig {
                schema_version: 1,
                mode: "portable".into(),
                instance_id: uuid::Uuid::new_v4().to_string(),
                display_name: root
                    .file_name()
                    .unwrap_or_default()
                    .to_string_lossy()
                    .into_owned(),
                active_build: build.into(),
                previous_build: None,
                data_root: portable::DataRoot {
                    kind: "relative".into(),
                    path: "userdata".into(),
                },
                server_port: None,
                fixed_port: false,
            };
            portable::write_json(&root.join("instance.json"), &initial)?;
        }
    }
    let mut config = portable::load_instance(&root)?;
    portable::write_json(
        &root.join("maintenance/initialized.json"),
        &serde_json::json!({"instanceId":config.instance_id}),
    )?;
    let data = portable::data_root(&root, &config)?;
    let _lock = portable::lock_directory(&data)?;
    let lease = lease_server(data.clone())?;
    let journal = update_transaction::journal_path(&root);
    let automatic_journal = root.join("maintenance/automatic-upgrade.json");
    let automatic: Option<serde_json::Value> = if automatic_journal.exists() {
        Some(portable::read_json(&automatic_journal)?)
    } else {
        None
    };
    let automatic_pending = automatic
        .as_ref()
        .is_some_and(|job| job["phase"] == "published" || job["phase"] == "validated");
    let automatic_cleanup = automatic.as_ref().is_some_and(|job| {
        job["phase"] == "published" || job["phase"] == "validated" || job["phase"] == "committed"
    });
    let reinstall = root.join("maintenance/reinstall.json");
    if reinstall.is_file() {
        let recovery: serde_json::Value = portable::read_json(&reinstall)?;
        let original: InstanceConfig = serde_json::from_value(recovery["originalConfig"].clone())
            .map_err(|e| e.to_string())?;
        if original.instance_id != config.instance_id {
            return Err("重装记录不属于当前图库，请保留配置与数据".into());
        }
        let build = recovery["newBuild"].as_str().ok_or("重装程序版本缺失")?;
        let offered = manifest(&root, build)?;
        let previous: Option<UpdateTransaction> = portable::read_json(&journal).ok();
        let committed = previous
            .as_ref()
            .is_some_and(|tx| tx.phase == "committed" && tx.new_build == build);
        if !committed {
            if let Some(mut tx) = previous
                .filter(|tx| !["verified", "committed", "rolled_back"].contains(&tx.phase.as_str()))
            {
                rollback(&root, &data, &mut config, &mut tx)?;
            }
            // There is no previous executable after uninstall. Keep its original
            // configuration, snapshot the library, and stop if verification fails.
            config.active_build = build.into();
            let mut tx = UpdateTransaction {
                schema_version: 1,
                id: uuid::Uuid::new_v4().to_string(),
                old_build: build.into(),
                new_build: build.into(),
                version: offered.version,
                phase: "apply_requested".into(),
                nonce: uuid::Uuid::new_v4().to_string(),
                error: None,
            };
            update_transaction::publish(&root, &tx)?;
            if let Err(error) = apply(&root, &data, &mut config, &mut tx, &lease) {
                tx.error = Some(error.clone());
                rollback(&root, &data, &mut config, &mut tx)?;
                portable::write_json(&root.join("instance.json"), &original)?;
                return Err(format!("重新安装后的程序验证失败，已恢复图库数据。请保留当前目录与 backups，并重新安装兼容版本：{error}"));
            }
        }
        fs::remove_file(reinstall).map_err(|e| e.to_string())?;
    }
    let validate_only = std::env::args().any(|arg| arg == "--validate-only");
    if validate_only || automatic_pending {
        let tx = UpdateTransaction {
            schema_version: 1,
            id: uuid::Uuid::new_v4().to_string(),
            old_build: config.active_build.clone(),
            new_build: config.active_build.clone(),
            version: String::new(),
            phase: "validating".into(),
            nonce: uuid::Uuid::new_v4().to_string(),
            error: None,
        };
        let snapshot = data.join("backups").join(&tx.id);
        helper(
            &root,
            &config.active_build,
            "--snapshot-data",
            &data,
            &snapshot,
        )?;
        fs::create_dir_all(root.join("maintenance")).map_err(|e| e.to_string())?;
        fs::copy(
            snapshot.join("snapshot.json"),
            root.join("maintenance/validation-baseline.json"),
        )
        .map_err(|e| e.to_string())?;
        // A broken copied path must not disappear from the verification set
        // just because the target can no longer read it while snapshotting.
        let conversion = root.join("conversion.json");
        if conversion.is_file() {
            let proof: serde_json::Value = portable::read_json(&conversion)?;
            if let Some(media) = proof.get("media") {
                if !media.is_array() {
                    return Err("导入照片校验记录无效，请保留副本与原图库".into());
                }
                let path = root.join("maintenance/validation-baseline.json");
                let mut baseline: serde_json::Value = portable::read_json(&path)?;
                baseline["media"] = media.clone();
                portable::write_json(&path, &baseline)?;
            }
        }
        validate(&root, &config, &tx, &lease)?;
        if validate_only {
            return Ok(());
        }
        automatic_upgrade(&root, "validated")?;
    }
    if journal.exists() {
        let mut tx: UpdateTransaction = portable::read_json(&journal)?;
        portable::relative_path(Path::new(&tx.id))?;
        if !["verified", "committed", "rolled_back"].contains(&tx.phase.as_str()) {
            tx.error = Some("上次更新中断，已恢复升级前的数据与程序".into());
            rollback(&root, &data, &mut config, &mut tx)?;
        }
    }
    // A new installer only publishes a distribution descriptor. Applying it
    // uses the same backup/validation/rollback transaction as a ZIP update.
    let distribution: serde_json::Value = portable::read_json(&root.join("portable.json"))?;
    if let Some(build) = distribution["activeBuild"].as_str() {
        let current = manifest(&root, &config.active_build)?;
        let offered = manifest(&root, build)?;
        let previous: Option<UpdateTransaction> = portable::read_json(&journal).ok();
        let already_failed = previous
            .as_ref()
            .is_some_and(|tx| tx.phase == "rolled_back" && tx.new_build == build);
        if should_apply_distribution(&current, &offered)? && !already_failed {
            let mut tx = UpdateTransaction {
                schema_version: 1,
                id: uuid::Uuid::new_v4().to_string(),
                old_build: config.active_build.clone(),
                new_build: build.into(),
                version: offered.version,
                phase: "apply_requested".into(),
                nonce: uuid::Uuid::new_v4().to_string(),
                error: None,
            };
            update_transaction::publish(&root, &tx)?;
            if let Err(error) = apply(&root, &data, &mut config, &mut tx, &lease) {
                tx.error = Some(error);
                rollback(&root, &data, &mut config, &mut tx)?;
            }
        }
    }
    loop {
        let ready = root.join("maintenance/runtime-ready.json");
        if ready.exists() {
            fs::remove_file(&ready).map_err(|e| e.to_string())?;
        }
        startup::stage("launching");
        let (mut child, job) = spawn(&root, &config, &lease, None)?;
        startup::child(child.id());
        // Cleanup is authorized only by this normal shell's backend readiness,
        // never by the candidate or a stale marker from an earlier launch.
        {
            let deadline = Instant::now() + Duration::from_secs(30 * 60);
            let mut backend_ready = false;
            while Instant::now() < deadline {
                if let Some(status) = child.try_wait().map_err(|e| e.to_string())? {
                    // Closing the actual client during startup is a user exit,
                    // not a migration failure. Do not clean the old source.
                    if status.success() {
                        return Ok(());
                    }
                    return Err("行影集在启动完成前退出，请查看日志后重试。".into());
                }
                if portable::read_json::<serde_json::Value>(&ready)
                    .ok()
                    .is_some_and(|v| v["pid"] == child.id() && v["verified"] == true)
                {
                    backend_ready = true;
                    startup::ready();
                    if automatic_cleanup {
                        if let Err(error) = automatic_upgrade(&root, "cleanup") {
                            portable::write_json(
                                &root.join("maintenance/automatic-upgrade-cleanup-error.json"),
                                &serde_json::json!({"error": error}),
                            )?;
                        }
                    }
                    break;
                }
                std::thread::sleep(Duration::from_millis(200));
            }
            if !backend_ready {
                return Err("行影集启动超时，请检查日志与磁盘后重试。".into());
            }
        }
        child.wait().map_err(|e| e.to_string())?;
        drop(job);
        let handoff = root.join("maintenance/handoff.json");
        if handoff.exists() {
            let value: serde_json::Value = portable::read_json(&handoff)?;
            let target = PathBuf::from(value["target"].as_str().ok_or("副本入口缺失")?);
            let target_config = portable::load_instance(&target)?;
            manifest(&target, &target_config.active_build)?;
            fs::remove_file(&handoff).map_err(|e| e.to_string())?;
            let mut command = Command::new(target.join("TrailSnap.exe"));
            if value["original"] == true {
                command.arg("--original-library");
            }
            #[cfg(windows)]
            command.creation_flags(0x08000000);
            command.spawn().map_err(|e| {
                format!(
                    "副本已保存到 {}，自动打开失败：{e}。请手动运行其中的 TrailSnap.exe",
                    target.display()
                )
            })?;
            return Ok(());
        }
        let mut latest = portable::load_instance(&root)?;
        if journal.exists() {
            let mut tx: UpdateTransaction = portable::read_json(&journal)?;
            if tx.phase == "apply_requested" {
                if let Err(error) = apply(&root, &data, &mut latest, &mut tx, &lease) {
                    tx.error = Some(error);
                    rollback(&root, &data, &mut latest, &mut tx)?;
                }
                config = latest;
                continue;
            }
        }
        // Tauri relaunch is routed through a marker so the lock-owning parent
        // supervises the new process, rather than creating an orphan child.
        let restart = root.join("maintenance/restart.json");
        if restart.exists() {
            fs::remove_file(restart).map_err(|e| e.to_string())?;
            config = latest;
            continue;
        }
        return Ok(());
    }
}

fn main() {
    if let Err(error) = startup::coordinate(run) {
        if let Ok(executable) = std::env::current_exe() {
            if let Some(root) = executable.parent() {
                let _ = portable::write_json(
                    &root.join("maintenance/launcher-error.json"),
                    &serde_json::json!({"error":error}),
                );
            }
        }
        #[cfg(windows)]
        if !std::env::args().any(|arg| arg == "--validate-only" || arg == "--prepare-reinstall")
            && std::env::var("TS_DESKTOP_TEST_HEADLESS").as_deref() != Ok("1")
        {
            unsafe {
                #[link(name = "user32")]
                unsafe extern "system" {
                    fn MessageBoxW(
                        h: *mut std::ffi::c_void,
                        text: *const u16,
                        title: *const u16,
                        flags: u32,
                    ) -> i32;
                }
                let text: Vec<u16> = error.encode_utf16().chain(Some(0)).collect();
                let title: Vec<u16> = "行影集启动失败".encode_utf16().chain(Some(0)).collect();
                MessageBoxW(std::ptr::null_mut(), text.as_ptr(), title.as_ptr(), 0x10);
            }
        }
        eprintln!("{error}");
        std::process::exit(1);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn build(version: &str, id: &str) -> BuildManifest {
        BuildManifest {
            schema_version: 1,
            version: version.into(),
            build_id: id.into(),
            platform: update_transaction::platform(),
            min_launcher_version: 1,
            executable: "trailsnap-desktop.exe".into(),
        }
    }

    #[test]
    fn installer_refresh_reaches_imported_library_once_without_downgrading() {
        let root = std::env::temp_dir().join(uuid::Uuid::new_v4().to_string());
        let source = root.join("installed");
        let target = root.join("imported");
        for folder in [&source, &target] {
            fs::create_dir_all(folder.join("userdata")).unwrap();
            fs::create_dir_all(folder.join("app/old")).unwrap();
            portable::write_json(
                &folder.join("app/old/manifest.json"),
                &build("1.0.0", "old"),
            )
            .unwrap();
            fs::write(folder.join("TrailSnap.exe"), b"launcher").unwrap();
            portable::write_json(
                &folder.join("portable.json"),
                &serde_json::json!({"activeBuild":"old"}),
            )
            .unwrap();
        }
        let mut config = InstanceConfig {
            schema_version: 1,
            mode: "portable".into(),
            instance_id: "imported".into(),
            display_name: "test".into(),
            active_build: "old".into(),
            previous_build: None,
            data_root: portable::DataRoot {
                kind: "relative".into(),
                path: "userdata".into(),
            },
            server_port: None,
            fixed_port: false,
        };
        portable::write_json(&target.join("instance.json"), &config).unwrap();
        library_link::activate(&source, &target).unwrap();
        fs::create_dir_all(source.join("app/refreshed/server")).unwrap();
        portable::write_json(
            &source.join("app/refreshed/manifest.json"),
            &build("1.0.1", "refreshed"),
        )
        .unwrap();
        fs::write(source.join("app/refreshed/server/test"), b"new program").unwrap();
        portable::write_json(
            &source.join("portable.json"),
            &serde_json::json!({"activeBuild":"refreshed"}),
        )
        .unwrap();
        sync_linked_distribution(&source, &target).unwrap();
        assert_eq!(
            fs::read(target.join("app/refreshed/server/test")).unwrap(),
            b"new program"
        );
        let descriptor: serde_json::Value =
            portable::read_json(&target.join("portable.json")).unwrap();
        assert_eq!(descriptor["activeBuild"], "refreshed");
        sync_linked_distribution(&source, &target).unwrap();
        config.active_build = "refreshed".into();
        portable::write_json(&target.join("instance.json"), &config).unwrap();
        portable::write_json(
            &source.join("portable.json"),
            &serde_json::json!({"activeBuild":"old"}),
        )
        .unwrap();
        sync_linked_distribution(&source, &target).unwrap();
        let descriptor: serde_json::Value =
            portable::read_json(&target.join("portable.json")).unwrap();
        assert_eq!(descriptor["activeBuild"], "refreshed");
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn overwritten_preview_applies_new_build_without_downgrading() {
        let current = build("0.17.4", "old");
        assert!(should_apply_distribution(&current, &build("0.17.4", "fixed")).unwrap());
        assert!(!should_apply_distribution(&current, &build("0.17.4", "old")).unwrap());
        assert!(!should_apply_distribution(&current, &build("0.17.3", "different")).unwrap());
        assert!(should_apply_distribution(&current, &build("0.17.5", "next")).unwrap());
    }
}
