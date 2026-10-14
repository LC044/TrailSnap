#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]
#[path = "../../src-tauri/src/portable.rs"]
mod portable;
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

fn run() -> Result<(), String> {
    let root = portable::clean_path(
        std::env::current_exe()
            .map_err(|e| e.to_string())?
            .parent()
            .ok_or("启动器路径无效")?
            .canonicalize()
            .map_err(|e| e.to_string())?,
    );
    if !root.join("instance.json").exists() {
        fs::create_dir_all(root.join("maintenance")).map_err(|e| e.to_string())?;
        let _initialization_lock = portable::lock_directory(&root.join("maintenance"))?;
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
    if std::env::args().any(|arg| arg == "--validate-only") {
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
        return validate(&root, &config, &tx, &lease);
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
        if semver::Version::parse(&offered.version).map_err(|e| e.to_string())?
            > semver::Version::parse(&current.version).map_err(|e| e.to_string())?
            && !already_failed
        {
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
        let (mut child, job) = spawn(&root, &config, &lease, None)?;
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
    if let Err(error) = run() {
        if let Ok(executable) = std::env::current_exe() {
            if let Some(root) = executable.parent() {
                let _ = portable::write_json(
                    &root.join("maintenance/launcher-error.json"),
                    &serde_json::json!({"error":error}),
                );
            }
        }
        #[cfg(windows)]
        if !std::env::args().any(|arg| arg == "--validate-only")
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
