import re

import aiohttp
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, Response
from app.core.system_config import system_config
from app.api.deps import get_current_user
from app.db.models.user import User
from app.service.update_checker import fetch_remote_update_info
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

_TIANDITU_HOST = re.compile(
    r"^(?:api|location|t[0-7])\.tianditu\.(?:gov\.cn|com)$",
    re.IGNORECASE,
)


def _rewrite_tianditu_text(value: str) -> str:
    """Route URLs constructed inside the Tianditu SDK back through TrailSnap.

    The SDK builds most endpoints by concatenating protocol, host and path, so
    replacing only literal absolute URLs is insufficient.  These two source
    expressions cover the API/service bundles; map tiles are explicitly
    replaced by the client with TrailSnap's tile proxy.
    """
    proxy_api = '"/api/system/map-proxy/api.tianditu.gov.cn"'
    value = value.replace('T.Protocol.value+"api.tianditu."+T.Domain', proxy_api)
    value = value.replace(
        'T.Protocol.value+"location.tianditu.gov.cn"',
        '"/api/system/map-proxy/location.tianditu.gov.cn"',
    )
    return re.sub(
        r"https?:\/\/((?:api|location|t[0-7])\.tianditu\.(?:gov\.cn|com))",
        r"/api/system/map-proxy/\1",
        value,
        flags=re.IGNORECASE,
    )


def _public_request_origin(request: Request) -> str:
    """Build the browser-key origin represented by the self-hosted gateway."""
    forwarded_proto = request.headers.get("x-forwarded-proto", "").split(",", 1)[0].strip().lower()
    scheme = forwarded_proto if forwarded_proto in {"http", "https"} else request.url.scheme
    forwarded_host = request.headers.get("x-forwarded-host", "").split(",", 1)[0].strip()
    host = forwarded_host or request.headers.get("host", "")
    return f"{scheme}://{host}" if host else ""


@router.get("/map-proxy/{host}/{path:path}", include_in_schema=False)
async def proxy_tianditu_resource(host: str, path: str, request: Request):
    """Strict reverse proxy used by the mobile app for Tianditu resources.

    ``host`` is allow-listed to avoid turning a self-hosted TrailSnap instance
    into an open proxy or SSRF primitive.  The phone therefore talks only to
    TrailSnap; all third-party traffic originates from the server.
    """
    if not _TIANDITU_HOST.fullmatch(host):
        raise HTTPException(status_code=404, detail="Unsupported map host")
    upstream = f"https://{host}/{path}"
    timeout = aiohttp.ClientTimeout(total=30, connect=8)
    headers = {
        "Accept": request.headers.get("accept", "*/*"),
        "User-Agent": "TrailSnap-Map-Proxy/1.0",
    }
    # Tianditu browser keys can be restricted by an allowed web origin.  From
    # Tianditu's perspective the self-hosted gateway is now the caller, so use
    # its public origin rather than Capacitor's synthetic http://localhost.
    public_origin = _public_request_origin(request)
    if public_origin:
        headers["Referer"] = f"{public_origin}/"
        headers["Origin"] = public_origin
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(upstream, params=request.query_params, headers=headers) as response:
                body = await response.read()
                content_type = response.headers.get("Content-Type", "application/octet-stream")
                if "javascript" in content_type or "text/" in content_type:
                    charset = response.charset or "utf-8"
                    body = _rewrite_tianditu_text(body.decode(charset, errors="replace")).encode("utf-8")
                    content_type = content_type.split(";", 1)[0] + "; charset=utf-8"
                return Response(
                    content=body,
                    status_code=response.status,
                    media_type=None,
                    headers={
                        "Content-Type": content_type,
                        "Cache-Control": "public, max-age=86400",
                        "X-Content-Type-Options": "nosniff",
                    },
                )
    except aiohttp.ClientError as error:
        logger.warning("Tianditu proxy failed for %s: %s", upstream, error)
        raise HTTPException(status_code=502, detail="Map service is unavailable") from error

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


@router.get("/app-update-check")
async def check_app_update_endpoint(version: str, platform: str = "android"):
    """手机 App 自更新检查。

    与 ``/update-check`` 不同：这里的 ``version`` 是 App 自身安装的
    ``versionName``（由客户端传入），返回值仅携带当前 Server 的 APK
    缓存路径和文件大小，App 不接触外部发布服务器。
    """
    from app.service.app_update import check_app_update

    return await check_app_update(current_version=version, platform=platform)


@router.get("/app-update-download/{version}", include_in_schema=False)
async def download_cached_app_update(version: str):
    """Serve only APKs already downloaded and validated by this Server."""
    from app.service.app_update import cached_apk_path, normalize_version

    normalized = normalize_version(version)
    path = cached_apk_path(normalized)
    if not normalized or not path:
        raise HTTPException(status_code=404, detail="App update is not cached")
    return FileResponse(
        path,
        filename=f"TrailSnap-{normalized}.apk",
        media_type="application/vnd.android.package-archive",
        headers={"Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff"},
    )
