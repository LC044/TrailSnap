//! Bounded process reaping after request writers and downloads have drained.
#[cfg(any(windows, test))]
use std::process::{Command, Stdio};
use std::{
    process::{Child, ExitStatus},
    time::{Duration, Instant},
};

fn wait(child: &mut Child, timeout: Duration) -> Result<ExitStatus, String> {
    let deadline = Instant::now() + timeout;
    loop {
        if let Some(status) = child.try_wait().map_err(|e| e.to_string())? {
            return Ok(status);
        }
        if Instant::now() >= deadline {
            return Err(format!("等待进程 {} 退出超时", child.id()));
        }
        std::thread::sleep(Duration::from_millis(20));
    }
}

pub fn stop(child: &mut Child) -> Result<(), String> {
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        // Do not wait on inherited output pipes. Bound both process waits.
        let mut helper = Command::new("taskkill")
            .args(["/pid", &child.id().to_string(), "/t", "/f"])
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .creation_flags(0x08000000)
            .spawn()
            .map_err(|e| format!("无法运行 taskkill：{e}"))?;
        let status = match wait(&mut helper, Duration::from_secs(5)) {
            Ok(status) => status,
            Err(error) => {
                let _ = helper.kill();
                let _ = wait(&mut helper, Duration::from_secs(1));
                return Err(error);
            }
        };
        if !status.success() {
            // Root exit alone cannot prove that all descendants stopped.
            return Err(format!(
                "无法确认进程树 {} 已停止：taskkill {status}",
                child.id()
            ));
        }
    }
    #[cfg(not(windows))]
    child.kill().map_err(|e| e.to_string())?;
    wait(child, Duration::from_secs(5)).map(|_| ())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    #[ignore = "subprocess fixture"]
    fn sleeping_child() {
        std::thread::sleep(Duration::from_secs(30));
    }

    fn sleeper() -> Child {
        let mut cmd = Command::new(std::env::current_exe().unwrap());
        cmd.args([
            "--exact",
            "process_shutdown::tests::sleeping_child",
            "--ignored",
        ])
        .stdout(Stdio::null())
        .stderr(Stdio::null());
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            cmd.creation_flags(0x08000000);
        }
        cmd.spawn().unwrap()
    }

    #[test]
    fn timeout_preserves_live_child_until_explicit_stop() {
        let mut child = sleeper();
        let result = wait(&mut child, Duration::from_millis(20));
        let alive = child.try_wait().unwrap().is_none();
        let stopped = stop(&mut child);
        assert!(result.unwrap_err().contains("退出超时"));
        assert!(alive);
        stopped.unwrap();
        assert!(child.try_wait().unwrap().is_some());
    }
}
