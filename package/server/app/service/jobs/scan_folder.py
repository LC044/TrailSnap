"""定时扫描任务：若没有进行中的 SCAN_FOLDER 任务则入队一个。

触发时机由 ``JobScheduler`` 解析 ``system_config.scan_schedule`` 的 cron
表达式决定；``mode='off'`` 时 job 不会被注册。
"""
import logging

from app.db.session import SessionLocal
from app.db.models.task import Task, TaskType, TaskStatus
from app.service.task_manager import TaskManager

logger = logging.getLogger("app.service.jobs.scan_folder")


def scan_folder_job():
    db = SessionLocal()
    try:
        existing = db.query(Task).filter(
            Task.type == TaskType.SCAN_FOLDER,
            Task.status.in_([TaskStatus.PENDING, TaskStatus.PROCESSING])
        ).first()
        if existing:
            logger.info("scan_folder_job: SCAN_FOLDER already pending/processing, skipping.")
            return
        TaskManager.get_instance().add_task(db, TaskType.SCAN_FOLDER, {})
        logger.info("scan_folder_job: enqueued SCAN_FOLDER task.")
    except Exception as e:
        logger.error(f"scan_folder_job failed: {e}")
    finally:
        db.close()