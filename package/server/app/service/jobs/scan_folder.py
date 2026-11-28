"""定时扫描任务：若没有进行中的 SCAN_FOLDER 任务则入队一个。

触发时机由 ``JobScheduler`` 解析 ``system_config.scan_schedule`` 的 cron
表达式决定；``mode='off'`` 时 job 不会被注册。
"""
import logging
import os
from datetime import datetime, timedelta

from app.core.system_config import system_config
from app.db.session import SessionLocal
from app.db.models.user import User
from app.service.gallery_sync import external_roots
from app.service.task_manager import TaskManager

logger = logging.getLogger("app.service.jobs.scan_folder")


def startup_scan_enabled() -> bool:
    return os.getenv("TS_DESKTOP_VERIFY") != "1" and system_config.config.scan_on_startup


def schedule_startup_scan(job_scheduler):
    if not startup_scan_enabled():
        return

    def run():
        if not startup_scan_folder_job():
            schedule(10)

    def schedule(delay):
        job_scheduler.register_once_job(
            "scan_folder_startup", datetime.now() + timedelta(seconds=delay), run,
        )

    schedule(30)


def startup_scan_folder_job() -> bool:
    """Return whether startup import is covered or needs no further attempt."""
    if not startup_scan_enabled():
        return True
    try:
        with SessionLocal() as db:
            if any(external_roots(user) for user in db.query(User).all()):
                return TaskManager.get_instance().try_enqueue_gallery_scan(db, {"import_only": True})
    except Exception:
        logger.exception("Failed to enqueue the startup gallery scan")
        return False
    return True


def scan_folder_job():
    try:
        with SessionLocal() as db:
            if TaskManager.get_instance().try_enqueue_gallery_scan(db, {}):
                logger.info("scan_folder_job: enqueued SCAN_FOLDER task.")
            else:
                logger.info("scan_folder_job: SCAN_FOLDER already pending/processing, skipping.")
    except Exception:
        logger.exception("Scheduled gallery scan failed")
