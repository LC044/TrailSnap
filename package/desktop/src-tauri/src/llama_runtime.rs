use serde_json::{json, Value};
use std::{env, path::PathBuf, process::Command};

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

    known_locations(executable)
        .into_iter()
        .find(|candidate| candidate.is_file())
}

fn known_locations(executable: &str) -> Vec<PathBuf> {
    let mut locations = Vec::new();
    #[cfg(windows)]
    if let Some(root) = env::var_os("LOCALAPPDATA") {
        let winget = PathBuf::from(root).join("Microsoft").join("WinGet");
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
    let version = path
        .as_ref()
        .and_then(|executable| Command::new(executable).arg("--version").output().ok())
        .filter(|output| output.status.success())
        .map(|output| {
            let stdout = String::from_utf8_lossy(&output.stdout).trim().to_string();
            let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();
            if stdout.is_empty() {
                stderr
            } else {
                stdout
            }
        });
    let installed = path.is_some() && version.is_some();
    json!({
        "installed": installed,
        "path": path.map(|value| value.to_string_lossy().to_string()),
        "version": version,
        "installSupported": cfg!(windows) || cfg!(target_os = "macos"),
        "installCommand": if cfg!(windows) {
            "winget install --id ggml.llamacpp --exact"
        } else if cfg!(target_os = "macos") {
            "brew install llama.cpp"
        } else {
            "请按照 AI 服务 README 编译并将 llama-server 加入 PATH"
        },
    })
}

pub async fn install() -> Result<Value, String> {
    tauri::async_runtime::spawn_blocking(install_blocking)
        .await
        .map_err(|error| format!("llama.cpp 安装任务异常：{error}"))??;
    let result = status();
    if result["installed"].as_bool() != Some(true) {
        return Err("安装命令已结束，但未检测到可用的 llama-server".into());
    }
    Ok(result)
}

fn install_blocking() -> Result<(), String> {
    if find_llama_server().is_some() {
        return Ok(());
    }

    #[cfg(windows)]
    let mut command = {
        let mut command = Command::new("winget");
        command.args([
            "install",
            "--id",
            "ggml.llamacpp",
            "--exact",
            "--silent",
            "--accept-package-agreements",
            "--accept-source-agreements",
        ]);
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000);
        command
    };
    #[cfg(target_os = "macos")]
    let mut command = {
        let mut command = Command::new("brew");
        command.args(["install", "llama.cpp"]);
        command
    };
    #[cfg(not(any(windows, target_os = "macos")))]
    return Err("Linux 暂不支持一键安装，请按照 package/ai/README.md 编译 llama.cpp".into());

    #[cfg(any(windows, target_os = "macos"))]
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
