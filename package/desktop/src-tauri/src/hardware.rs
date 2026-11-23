//! Local capability checks used to pick release assets before downloading them.
use std::{ffi::OsStr, time::Duration};
use tokio::{process::Command, time::timeout};

pub async fn probe(program: impl AsRef<OsStr>, args: &[&str], seconds: u64) -> Option<String> {
    let mut command = Command::new(program);
    command.args(args).kill_on_drop(true);
    #[cfg(windows)]
    command.creation_flags(0x08000000);
    let output = timeout(Duration::from_secs(seconds), command.output())
        .await
        .ok()?
        .ok()?;
    if !output.status.success() {
        return None;
    }
    Some(format!(
        "{}\n{}",
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    ))
}

#[cfg(not(target_os = "macos"))]
pub async fn cuda_devices() -> Option<String> {
    let args = [
        "--query-gpu=driver_version,compute_cap",
        "--format=csv,noheader",
    ];
    let result = probe("nvidia-smi", &args, 5).await;
    #[cfg(windows)]
    if result.is_none() {
        if let Some(windows) = std::env::var_os("SystemRoot") {
            let program = std::path::PathBuf::from(windows).join("System32/nvidia-smi.exe");
            return probe(program, &args, 5).await;
        }
    }
    result
}

#[cfg(any(not(target_os = "macos"), test))]
pub fn cuda_compatible(output: &str, driver_min: u32, compute_min: (u32, u32)) -> bool {
    output.lines().any(|line| {
        let Some((driver, compute)) = line.split_once(',') else {
            return false;
        };
        let major_driver = driver
            .trim()
            .split('.')
            .next()
            .and_then(|value| value.parse::<u32>().ok());
        let capability = compute.trim().split_once('.').and_then(|(major, minor)| {
            Some((major.parse::<u32>().ok()?, minor.parse::<u32>().ok()?))
        });
        major_driver.is_some_and(|driver| driver >= driver_min)
            && capability.is_some_and(|compute| compute >= compute_min)
    })
}

#[cfg(windows)]
pub async fn display_devices() -> String {
    let script = "Get-CimInstance Win32_PnPEntity -Filter 'ConfigManagerErrorCode = 0' | Select-Object PNPClass, PNPDeviceID, Name | ConvertTo-Json -Compress";
    let Some(windows) = std::env::var_os("SystemRoot") else {
        return String::new();
    };
    let path =
        std::path::PathBuf::from(windows).join("System32/WindowsPowerShell/v1.0/powershell.exe");
    probe(
        path,
        &["-NoProfile", "-NonInteractive", "-Command", script],
        12,
    )
    .await
    .unwrap_or_default()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn cuda_requires_a_compatible_driver_and_gpu() {
        assert!(cuda_compatible("551.61, 8.6\n", 528, (6, 0)));
        assert!(cuda_compatible("580.10, 6.1\n580.10, 8.6\n", 580, (7, 5)));
        assert!(!cuda_compatible(
            "527.99, 8.6\n580.10, 6.1\nN/A, N/A",
            528,
            (7, 5)
        ));
    }
}
