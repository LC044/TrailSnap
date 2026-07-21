"""版本更新检查 + 由 ``JobScheduler`` 触发的执行体。

- ``fetch_remote_update_info()``：从远端 ``version.json`` 拉取并解析，被
  ``app/api/system.py`` 的 ``/api/system/update-check`` 端点和
  ``UpdateCheckScheduler`` 复用。
- ``UpdateCheckScheduler``：无自带线程，由 ``app/service/jobs/update_check.py``
  在 APScheduler 触发的间隔里调用 ``tick()``。检测到的新版本既高于当前
  ``VERSION`` 也高于 ``SystemState('last_notified_update_version')`` 时，
  遍历所有用户写入 ``Notification(type=UPDATE)`` 并通过 ``NotificationManager``
  实时推送。
"""
import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, Optional

import aiohttp

from app.core.config_manager import VERSION
from app.db.session import SessionLocal
from app.crud import notification as crud_notification
from app.crud import user as crud_user
from app.db.models.notification import NotificationType, NotificationLevel
from app.db.models.system import SystemState
from app.service.notification_manager import NotificationManager

logger = logging.getLogger("app.service.update_checker")

# 远端版本清单 URL（与 system.py 中保持一致）
DEFAULT_UPDATE_URL = "https://trailsnap.cn/version.json"

# SystemState key：记录「已通知过的最高远端版本」，用于去重
LAST_NOTIFIED_KEY = "last_notified_update_version"


def compare_versions(v1: str, v2: str) -> int:
    """比较两个语义化版本字符串。返回 1 / -1 / 0。"""
    if not v1 or not v2:
        return 0
    try:
        parts1 = [int(x) for x in v1.split('.')]
        parts2 = [int(x) for x in v2.split('.')]
        length = max(len(parts1), len(parts2))
        parts1.extend([0] * (length - len(parts1)))
        parts2.extend([0] * (length - len(parts2)))
        for i in range(length):
            if parts1[i] > parts2[i]:
                return 1
            if parts1[i] < parts2[i]:
                return -1
    except ValueError:
        logger.warning(f"Invalid version format: v1={v1}, v2={v2}")
    return 0


async def fetch_remote_update_info(
    url: str = DEFAULT_UPDATE_URL,
    current_version: str = VERSION,
    timeout: float = 5.0,
) -> Optional[Dict[str, Any]]:
    """拉取远端版本清单并解析。

    返回与 ``/api/system/update-check`` 一致的字典结构：
        ``{latest_version, has_update, update_info, download_url}``

    网络失败 / 解析失败时返回 ``None``。
    """
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=timeout) as response:
                if response.status != 200:
                    logger.error(f"Update check HTTP {response.status}: {url}")
                    return None
                remote_data = await response.json()
        if not isinstance(remote_data, list) or not remote_data:
            logger.warning("Update check: empty or invalid remote payload")
            return None
        latest_version = remote_data[-1].get("version", "")
        download_url = remote_data[-1].get("download_url")
        update_info = ""
        for item in remote_data:
            if compare_versions(item.get("version", ""), current_version) > 0:
                update_info += f"<br>{item['version']}:<br>{item.get('update_info', '')}<br>"
        update_info = update_info.strip().strip("<br>")
        return {
            "latest_version": latest_version,
            "has_update": compare_versions(latest_version, current_version) > 0,
            "update_info": update_info,
            "download_url": download_url,
        }
    except Exception as e:
        logger.error(f"Update check failed: {e}")
        return None


class UpdateCheckScheduler:
    """版本更新检查的执行体（无自带线程）。

    由 ``JobScheduler`` 按 interval / cron 调用 ``tick()``：
    - 若远端版本高于 ``VERSION`` 且高于 ``SystemState`` 中记录的上次通知版本，
      则为每个用户写入一条 ``Notification(type=UPDATE)`` 并通过
      ``NotificationManager`` 实时推送。
    - 去重记录只在成功写入通知后才更新，避免重复刷屏。

    APScheduler 触发 ``tick()`` 时，调度线程里没有运行中的 event loop，
    因此内部用 ``asyncio.run`` 跑 aiohttp 请求；不要在已有 event loop
    的协程里直接调用本方法（测试时通过 ``threading.Thread`` 间接调用）。
    """

    def __init__(self, url: str = DEFAULT_UPDATE_URL):
        self.url = url

    def tick(self):
        try:
            info = asyncio.run(fetch_remote_update_info(url=self.url))
        except Exception as e:
            logger.error(f"fetch_remote_update_info failed: {e}")
            return
        if info is None:
            return
        if not info.get("has_update"):
            return
        remote_version = info.get("latest_version") or ""
        if not remote_version:
            return

        # SystemState 去重：只在「新版本确实没通知过」时写入
        last_notified = _load_last_notified()
        if last_notified and compare_versions(remote_version, last_notified) <= 0:
            return

        # 给所有用户各写一条 UPDATE 通知 + 推送
        db = SessionLocal()
        try:
            users = crud_user.get_all_users(db)
            if not users:
                logger.debug("Update-check: no users in DB, skipping notification.")
                return
            title = f"新版本可用：v{remote_version}"
            body = {
                "current_version": VERSION,
                "latest_version": remote_version,
                "update_info": info.get("update_info", ""),
                "download_url": info.get("download_url"),
            }
            manager = NotificationManager.get_instance()
            created_count = 0
            for u in users:
                try:
                    n = crud_notification.create_notification(
                        db,
                        user_id=u.id,
                        type=NotificationType.UPDATE.value,
                        level=NotificationLevel.INFO.value,
                        title=title,
                        body=body,
                        ref_type="release",
                        ref_id=remote_version,
                    )
                    manager.publish_to_user(u.id, "notification.created", crud_notification._serialize(n))
                    created_count += 1
                except Exception as e:
                    logger.debug(f"Failed to create update notification for {u.id}: {e}")
            db.commit()
            if created_count:
                logger.info(
                    f"Update-check notified {created_count} user(s) about v{remote_version}."
                )
                _save_last_notified(remote_version)
        finally:
            db.close()


def _load_last_notified() -> Optional[str]:
    """读取 SystemState 中记录的「已通知过的最高远端版本」。"""
    try:
        db = SessionLocal()
        try:
            row = db.query(SystemState).filter(SystemState.key == LAST_NOTIFIED_KEY).first()
            if row and row.value:
                return row.value
        finally:
            db.close()
    except Exception as e:
        logger.debug(f"_load_last_notified failed: {e}")
    return None


def _save_last_notified(version: str):
    """持久化「已通知过的最高远端版本」，用于下次去重。"""
    try:
        db = SessionLocal()
        try:
            row = db.query(SystemState).filter(SystemState.key == LAST_NOTIFIED_KEY).first()
            if row:
                row.value = version
            else:
                db.add(SystemState(key=LAST_NOTIFIED_KEY, value=version))
            db.commit()
        finally:
            db.close()
    except Exception as e:
        logger.debug(f"_save_last_notified failed: {e}")