use futures_util::StreamExt;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
#[cfg(not(windows))]
use std::process::Command;
use std::{env, path::PathBuf};
use std::{
    fs,
    io::{self, Write},
    path::Path,
};

const LLAMA_BUILD: &str = "b9354";

fn managed_runtime_root() -> Option<PathBuf> {
    env::var_os("TS_DESKTOP_ROOT")
        .map(PathBuf::from)
        .map(|path| path.join("runtime").join("llama.cpp"))
}

pub fn find_llama_server() -> Option<PathBuf> {
    if let Some(path) = env::var_os("LLAMA_SERVER_PATH").map(PathBuf::from) {
        if path.is_file() {
            return Some(path);
        }
    }

    if let Some(root) = managed_runtime_root() {
        return find_file_named(&root.join(LLAMA_BUILD), if cfg!(windows) { "llama-server.exe" } else { "llama-server" });
    }

    let executable = if cfg!(windows) {
        "llama-server.exe"
    } else {
        "llama-server"
    };
    if let Some(path) = env::var_os("PATH") {
        for directory in env::split_paths(&path) {
            let candidate = directory.join(executable);
            if candidate.is_file() {
                return Some(candidate);
            }
        }
    }

    let resolved = known_locations(executable)
        .into_iter()
        .find(|candidate| candidate.is_file());
    if resolved.is_some() {
        return resolved;
    }
    #[cfg(windows)]
    if let Some(root) = managed_runtime_root() {
        return find_file_named(&root, executable);
    }
    None
}

fn known_locations(executable: &str) -> Vec<PathBuf> {
    let mut locations = Vec::new();
    #[cfg(windows)]
    if let Some(root) = managed_runtime_root() {
        locations.push(root.join(LLAMA_BUILD).join(executable));
    }
    #[cfg(windows)]
    if let Some(local_app_data) = env::var_os("LOCALAPPDATA") {
        let local_app_data = PathBuf::from(local_app_data);
        let winget = local_app_data.join("Microsoft").join("WinGet");
        locations.push(winget.join("Links").join(executable));
        let packages = winget.join("Packages");
        if let Ok(entries) = std::fs::read_dir(packages) {
            for entry in entries.flatten() {
                if entry
                    .file_name()
                    .to_string_lossy()
                    .starts_with("ggml.llamacpp_")
                {
                    locations.push(entry.path().join(executable));
                }
            }
        }
    }
    #[cfg(target_os = "macos")]
    {
        locations.push(std::path::Path::new("/opt/homebrew/bin").join(executable));
        locations.push(std::path::Path::new("/usr/local/bin").join(executable));
    }
    #[cfg(target_os = "linux")]
    {
        locations.push(std::path::Path::new("/usr/local/bin").join(executable));
        locations.push(std::path::Path::new("/usr/bin").join(executable));
        locations.push(std::path::Path::new("/home/linuxbrew/.linuxbrew/bin").join(executable));
    }
    locations
}

pub fn status() -> Value {
    let path = find_llama_server();
    // Automatic status checks run when the settings page opens and polls.
    // Starting llama-server just to read --version is expensive on some
    // machines and briefly creates a console window on Windows. A resolved
    // executable is sufficient here; the real process is still validated when
    // the AI service launches it for inference.
    let installed = path.is_some();
    json!({
        "installed": installed,
        "path": path.map(|value| value.to_string_lossy().to_string()),
        "version": Value::Null,
        "installSupported": true,
        "installCommand": if cfg!(windows) {
            "由 TrailSnap 从 llama.cpp 官方 GitHub Release 直接下载安装，不依赖 winget"
        } else if cfg!(target_os = "macos") {
            "brew install llama.cpp"
        } else {
            "请按照 AI 服务 README 编译并将 llama-server 加入 PATH"
        },
    })
}

pub async fn install() -> Result<Value, String> {
    if find_llama_server().is_none() {
        #[cfg(windows)]
        install_windows().await?;
        #[cfg(not(windows))]
        install_unix().await?;
    }
    let result = status();
    if result["installed"].as_bool() != Some(true) {
        return Err("安装命令已结束，但未检测到可用的 llama-server".into());
    }
    Ok(result)
}

#[cfg(not(windows))]
async fn install_unix() -> Result<(), String> {
    let (suffix, expected) = match (env::consts::OS, env::consts::ARCH) {
        ("macos", "aarch64") => ("macos-arm64", "fc86d461ad07b997ea8b9cdcc4458cf24943edd2f8ea06bdea7ffefc1d1176c3"),
        ("macos", "x86_64") => ("macos-x64", "589bb21149ff8a85d48fdfdabfaf08bc81ae27dd2852feac1d77a7a120b8b46f"),
        ("linux", "aarch64") => ("ubuntu-arm64", "edd18beb62f8798a7f6d0021a293be53c460a6a67c86cfdf72d1ab568c1c2968"),
        ("linux", "x86_64") => ("ubuntu-x64", "aa6195414b139b28591a8b207f2db9fcde2bb5791e8c694bdf450cff7ef87d02"),
        _ => return Err("当前系统暂不支持自动准备本地推理环境".into()),
    };
    let root = managed_runtime_root().ok_or("无法读取行影集数据目录")?;
    fs::create_dir_all(&root).map_err(|e| e.to_string())?;
    let token = uuid::Uuid::new_v4();
    let archive = root.join(format!(".{token}.download"));
    let staging = root.join(format!(".{token}.staging"));
    let target = root.join(LLAMA_BUILD);
    let result = async {
        let url = format!("https://github.com/ggml-org/llama.cpp/releases/download/{LLAMA_BUILD}/llama-{LLAMA_BUILD}-bin-{suffix}.tar.gz");
        let response = reqwest::Client::builder().connect_timeout(std::time::Duration::from_secs(20))
            .timeout(std::time::Duration::from_secs(900)).build().map_err(|e| e.to_string())?
            .get(url).header("User-Agent", "TrailSnap Desktop").send().await.map_err(|e| e.to_string())?
            .error_for_status().map_err(|e| e.to_string())?;
        let mut file = fs::File::create(&archive).map_err(|e| e.to_string())?;
        let mut digest = Sha256::new();
        let mut stream = response.bytes_stream();
        while let Some(chunk) = stream.next().await {
            let chunk = chunk.map_err(|e| e.to_string())?;
            digest.update(&chunk);
            file.write_all(&chunk).map_err(|e| e.to_string())?;
        }
        file.sync_all().map_err(|e| e.to_string())?;
        drop(file);
        if format!("{:x}",digest.finalize()) != expected { return Err("本地推理环境校验失败，请重试".into()); }
        let input = archive.clone();
        let destination = staging.clone();
        tauri::async_runtime::spawn_blocking(move || -> Result<(), String> {
            let file = fs::File::open(input).map_err(|e| e.to_string())?;
            let mut tar = tar::Archive::new(flate2::read::GzDecoder::new(file));
            for entry in tar.entries().map_err(|e| e.to_string())? {
                if !entry.map_err(|e| e.to_string())?.unpack_in(&destination).map_err(|e| e.to_string())? {
                    return Err("本地推理环境文件路径无效".into());
                }
            }
            Ok(())
        }).await.map_err(|e| e.to_string())??;
        let executable = find_file_named(&staging, "llama-server").ok_or("本地推理环境文件不完整")?;
        let output = Command::new(executable).arg("--version").output().map_err(|e| e.to_string())?;
        if !output.status.success() { return Err("本地推理环境与当前系统不兼容".into()); }
        if target.exists() { fs::rename(&target, root.join(format!(".{token}.previous"))).map_err(|e| e.to_string())?; }
        fs::rename(&staging,&target).map_err(|e| e.to_string())?;
        Ok(())
    }.await;
    let _ = fs::remove_file(&archive);
    if staging.exists() { let _ = fs::remove_dir_all(&staging); }
    result
}

#[cfg(windows)]
fn windows_asset() -> Result<(String, &'static str), String> {
    let (architecture, sha256) = match env::consts::ARCH {
        "x86_64" => (
            "x64",
            "5fb1573fdf4eac5bc9f3c3b88facc7abcbb4c14b21027ca09e0900dc071171cf",
        ),
        "aarch64" => (
            "arm64",
            "39e4f78580443293a6f71c7ba00edfb66b4c5b31fe25e4b426ea64cd2bf8fd03",
        ),
        other => {
            return Err(format!(
                "当前 Windows 架构暂不支持自动安装 llama.cpp：{other}"
            ))
        }
    };
    Ok((
        format!("llama-{LLAMA_BUILD}-bin-win-cpu-{architecture}.zip"),
        sha256,
    ))
}

#[cfg(windows)]
async fn install_windows() -> Result<(), String> {
    let root = managed_runtime_root().ok_or_else(|| "无法读取桌面数据目录".to_string())?;
    fs::create_dir_all(&root).map_err(|error| format!("无法创建 llama.cpp 运行时目录：{error}"))?;
    let (asset, expected_sha256) = windows_asset()?;
    let url =
        format!("https://github.com/ggml-org/llama.cpp/releases/download/{LLAMA_BUILD}/{asset}");
    let archive_path = root.join(format!(".{LLAMA_BUILD}-{}.zip", std::process::id()));
    let staging_dir = root.join(format!(".{LLAMA_BUILD}-{}-staging", std::process::id()));
    let final_dir = root.join(LLAMA_BUILD);
    let _ = fs::remove_file(&archive_path);
    let _ = fs::remove_dir_all(&staging_dir);

    let result = async {
        let response = reqwest::Client::builder()
            .connect_timeout(std::time::Duration::from_secs(20))
            .timeout(std::time::Duration::from_secs(15 * 60))
            .build()
            .map_err(|error| format!("无法创建下载客户端：{error}"))?
            .get(&url)
            .header(reqwest::header::USER_AGENT, "TrailSnap Desktop")
            .send()
            .await
            .map_err(|error| format!("下载 llama.cpp 失败：{error}"))?
            .error_for_status()
            .map_err(|error| format!("下载 llama.cpp 失败：{error}"))?;
        let mut output = fs::File::create(&archive_path)
            .map_err(|error| format!("无法创建 llama.cpp 下载文件：{error}"))?;
        let mut hasher = Sha256::new();
        let mut stream = response.bytes_stream();
        while let Some(chunk) = stream.next().await {
            let chunk = chunk.map_err(|error| format!("下载 llama.cpp 中断：{error}"))?;
            hasher.update(&chunk);
            output
                .write_all(&chunk)
                .map_err(|error| format!("写入 llama.cpp 下载文件失败：{error}"))?;
        }
        output
            .sync_all()
            .map_err(|error| format!("保存 llama.cpp 下载文件失败：{error}"))?;
        let actual_sha256 = format!("{:x}", hasher.finalize());
        if actual_sha256 != expected_sha256 {
            return Err("llama.cpp 下载包校验失败，请稍后重试".into());
        }

        let archive = archive_path.clone();
        let staging = staging_dir.clone();
        tauri::async_runtime::spawn_blocking(move || extract_zip(&archive, &staging))
            .await
            .map_err(|error| format!("llama.cpp 解压任务异常：{error}"))??;
        if find_file_named(&staging_dir, "llama-server.exe").is_none() {
            return Err("下载包中没有找到 llama-server.exe".into());
        }
        if final_dir.exists() {
            fs::remove_dir_all(&final_dir)
                .map_err(|error| format!("无法替换旧 llama.cpp 运行时：{error}"))?;
        }
        fs::rename(&staging_dir, &final_dir)
            .map_err(|error| format!("无法启用 llama.cpp 运行时：{error}"))?;
        Ok(())
    }
    .await;

    let _ = fs::remove_file(archive_path);
    if result.is_err() {
        let _ = fs::remove_dir_all(staging_dir);
    }
    result
}

#[cfg(windows)]
fn extract_zip(archive_path: &Path, destination: &Path) -> Result<(), String> {
    fs::create_dir_all(destination).map_err(|error| format!("无法创建解压目录：{error}"))?;
    let archive =
        fs::File::open(archive_path).map_err(|error| format!("无法打开下载包：{error}"))?;
    let mut zip =
        zip::ZipArchive::new(archive).map_err(|error| format!("下载包格式无效：{error}"))?;
    for index in 0..zip.len() {
        let mut entry = zip
            .by_index(index)
            .map_err(|error| format!("读取下载包失败：{error}"))?;
        let Some(relative) = entry.enclosed_name() else {
            continue;
        };
        let output_path = destination.join(relative);
        if entry.is_dir() {
            fs::create_dir_all(&output_path)
                .map_err(|error| format!("创建解压目录失败：{error}"))?;
            continue;
        }
        if let Some(parent) = output_path.parent() {
            fs::create_dir_all(parent).map_err(|error| format!("创建解压目录失败：{error}"))?;
        }
        let mut output =
            fs::File::create(&output_path).map_err(|error| format!("创建解压文件失败：{error}"))?;
        io::copy(&mut entry, &mut output)
            .map_err(|error| format!("解压 llama.cpp 失败：{error}"))?;
    }
    Ok(())
}

fn find_file_named(root: &Path, name: &str) -> Option<PathBuf> {
    let entries = fs::read_dir(root).ok()?;
    for entry in entries.flatten() {
        let path = entry.path();
        if path.is_file()
            && entry
                .file_name()
                .to_string_lossy()
                .eq_ignore_ascii_case(name)
        {
            return Some(path);
        }
        if path.is_dir() {
            if let Some(found) = find_file_named(&path, name) {
                return Some(found);
            }
        }
    }
    None
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn status_exposes_install_contract() {
        let value = status();
        assert!(value.get("installed").is_some());
        assert!(value.get("installSupported").is_some());
        assert!(value.get("installCommand").is_some());
    }
}
