#[cfg(windows)]
use futures_util::StreamExt;
use serde_json::{json, Value};
#[cfg(windows)]
use sha2::{Digest, Sha256};
#[cfg(not(windows))]
use std::process::Command;
use std::{env, path::PathBuf};
#[cfg(windows)]
use std::{
    fs,
    io::{self, Write},
    path::Path,
};

#[cfg(windows)]
const LLAMA_BUILD: &str = "b9354";

#[cfg(windows)]
fn managed_runtime_root() -> Option<PathBuf> {
    env::var_os("LOCALAPPDATA")
        .map(PathBuf::from)
        .map(|path| path.join("TrailSnap").join("runtime").join("llama.cpp"))
}

pub fn find_llama_server() -> Option<PathBuf> {
    if let Some(path) = env::var_os("LLAMA_SERVER_PATH").map(PathBuf::from) {
        if path.is_file() {
            return Some(path);
        }
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
    if let Some(local_app_data) = env::var_os("LOCALAPPDATA") {
        let local_app_data = PathBuf::from(local_app_data);
        locations.push(
            local_app_data
                .join("TrailSnap")
                .join("runtime")
                .join("llama.cpp")
                .join(LLAMA_BUILD)
                .join(executable),
        );
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
        "installSupported": cfg!(windows) || cfg!(target_os = "macos"),
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
        tauri::async_runtime::spawn_blocking(install_blocking)
            .await
            .map_err(|error| format!("llama.cpp 安装任务异常：{error}"))??;
    }
    let result = status();
    if result["installed"].as_bool() != Some(true) {
        return Err("安装命令已结束，但未检测到可用的 llama-server".into());
    }
    Ok(result)
}

#[cfg(not(windows))]
fn install_blocking() -> Result<(), String> {
    if find_llama_server().is_some() {
        return Ok(());
    }

    #[cfg(target_os = "macos")]
    let mut command = {
        let mut command = Command::new("brew");
        command.args(["install", "llama.cpp"]);
        command
    };
    #[cfg(not(target_os = "macos"))]
    return Err("Linux 暂不支持一键安装，请按照 package/ai/README.md 编译 llama.cpp".into());

    #[cfg(target_os = "macos")]
    {
        let output = command
            .output()
            .map_err(|error| format!("无法启动 llama.cpp 安装程序：{error}"))?;
        if output.status.success() {
            return Ok(());
        }
        let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();
        let stdout = String::from_utf8_lossy(&output.stdout).trim().to_string();
        Err(format!(
            "llama.cpp 安装失败：{}",
            if stderr.is_empty() { stdout } else { stderr }
        ))
    }
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
    let root = managed_runtime_root().ok_or_else(|| "无法读取 LOCALAPPDATA".to_string())?;
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

#[cfg(windows)]
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
