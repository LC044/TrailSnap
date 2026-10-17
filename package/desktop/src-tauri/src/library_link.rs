//! User-confirmed library activation shared by the shell and stable launcher.
use crate::portable;
use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};

#[derive(Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct LibraryLink {
    pub target: PathBuf,
    pub instance_id: String,
    #[serde(default)]
    pub source_build: Option<String>,
}

pub fn resolve(root: &Path) -> Result<Option<PathBuf>, String> {
    let mut current = portable::clean_path(root.canonicalize().map_err(|e| e.to_string())?);
    let mut visited = vec![current.clone()];
    for _ in 0..8 {
        let marker = current.join("maintenance/library-link.json");
        if !marker.exists() {
            return Ok((visited.len() > 1).then_some(current));
        }
        let link: LibraryLink = portable::read_json(&marker)?;
        let target = link.target.canonicalize().map(portable::clean_path).map_err(|_| {
            format!("导入后的图库不可用：{}。请连接原磁盘或将图库放回该位置。为保护数据，未打开旧图库或新建空库。启动关联保存在 {}。", link.target.display(), marker.display())
        })?;
        let config = portable::load_instance(&target)?;
        if config.instance_id != link.instance_id || !target.join("TrailSnap.exe").is_file() {
            return Err("导入后的图库身份或入口已改变，请检查原目录；未打开替代图库".into());
        }
        portable::data_root(&target, &config)?;
        if visited.iter().any(|p| {
            p.to_string_lossy()
                .eq_ignore_ascii_case(&target.to_string_lossy())
        }) {
            return Err("图库启动关联形成循环，请检查 maintenance/library-link.json".into());
        }
        visited.push(target.clone());
        current = target;
    }
    Err("图库启动关联层数过多，请检查配置".into())
}

pub fn activate(root: &Path, target: &Path) -> Result<(), String> {
    let config = portable::load_instance(target)?;
    let source_build = portable::read_json::<serde_json::Value>(&root.join("portable.json"))
        .ok()
        .and_then(|v| v["activeBuild"].as_str().map(str::to_owned));
    let link = LibraryLink {
        target: target.to_path_buf(),
        instance_id: config.instance_id,
        source_build,
    };
    portable::write_json(&root.join("maintenance/library-link.json"), &link)
}

/// Repair a moved library, never replace it with an unrelated instance.
pub fn relink(root: &Path, selected: &Path) -> Result<PathBuf, String> {
    let root = portable::clean_path(root.canonicalize().map_err(|e| e.to_string())?);
    let target = portable::clean_path(selected.canonicalize().map_err(|e| e.to_string())?);
    let marker = root.join("maintenance/library-link.json");
    let mut link: LibraryLink = portable::read_json(&marker)?;
    let config = portable::load_instance(&target)?;
    if config.instance_id != link.instance_id {
        return Err("这不是之前导入的图库，请选择搬迁后的原行影集文件夹。未更改启动位置。".into());
    }
    let data = portable::data_root(&target, &config)?;
    if target == root || !target.join("TrailSnap.exe").is_file()
        || !target.join("app").join(&config.active_build).join("manifest.json").is_file()
        || !data.join("data/trailsnap.sqlite").is_file()
        || !data.join("library.json").is_file() {
        return Err("所选图库不完整，请选择同时包含 TrailSnap.exe、instance.json 和 userdata 的文件夹，保留原文件。".into());
    }
    // Validate the complete chain before touching the only known startup link.
    let final_target = resolve(&target)?.unwrap_or_else(|| target.clone());
    if final_target == root {
        return Err("所选位置会形成循环，未更改启动位置。".into());
    }
    link.target = target.clone();
    portable::write_json(&marker, &link)?;
    Ok(target)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn moved_library_can_be_relinked_but_replacement_incomplete_and_cyclic_libraries_cannot() {
        let root = std::env::temp_dir().join(uuid::Uuid::new_v4().to_string());
        let source = root.join("installed");
        let target = root.join("original");
        let moved = root.join("moved");
        std::fs::create_dir_all(&source).unwrap();
        std::fs::create_dir_all(target.join("userdata/data")).unwrap();
        std::fs::create_dir_all(target.join("app/build")).unwrap();
        std::fs::write(target.join("TrailSnap.exe"), b"fixture").unwrap();
        std::fs::write(target.join("userdata/data/trailsnap.sqlite"), b"fixture").unwrap();
        std::fs::write(target.join("userdata/library.json"), b"{}").unwrap();
        std::fs::write(target.join("app/build/manifest.json"), b"{}").unwrap();
        let mut config = serde_json::json!({"schemaVersion":1,"mode":"portable","instanceId":"original-id",
            "displayName":"fixture","activeBuild":"build","previousBuild":null,
            "dataRoot":{"kind":"relative","path":"userdata"},"serverPort":null,"fixedPort":false});
        portable::write_json(&target.join("instance.json"), &config).unwrap();
        activate(&source, &target).unwrap();
        std::fs::rename(&target, &moved).unwrap();
        assert!(resolve(&source).is_err());
        let before = std::fs::read(source.join("maintenance/library-link.json")).unwrap();
        config["instanceId"] = serde_json::json!("replacement");
        portable::write_json(&moved.join("instance.json"), &config).unwrap();
        assert!(relink(&source, &moved).is_err());
        assert_eq!(std::fs::read(source.join("maintenance/library-link.json")).unwrap(), before);
        config["instanceId"] = serde_json::json!("original-id");
        portable::write_json(&moved.join("instance.json"), &config).unwrap();
        std::fs::remove_file(moved.join("userdata/library.json")).unwrap();
        assert!(relink(&source, &moved).is_err());
        std::fs::write(moved.join("userdata/library.json"), b"{}").unwrap();
        portable::write_json(&moved.join("maintenance/library-link.json"), &serde_json::json!({"target":source,"instanceId":"source"})).unwrap();
        assert!(relink(&source, &moved).is_err());
        std::fs::remove_file(moved.join("maintenance/library-link.json")).unwrap();
        relink(&source, &moved).unwrap();
        assert_eq!(resolve(&source).unwrap().unwrap(), portable::clean_path(moved.canonicalize().unwrap()));
        std::fs::remove_dir_all(root).unwrap();
    }
    #[test]
    fn confirmed_link_is_persistent_and_rejects_missing_or_replaced_targets() {
        let root = std::env::temp_dir().join(uuid::Uuid::new_v4().to_string());
        let source = root.join("source");
        let target = root.join("target");
        std::fs::create_dir_all(&source).unwrap();
        std::fs::create_dir_all(target.join("userdata")).unwrap();
        std::fs::write(target.join("TrailSnap.exe"), b"fixture").unwrap();
        let config = portable::InstanceConfig {
            schema_version: 1,
            mode: "portable".into(),
            instance_id: "one".into(),
            display_name: "test".into(),
            active_build: "build".into(),
            previous_build: None,
            data_root: portable::DataRoot {
                kind: "relative".into(),
                path: "userdata".into(),
            },
            server_port: None,
            fixed_port: false,
        };
        portable::write_json(&target.join("instance.json"), &config).unwrap();
        assert!(resolve(&source).unwrap().is_none());
        activate(&source, &target).unwrap();
        assert_eq!(
            resolve(&source).unwrap().unwrap(),
            portable::clean_path(target.canonicalize().unwrap())
        );
        let mut changed = config;
        changed.instance_id = "another".into();
        portable::write_json(&target.join("instance.json"), &changed).unwrap();
        assert!(resolve(&source).is_err());
        std::fs::remove_dir_all(&target).unwrap();
        assert!(resolve(&source).unwrap_err().contains("未打开旧图库"));
        std::fs::remove_dir_all(root).unwrap();
    }
}
