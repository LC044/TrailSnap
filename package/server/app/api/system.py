from fastapi import APIRouter, Depends, HTTPException
from app.core.system_config import system_config
from app.api.deps import get_current_user
from app.db.models.user import User
from app.service.update_checker import fetch_remote_update_info
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/config")
def get_system_config(current_user: User = Depends(get_current_user)):
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Not authorized")
    return system_config.config.model_dump()

@router.put("/config")
def update_system_config(payload: dict, current_user: User = Depends(get_current_user)):
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Update system config
    current_config = system_config.config.model_dump()
    for key, value in payload.items():
        if key in current_config and isinstance(value, dict) and isinstance(current_config[key], dict):
            current_config[key].update(value)
        else:
            current_config[key] = value

    # Re-initialize the model to validate and save
    from app.core.system_config import SystemSettings
    system_config.config = SystemSettings(**current_config)
    system_config.save()
    # Consumer semaphores and process/thread pools are created in the worker
    # process. Restart it so a changed concurrency profile takes effect now.
    apply_status = {"status": "applied"}
    if "task" in payload:
        from app.service.task_manager import TaskManager
        apply_status = TaskManager.get_instance().restart_worker(graceful=True)
    return {
        "status": "success",
        "config": system_config.config.model_dump(),
        "apply": apply_status,
    }

# ``compare_versions`` 与 ``fetch_remote_update_info`` 都搬到
# ``app.service.update_checker`` 了，便于 ``UpdateCheckScheduler`` 共用。

@router.get("/version")
def get_version():
    from app.core.config_manager import VERSION
    return {"version": VERSION}

@router.get("/update-check")
async def check_update():
    """手动触发版本检查。实现细节统一在 ``app.service.update_checker``，
    ``UpdateCheckScheduler`` 复用同一段 fetch/parse 逻辑。"""
    from app.core.config_manager import VERSION
    current_version = VERSION
    info = await fetch_remote_update_info(current_version=current_version)
    if info is None:
        return {
            "current_version": current_version,
            "latest_version": None,
            "has_update": False,
            "error": "Failed to check for updates",
        }
    return {
        "current_version": current_version,
        "latest_version": info.get("latest_version"),
        "has_update": info.get("has_update", False),
        "update_info": info.get("update_info", ""),
        "download_url": info.get("download_url"),
    }
