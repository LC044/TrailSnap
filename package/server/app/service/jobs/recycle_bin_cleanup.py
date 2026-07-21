"""定时回收站清理：永久删除超过保留天数的已删照片。

触发时机由 ``JobScheduler`` 根据 ``system_config.recycle_bin.cleanup_time``
拼成 ``"M H * * *"`` cron 表达式，每天固定时刻执行。
"""
import logging
from collections import defaultdict
from datetime import datetime, timedelta

from app.core.system_config import system_config
from app.db.session import SessionLocal
from app.db.models.photo import Photo

logger = logging.getLogger("app.service.jobs.recycle_bin_cleanup")


def recycle_bin_cleanup_job():
    retention_days = system_config.config.recycle_bin.retention_days
    cutoff = datetime.now() - timedelta(days=retention_days)
    db = SessionLocal()
    try:
        expired = db.query(Photo).filter(
            Photo.is_deleted == True,
            Photo.deleted_at <= cutoff
        ).all()
        if not expired:
            return
        from app.crud.photo import batch_delete_photos_db
        by_owner = defaultdict(list)
        for p in expired:
            by_owner[p.owner_id].append(p.id)
        total = 0
        for owner_id, photo_ids in by_owner.items():
            batch_delete_photos_db(db, photo_ids, is_delete_file=True, user_id=owner_id)
            total += len(photo_ids)
        logger.info(
            f"recycle_bin_cleanup_job: permanently deleted {total} photos "
            f"(older than {retention_days}d)."
        )
    except Exception as e:
        logger.error(f"recycle_bin_cleanup_job failed: {e}")
    finally:
        db.close()