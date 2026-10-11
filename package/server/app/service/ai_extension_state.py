"""Desktop extension availability is independent of the user's pause choices."""
import os
import re

from app.db.models.task import Task, TaskStatus, TaskType

STATE_KEY = "desktop_ai_extension_state"
# Raise this only when Server needs an AI API unavailable in older extensions.
# Unlike the product version, it is not bumped for every release.
MINIMUM_AI_EXTENSION_VERSION = "0.17.3"
LOCAL_TYPES = {
    TaskType.CLASSIFY_IMAGE, TaskType.RECOGNIZE_FACE, TaskType.RECOGNIZE_TICKET,
    TaskType.OCR, TaskType.IMAGE_EMBEDDING,
}
WAIT_INSTALL = "等待安装 AI 扩展"
WAIT_UPDATE = "等待 AI 扩展更新"


def meets_server_minimum(installed_version):
    """The Server minimum is a stable release; prereleases rank below it."""
    parsed = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)(-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?", installed_version or "")
    minimum = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", MINIMUM_AI_EXTENSION_VERSION)
    if not parsed or not minimum:
        return None
    current = tuple(map(int, parsed.group(1, 2, 3)))
    required = tuple(map(int, minimum.group(1, 2, 3)))
    return current > required or (current == required and not parsed.group(4))


def wait_reason(state):
    if os.environ.get("TS_DESKTOP") != "1" or state == "ready":
        return None
    return WAIT_INSTALL if state == "missing" else WAIT_UPDATE


def requires_extension(task_type, owner_id, db):
    if task_type in LOCAL_TYPES:
        return True
    if task_type == TaskType.VISUAL_DESCRIPTION:
        from app.core.config_manager import config_manager
        return config_manager.get_user_config(owner_id, db).ai.analysis_connection_id == "builtin"
    return False


def apply_wait_state(db, state):
    """Only pending rows change; inference and result commits finish normally."""
    reason = wait_reason(state)
    query = db.query(Task).filter(Task.status == TaskStatus.PENDING)
    if reason:
        query.filter(Task.type.in_(list(LOCAL_TYPES))).filter(
            (Task.error.is_(None)) | (Task.error != reason)
        ).update({Task.error: reason, Task.next_retry_at: None}, synchronize_session=False)
        for task in query.filter(Task.type == TaskType.VISUAL_DESCRIPTION).all():
            if requires_extension(task.type, task.owner_id, db):
                task.error = reason
                task.next_retry_at = None
    else:
        query.filter(Task.error.in_([WAIT_INSTALL, WAIT_UPDATE])).update(
            {Task.error: None, Task.next_retry_at: None}, synchronize_session=False,
        )
    db.commit()
