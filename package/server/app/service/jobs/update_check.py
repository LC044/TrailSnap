"""定时版本更新检查：发现新版本时为所有用户写入 UPDATE 通知并推送。

调度由 ``JobScheduler`` 负责（默认每 6 小时一次），本函数仅作为
``UpdateCheckScheduler.tick()`` 的薄封装，便于在日志里区分是定时触发。
"""
import asyncio
import logging

from app.service.update_checker import UpdateCheckScheduler

logger = logging.getLogger("app.service.jobs.update_check")


def update_check_job():
    try:
        UpdateCheckScheduler().tick()
        # The phone is intentionally forbidden from reaching release hosts.
        # Keep the newest APK ready on this self-hosted Server instead.
        from app.service.app_update import prefetch_latest_app_update
        asyncio.run(prefetch_latest_app_update())
    except Exception as e:
        logger.error(f"update_check_job failed: {e}")
