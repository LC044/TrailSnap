from fastapi import APIRouter, Depends, HTTPException
import aiohttp
from app.core.config_manager import config_manager, VERSION
from app.core.system_config import system_config
from app.api.deps import get_current_user
from app.db.models.user import User
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
    return {"status": "success", "config": system_config.config.model_dump()}

def compare_versions(v1: str, v2: str) -> int:
    """
    Compare two version strings.
    Returns:
        1 if v1 > v2
        -1 if v1 < v2
        0 if v1 == v2
    """
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

@router.get("/version")
def get_version():
    return {"version": VERSION}

@router.get("/update-check")
async def check_update():
    current_version = VERSION
    update_url = "https://trailsnap.cn/version.json"
    # update_url = "http://localhost:5173/version.json"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(update_url, timeout=5) as response:
                if response.status == 200:
                    remote_data = await response.json()
                    # sort by version
                    # remote_data.sort(key=lambda x: x["version"], reverse=True)
                    remote_version = remote_data[-1]["version"]
                    update_info = remote_data[-1].get("update_info")
                    download_url = remote_data[-1].get("download_url")
                    has_update = compare_versions(remote_version, current_version) > 0
                    update_info = ""
                    for item in remote_data:
                        if compare_versions(item["version"], current_version) > 0:
                            update_info += f"<br>{item['version']}:<br>{item['update_info']}<br>"
                    update_info = update_info.strip().strip("<br>")
                    return {
                        "current_version": current_version,
                        "latest_version": remote_version,
                        "has_update": has_update,
                        "update_info": update_info,
                        "download_url": download_url
                    }
                else:
                     logger.error(f"Update check failed with status: {response.status}")
    except Exception as e:
        logger.error(f"Failed to check for updates: {e}")
    
    return {
        "current_version": current_version,
        "latest_version": None,
        "has_update": False,
        "error": "Failed to check for updates"
    }
