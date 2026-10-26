"""Migration of obsolete extension waits to the bundled desktop runtime."""
from sqlalchemy import delete, update

from app.db.models.task import Task, TaskStatus
from app.db.models.system import SystemState


def recover_legacy_extension_waits(db):
    # Only obsolete extension errors are cleared. User pauses, attempts, models,
    # results and genuine inference failures are left intact.
    result = db.execute(update(Task).where(
        Task.status == TaskStatus.PENDING,
        Task.error.in_(["等待安装 AI 扩展", "等待 AI 扩展更新"]),
    ).values(error=None, next_retry_at=None))
    db.execute(delete(SystemState).where(SystemState.key == "desktop_ai_extension_state"))
    db.commit()
    return result.rowcount
