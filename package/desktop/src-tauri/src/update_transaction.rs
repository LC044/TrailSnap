//! Signed, immutable program staging. No user-data file is accepted from a ZIP.
use crate::portable::{self, BuildManifest};
use base64::{engine::general_purpose::STANDARD, Engine};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    fs,
    io::{Read, Write},
    path::{Path, PathBuf},
};

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct UpdateTransaction {
    pub schema_version: u32,
    pub id: String,
    pub phase: String,
    pub old_build: String,
    pub new_build: String,
    pub version: String,
    pub nonce: String,
    pub error: Option<String>,
}

pub fn journal_path(root: &Path) -> PathBuf {
    root.join("maintenance/update.json")
}
pub fn publish(root: &Path, tx: &UpdateTransaction) -> Result<(), String> {
    portable::write_json(&journal_path(root), tx)
}

fn plain_temporary_tree(path: &Path) -> Result<(), String> {
    let metadata = fs::symlink_metadata(path).map_err(|e| e.to_string())?;
    #[cfg(windows)]
    {
        use std::os::windows::fs::MetadataExt;
        if metadata.file_attributes() & 0x400 != 0 {
            return Err("更新临时文件含链接，已保留".into());
        }
    }
    if metadata.is_symlink() {
        return Err("更新临时文件含链接，已保留".into());
    }
    if path
        .file_name()
        .is_some_and(|name| name == "library.json" || name == "instance.json" || name == "userdata")
        || path
            .extension()
            .is_some_and(|ext| matches!(ext.to_str(), Some("db" | "sqlite" | "sqlite3")))
    {
        return Err("更新临时目录含图库，已保留".into());
    }
    if metadata.is_dir() {
        for entry in fs::read_dir(path).map_err(|e| e.to_string())? {
            plain_temporary_tree(&entry.map_err(|e| e.to_string())?.path())?;
        }
    }
    Ok(())
}

// Call only while holding the instance/data lock and before any updater starts.
// Do not sweep app/, backups, unknown names, configured data roots or links.
pub fn cleanup_orphaned(root: &Path, data: &Path) -> Result<(), String> {
    let maintenance = root.join("maintenance");
    if !maintenance.exists() {
        return Ok(());
    }
    let data = data.canonicalize().map_err(|e| e.to_string())?;
    let expected = root
        .canonicalize()
        .map_err(|e| e.to_string())?
        .join("maintenance");
    let metadata = fs::symlink_metadata(&maintenance).map_err(|e| e.to_string())?;
    #[cfg(windows)]
    {
        use std::os::windows::fs::MetadataExt;
        if metadata.file_attributes() & 0x400 != 0 {
            return Err("更新维护目录含链接，已保留".into());
        }
    }
    if metadata.is_symlink() || maintenance.canonicalize().map_err(|e| e.to_string())? != expected {
        return Err("更新维护目录越界，已保留".into());
    }
    let mut candidates = Vec::new();
    for entry in fs::read_dir(&maintenance).map_err(|e| e.to_string())? {
        let entry = entry.map_err(|e| e.to_string())?;
        let name = entry.file_name().to_string_lossy().into_owned();
        if name
            .strip_prefix("download-")
            .and_then(|s| s.strip_suffix(".zip"))
            .is_some_and(|s| uuid::Uuid::parse_str(s).is_ok())
            && entry.file_type().map_err(|e| e.to_string())?.is_file()
        {
            candidates.push(entry.path());
        }
    }
    let staging = maintenance.join("staging");
    if staging.exists() {
        let metadata = fs::symlink_metadata(&staging).map_err(|e| e.to_string())?;
        #[cfg(windows)]
        {
            use std::os::windows::fs::MetadataExt;
            if metadata.file_attributes() & 0x400 != 0 {
                return Err("更新暂存目录含链接，已保留".into());
            }
        }
        if metadata.is_symlink() {
            return Err("更新暂存目录含链接，已保留".into());
        }
        for entry in fs::read_dir(&staging).map_err(|e| e.to_string())? {
            let entry = entry.map_err(|e| e.to_string())?;
            if uuid::Uuid::parse_str(&entry.file_name().to_string_lossy()).is_ok() {
                candidates.push(entry.path());
            }
        }
    }
    // Validate all candidates before removing any one of them.
    for path in &candidates {
        plain_temporary_tree(path)?;
        let resolved = path.canonicalize().map_err(|e| e.to_string())?;
        if !resolved.starts_with(&expected) || data.starts_with(&resolved) {
            return Err("更新临时目录包含当前图库，已保留".into());
        }
    }
    for path in candidates {
        if path.is_dir() {
            fs::remove_dir_all(path)
        } else {
            fs::remove_file(path)
        }
        .map_err(|e| e.to_string())?;
    }
    Ok(())
}

struct StagingGuard(PathBuf);
impl Drop for StagingGuard {
    fn drop(&mut self) {
        if self.0.exists() && plain_temporary_tree(&self.0).is_ok() {
            let _ = fs::remove_dir_all(&self.0);
        }
    }
}

pub fn verify_archive(path: &Path, signature: &str, hash: &str) -> Result<(), String> {
    let config: serde_json::Value =
        serde_json::from_str(include_str!("../tauri.conf.json")).map_err(|e| e.to_string())?;
    let encoded_key = config["plugins"]["updater"]["pubkey"]
        .as_str()
        .ok_or("更新公钥缺失")?;
    verify_archive_with_key(path, signature, hash, encoded_key)
}

fn verify_archive_with_key(
    path: &Path,
    signature: &str,
    hash: &str,
    encoded_key: &str,
) -> Result<(), String> {
    let key = String::from_utf8(STANDARD.decode(encoded_key).map_err(|e| e.to_string())?)
        .map_err(|e| e.to_string())?;
    let signature = String::from_utf8(
        STANDARD
            .decode(signature.trim())
            .map_err(|e| e.to_string())?,
    )
    .map_err(|e| e.to_string())?;
    let key = minisign_verify::PublicKey::decode(&key).map_err(|e| e.to_string())?;
    let signature = minisign_verify::Signature::decode(&signature).map_err(|e| e.to_string())?;
    let mut verifier = key.verify_stream(&signature).map_err(|e| e.to_string())?;
    let mut file = fs::File::open(path).map_err(|e| e.to_string())?;
    let mut sha = Sha256::new();
    let mut buffer = [0_u8; 128 * 1024];
    loop {
        let count = file.read(&mut buffer).map_err(|e| e.to_string())?;
        if count == 0 {
            break;
        }
        sha.update(&buffer[..count]);
        verifier.update(&buffer[..count]);
    }
    verifier
        .finalize()
        .map_err(|_| "更新签名校验失败".to_string())?;
    if format!("{:x}", sha.finalize()) != hash.to_lowercase() {
        return Err("更新文件 SHA-256 不匹配".into());
    }
    Ok(())
}

pub fn platform() -> String {
    format!("{}-{}", std::env::consts::OS, std::env::consts::ARCH)
}

pub fn unpack_program(
    archive: &Path,
    destination: &Path,
    version: &str,
) -> Result<BuildManifest, String> {
    let file = fs::File::open(archive).map_err(|e| e.to_string())?;
    let mut zip = zip::ZipArchive::new(file).map_err(|e| e.to_string())?;
    if zip.len() > 100_000 {
        return Err("更新包文件过多".into());
    }
    let manifest: BuildManifest = {
        let mut entry = zip.by_name("manifest.json").map_err(|_| "更新包清单缺失")?;
        if entry.size() > 64 * 1024 {
            return Err("更新包清单过大".into());
        }
        let mut text = String::new();
        entry.read_to_string(&mut text).map_err(|e| e.to_string())?;
        serde_json::from_str(&text).map_err(|e| e.to_string())?
    };
    portable::relative_path(Path::new(&manifest.build_id))?;
    portable::relative_path(Path::new(&manifest.executable))?;
    if manifest.schema_version != 1
        || manifest.platform != platform()
        || manifest.version != version
        || Path::new(&manifest.build_id).components().count() != 1
    {
        return Err("更新包的平台、版本或启动器要求不匹配".into());
    }
    if manifest.min_launcher_version > portable::LAUNCHER_VERSION {
        return Err("此更新需要新版启动器，请下载完整安装包并覆盖安装到当前行影集文件夹".into());
    }
    fs::create_dir_all(destination).map_err(|e| e.to_string())?;
    let mut total = 0_u64;
    let mut seen = std::collections::HashSet::new();
    for index in 0..zip.len() {
        let mut entry = zip.by_index(index).map_err(|e| e.to_string())?;
        let path = entry.enclosed_name().ok_or("更新包路径越界")?;
        if entry.name().contains('\\') || entry.name().contains(':') {
            return Err("更新包路径无效".into());
        }
        portable::relative_path(&path)?;
        if entry
            .unix_mode()
            .is_some_and(|mode| mode & 0o170000 == 0o120000)
        {
            return Err("更新包不能包含符号链接".into());
        }
        let first = path
            .components()
            .next()
            .ok_or("更新包路径为空")?
            .as_os_str()
            .to_string_lossy()
            .to_lowercase();
        if ["userdata", "instance.json", "maintenance", "trailsnap.exe"].contains(&first.as_str()) {
            return Err("更新包不能覆盖实例数据".into());
        }
        if !seen.insert(path.to_string_lossy().to_lowercase()) {
            return Err("更新包包含重复路径".into());
        }
        total = total.checked_add(entry.size()).ok_or("更新包体积溢出")?;
        if total > 8 * 1024 * 1024 * 1024 {
            return Err("更新包解压体积过大".into());
        }
        let target = destination.join(&path);
        if entry.is_dir() {
            fs::create_dir_all(&target).map_err(|e| e.to_string())?;
        } else {
            fs::create_dir_all(target.parent().ok_or("更新包路径无效")?)
                .map_err(|e| e.to_string())?;
            let mut output = fs::OpenOptions::new()
                .create_new(true)
                .write(true)
                .open(&target)
                .map_err(|e| e.to_string())?;
            std::io::copy(&mut entry, &mut output).map_err(|e| e.to_string())?;
            output
                .flush()
                .and_then(|_| output.sync_all())
                .map_err(|e| e.to_string())?;
        }
    }
    if !destination.join(&manifest.executable).is_file()
        || !destination.join("server/trailsnap-server.exe").is_file()
        || !manifest.bundled_ai
        || !destination.join("ai/trailsnap-ai.exe").is_file()
        || (manifest.min_launcher_version >= 2
            && !destination.join("portable-launcher.exe").is_file())
    {
        return Err("更新包缺少完整桌面程序、后端或内置 AI".into());
    }
    Ok(manifest)
}

pub fn stage_update(
    root: &Path,
    archive: &Path,
    signature: &str,
    hash: &str,
    version: &str,
) -> Result<UpdateTransaction, String> {
    verify_archive(archive, signature, hash)?;
    stage_verified_update(root, archive, hash, version)
}

fn stage_verified_update(
    root: &Path,
    archive: &Path,
    hash: &str,
    version: &str,
) -> Result<UpdateTransaction, String> {
    let config = portable::load_instance(root)?;
    let old_manifest: BuildManifest = portable::read_json(
        &root
            .join("app")
            .join(&config.active_build)
            .join("manifest.json"),
    )?;
    if semver::Version::parse(version).map_err(|e| e.to_string())?
        <= semver::Version::parse(&old_manifest.version).map_err(|e| e.to_string())?
    {
        return Err("更新必须高于当前程序版本".into());
    }
    let id = uuid::Uuid::new_v4().to_string();
    let staging = root.join("maintenance/staging").join(&id);
    let _staging_guard = StagingGuard(staging.clone());
    let manifest = unpack_program(archive, &staging, version)?;
    let target = root.join("app").join(&manifest.build_id);
    if target.exists() {
        if fs::read_to_string(target.join("archive.sha256"))
            .ok()
            .as_deref()
            != Some(hash)
        {
            return Err("该程序版本目录已经存在且内容不同，请处理未完成更新".into());
        }
        // A rolled-back update may be retried without replacing immutable files.
        fs::remove_dir_all(&staging).map_err(|e| e.to_string())?;
    } else {
        fs::write(staging.join("archive.sha256"), hash).map_err(|e| e.to_string())?;
        fs::create_dir_all(root.join("app")).map_err(|e| e.to_string())?;
        fs::rename(&staging, &target).map_err(|e| e.to_string())?;
    }
    let tx = UpdateTransaction {
        schema_version: 1,
        id,
        phase: "verified".into(),
        old_build: config.active_build,
        new_build: manifest.build_id,
        version: manifest.version,
        nonce: uuid::Uuid::new_v4().to_string(),
        error: None,
    };
    publish(root, &tx)?;
    Ok(tx)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn orphan_cleanup_reclaims_only_update_files_and_preserves_library_and_unknowns() {
        let root = std::env::temp_dir().join(uuid::Uuid::new_v4().to_string());
        let data = root.join("userdata");
        fs::create_dir_all(&data).unwrap();
        let stage = root
            .join("maintenance/staging")
            .join(uuid::Uuid::new_v4().to_string());
        fs::create_dir_all(&stage).unwrap();
        fs::write(stage.join("partial.exe"), b"partial").unwrap();
        let download = root
            .join("maintenance")
            .join(format!("download-{}.zip", uuid::Uuid::new_v4()));
        fs::write(&download, b"partial").unwrap();
        fs::write(data.join("photo.jpg"), b"original").unwrap();
        fs::write(root.join("maintenance/download-manual.zip"), b"unknown").unwrap();
        fs::create_dir_all(root.join("maintenance/staging/manual")).unwrap();
        cleanup_orphaned(&root, &data).unwrap();
        assert!(!stage.exists());
        assert!(!download.exists());
        assert!(root.join("maintenance/download-manual.zip").exists());
        assert!(root.join("maintenance/staging/manual").exists());
        assert_eq!(fs::read(data.join("photo.jpg")).unwrap(), b"original");
        let protected = root
            .join("maintenance/staging")
            .join(uuid::Uuid::new_v4().to_string());
        fs::create_dir_all(&protected).unwrap();
        fs::write(protected.join("library.json"), b"library").unwrap();
        assert!(cleanup_orphaned(&root, &data).is_err());
        assert!(protected.join("library.json").exists());
        fs::remove_file(protected.join("library.json")).unwrap();
        assert!(cleanup_orphaned(&root, &protected).is_err());
        assert!(protected.exists());
        fs::remove_dir_all(root).unwrap();
    }

    #[cfg(windows)]
    #[test]
    fn orphan_cleanup_refuses_junctions() {
        let root = std::env::temp_dir().join(uuid::Uuid::new_v4().to_string());
        let external = root.join("external");
        fs::create_dir_all(&external).unwrap();
        fs::write(external.join("photo.jpg"), b"original").unwrap();
        fs::create_dir_all(root.join("maintenance/staging")).unwrap();
        let linked = root
            .join("maintenance/staging")
            .join(uuid::Uuid::new_v4().to_string());
        let script = root.join("junction.ps1");
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
            .arg(&linked)
            .arg("-Target")
            .arg(&external)
            .status()
            .unwrap()
            .success());
        assert!(cleanup_orphaned(&root, &external).is_err());
        assert_eq!(fs::read(external.join("photo.jpg")).unwrap(), b"original");
        fs::remove_dir(&linked).unwrap();
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn failed_extraction_does_not_leave_a_staging_tree() {
        let root = std::env::temp_dir().join(uuid::Uuid::new_v4().to_string());
        fs::create_dir_all(root.join("app/old")).unwrap();
        portable::write_json(&root.join("instance.json"), &serde_json::json!({
            "schemaVersion":1,"mode":"portable","instanceId":"test","displayName":"test","activeBuild":"old", "previousBuild":null,
            "dataRoot":{"kind":"relative","path":"userdata"}
        })).unwrap();
        portable::write_json(&root.join("app/old/manifest.json"), &serde_json::json!({
            "schemaVersion":1,"version":"1.0.0","buildId":"old","platform":platform(),"minLauncherVersion":1,"executable":"shell.exe"
        })).unwrap();
        let archive = root.join("bad.zip");
        let mut zip = zip::ZipWriter::new(fs::File::create(&archive).unwrap());
        let options = zip::write::SimpleFileOptions::default();
        zip.start_file("manifest.json", options).unwrap();
        zip.write_all(serde_json::json!({"schemaVersion":1,"version":"1.0.1","buildId":"new","platform":platform(),"minLauncherVersion":2,"executable":"shell.exe","bundledAI":true}).to_string().as_bytes()).unwrap();
        zip.start_file("partial.exe", options).unwrap();
        zip.write_all(b"partial").unwrap();
        zip.finish().unwrap();
        assert!(stage_verified_update(&root, &archive, "hash", "1.0.1").is_err());
        assert_eq!(
            fs::read_dir(root.join("maintenance/staging"))
                .unwrap()
                .count(),
            0
        );
        assert!(!journal_path(&root).exists());
        assert_eq!(portable::load_instance(&root).unwrap().active_build, "old");
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn complete_update_requires_ai_and_an_explicit_complete_manifest() {
        let root = std::env::temp_dir().join(uuid::Uuid::new_v4().to_string());
        fs::create_dir_all(&root).unwrap();
        for (index, bundled, include_ai, valid) in [
            (0, true, false, false),
            (1, false, true, false),
            (2, true, true, true),
        ] {
            let archive = root.join(format!("{index}.zip"));
            let mut zip = zip::ZipWriter::new(fs::File::create(&archive).unwrap());
            let options = zip::write::SimpleFileOptions::default();
            zip.start_file("manifest.json", options).unwrap();
            zip.write_all(serde_json::json!({"schemaVersion":1,"version":"1.0.0", "buildId":"complete",
                "platform":platform(),"minLauncherVersion":1,"executable":"trailsnap-desktop.exe","bundledAI":bundled}).to_string().as_bytes()).unwrap();
            for name in ["trailsnap-desktop.exe", "server/trailsnap-server.exe"] {
                zip.start_file(name, options).unwrap();
                zip.write_all(b"program").unwrap();
            }
            if include_ai {
                zip.start_file("ai/trailsnap-ai.exe", options).unwrap();
                zip.write_all(b"ai").unwrap();
            }
            zip.finish().unwrap();
            assert_eq!(
                unpack_program(&archive, &root.join(format!("unpacked-{index}")), "1.0.0").is_ok(),
                valid
            );
        }
        fs::remove_dir_all(root).unwrap();
    }
    #[test]
    fn rejects_untrusted_signature_before_opening_archive() {
        assert!(verify_archive(Path::new("missing.zip"), "not a signature", "00").is_err());
    }
    #[test]
    fn verifies_signed_bytes_and_rejects_tampering() {
        let path = std::env::temp_dir().join(uuid::Uuid::new_v4().to_string());
        fs::write(&path, b"test").unwrap();
        let key=STANDARD.encode("untrusted comment: test key\nRWQf6LRCGA9i53mlYecO4IzT51TGPpvWucNSCh1CBM0QTaLn73Y7GFO3\n");
        let signature=STANDARD.encode("untrusted comment: signature from minisign secret key\nRUQf6LRCGA9i559r3g7V1qNyJDApGip8MfqcadIgT9CuhV3EMhHoN1mGTkUidF/z7SrlQgXdy8ofjb7bNJJylDOocrCo8KLzZwo=\ntrusted comment: timestamp:1556193335\tfile:test\ny/rUw2y8/hOUYjZU71eHp/Wo1KZ40fGy2VJEDl34XMJM+TX48Ss/17u3IvIfbVR1FkZZSNCisQbuQY+bHwhEBg==\n");
        let hash = format!("{:x}", Sha256::digest(b"test"));
        verify_archive_with_key(&path, &signature, &hash, &key).unwrap();
        fs::write(&path, b"Test").unwrap();
        assert!(verify_archive_with_key(&path, &signature, &hash, &key).is_err());
        fs::remove_file(path).unwrap();
    }
    #[test]
    fn transaction_publication_survives_overwrite() {
        let root = std::env::temp_dir().join(uuid::Uuid::new_v4().to_string());
        let mut tx = UpdateTransaction {
            schema_version: 1,
            id: "t".into(),
            phase: "verified".into(),
            old_build: "old".into(),
            new_build: "new".into(),
            version: "1.0.1".into(),
            nonce: "n".into(),
            error: None,
        };
        publish(&root, &tx).unwrap();
        tx.phase = "committed".into();
        publish(&root, &tx).unwrap();
        assert_eq!(
            portable::read_json::<UpdateTransaction>(&journal_path(&root))
                .unwrap()
                .phase,
            "committed"
        );
        fs::remove_dir_all(root).unwrap();
    }
}
