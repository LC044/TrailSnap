//! Retire obsolete extension files only after a complete application is ready.
use crate::portable;
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

pub fn cleanup_legacy_ai(data: &Path) -> Result<(), String> {
    // Called only after the new complete build has reached normal readiness
    // and all rollback-sensitive program cleanup has committed.
    let data = data.canonicalize().map_err(|e| e.to_string())?;
    let extensions = data.join("ai-extensions");
    let legacy = extensions.join("core-ai");
    if !legacy.exists() {
        return Ok(());
    }
    plain_tree(&extensions)?;
    let metadata: serde_json::Value = portable::read_json(&legacy.join("manifest.json"))?;
    if metadata["id"] != "core-ai" || metadata.get("modelPath").is_some() {
        return Ok(()); // Old bundles that carry models are deliberately kept.
    }
    for entry in fs::read_dir(&legacy).map_err(|e| e.to_string())? {
        let name = entry.map_err(|e| e.to_string())?.file_name();
        if name != "runtime" && name != "manifest.json" {
            return Ok(()); // Never guess whether unknown files are user data.
        }
    }
    let parent = extensions.canonicalize().map_err(|e| e.to_string())?;
    let target = legacy.canonicalize().map_err(|e| e.to_string())?;
    if target.parent() != Some(parent.as_path()) || !parent.starts_with(&data) {
        return Err("旧 AI 程序目录越界，已保留".into());
    }
    fs::remove_dir_all(&target).map_err(|e| e.to_string())?;
    let state = extensions.join("installed.json");
    if state.exists() {
        let mut value: serde_json::Value = portable::read_json(&state)?;
        if let Some(items) = value["extensions"].as_object_mut() {
            items.remove("core-ai");
            portable::write_json(&state, &value)?;
        }
    }
    let downloads = extensions.join(".downloads");
    if downloads.is_dir() {
        for entry in fs::read_dir(downloads).map_err(|e| e.to_string())? {
            let path = entry.map_err(|e| e.to_string())?.path();
            let name = path.file_name().unwrap_or_default().to_string_lossy();
            if path.is_file() && name.starts_with("core-ai-")
                && (name.ends_with(".tar.gz") || name.ends_with(".tar.gz.part")) {
                fs::remove_file(&path).map_err(|e| e.to_string())?;
            }
        }
    }
    Ok(())
}
