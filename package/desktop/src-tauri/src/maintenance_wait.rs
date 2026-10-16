//! A bounded UI wait around a shutdown task which must keep its writer ownership.
use std::time::Duration;
use tokio::sync::watch;

pub const PENDING: &str = "后台任务仍在结束，尚未开始复制。请保持窗口和磁盘连接，稍后点击“继续等待”；不会强制结束正在写入的任务。";

pub struct Drain {
    purpose: String,
    pub receiver: watch::Receiver<Option<Result<(), String>>>,
}

impl Drain {
    pub fn new(purpose: &str, receiver: watch::Receiver<Option<Result<(), String>>>) -> Self {
        Self { purpose: purpose.into(), receiver }
    }

    pub fn for_operation(&self, purpose: &str) -> Result<watch::Receiver<Option<Result<(), String>>>, String> {
        if self.purpose != purpose {
            return Err("正在处理另一个图库操作，请等待其结束并重启后重试。".into());
        }
        Ok(self.receiver.clone())
    }
}

pub async fn wait(
    mut receiver: watch::Receiver<Option<Result<(), String>>>,
    timeout: Duration,
) -> Result<(), String> {
    tokio::time::timeout(timeout, async {
        loop {
            if let Some(result) = receiver.borrow().clone() {
                return result;
            }
            receiver.changed().await.map_err(|_| "等待服务结束的连接已中断，请保留图库并检查日志".to_string())?;
        }
    }).await.map_err(|_| PENDING.to_string())?
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn another_operation_cannot_reuse_pending_or_completed_shutdown_permission() {
        let (sender, receiver) = watch::channel(None);
        let drain = Drain::new("import:one", receiver);
        assert!(drain.for_operation("import:one").is_ok());
        assert!(drain.for_operation("update").is_err());
        assert!(drain.for_operation("import:two").is_err());
        sender.send(Some(Ok(()))).unwrap();
        assert!(drain.for_operation("import:one").is_ok());
        assert!(drain.for_operation("update").is_err());
    }

    #[tokio::test]
    async fn timeout_does_not_cancel_writer_and_a_later_wait_can_finish() {
        let (sender, receiver) = watch::channel(None);
        assert_eq!(wait(receiver.clone(), Duration::from_millis(5)).await.unwrap_err(), PENDING);
        // The sender still owns the drain; no new drain/copy is started on retry.
        sender.send(Some(Ok(()))).unwrap();
        assert!(wait(receiver, Duration::from_millis(5)).await.is_ok());
    }

    #[tokio::test]
    async fn completed_failure_is_preserved_for_every_waiter() {
        let (_sender, receiver) = watch::channel(Some(Err("worker failed".into())));
        assert_eq!(wait(receiver.clone(), Duration::from_millis(5)).await.unwrap_err(), "worker failed");
        assert_eq!(wait(receiver, Duration::from_millis(5)).await.unwrap_err(), "worker failed");
    }
}
