"""移动端 App（安装包）更新检查。

与 ``app/service/update_checker.py`` 的区别：
- ``update_checker`` 关心的是「服务端自身」是否有新版本，用于站内通知，
  ``download_url`` 指向 Release 页面，需要用户手动操作。
- 本模块关心的是「手机 App 安装包」，必须给出 **APK 直链和文件大小**，
  App 才能自行下载并唤起安装。

版本清单仍然复用官网的 ``version.json``（唯一版本事实来源），
拿到最新版本号后再向 GitHub Releases API 查询该 tag 下的 APK 资产以获取
精确的直链与体积；GitHub 不可达（限流 / 内网）时回退到 CI 的固定命名约定，
此时 ``size`` 为 0，客户端跳过大小校验。
"""
import logging
import os
import re
from typing import Any, Dict, List, Optional

import aiohttp

from app.service.update_checker import (
    DEFAULT_UPDATE_URL,
    compare_versions,
    fetch_remote_update_info,
)

logger = logging.getLogger("app.service.app_update")

GITHUB_REPO = os.getenv("TRAILSNAP_GITHUB_REPO", "LC044/TrailSnap")
GITHUB_RELEASE_API = "https://api.github.com/repos/{repo}/releases/tags/v{version}"

SUPPORTED_PLATFORMS = ("android",)

# CI（.github/workflows/build-mobile-app.yml）固定产出的 APK 名称。
APK_ASSET_TEMPLATE = "TrailSnap-{version}-debug.apk"
APK_FALLBACK_URL = (
    "https://github.com/{repo}/releases/download/v{version}/" + APK_ASSET_TEMPLATE
)

_VERSION_PATTERN = re.compile(r"^\d+(\.\d+)*$")


def normalize_version(value: Optional[str]) -> str:
    """去掉可能的 ``v`` 前缀并校验形如 ``0.12.1`` 的版本串，非法时返回空串。"""
    candidate = (value or "").strip().lstrip("vV")
    return candidate if _VERSION_PATTERN.match(candidate) else ""


def _pick_apk_asset(assets: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """从 Release 资产里挑选 APK：优先正式包，其次 debug 包。"""
    apks = [a for a in assets if str(a.get("name", "")).lower().endswith(".apk")]
    if not apks:
        return None
    apks.sort(key=lambda a: "debug" in str(a.get("name", "")).lower())
    return apks[0]


async def fetch_release_apk(
    version: str,
    repo: str = GITHUB_REPO,
    timeout: float = 8.0,
) -> Optional[Dict[str, Any]]:
    """查询指定 tag 的 APK 资产，返回 ``{download_url, size, file_name}``。"""
    version = normalize_version(version)
    if not version:
        return None
    url = GITHUB_RELEASE_API.format(repo=repo, version=version)
    try:
        headers = {"Accept": "application/vnd.github+json"}
        token = os.getenv("GITHUB_TOKEN", "")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=timeout) as response:
                if response.status != 200:
                    logger.info(f"Release lookup HTTP {response.status}: {url}")
                    return None
                payload = await response.json()
    except Exception as e:
        logger.info(f"Release lookup failed for v{version}: {e}")
        return None

    if not isinstance(payload, dict):
        return None
    asset = _pick_apk_asset(payload.get("assets") or [])
    if not asset or not asset.get("browser_download_url"):
        logger.info(f"Release v{version} has no APK asset")
        return None
    return {
        "download_url": asset["browser_download_url"],
        "size": int(asset.get("size") or 0),
        "file_name": asset.get("name") or APK_ASSET_TEMPLATE.format(version=version),
    }


async def check_app_update(
    current_version: str,
    platform: str = "android",
    manifest_url: str = DEFAULT_UPDATE_URL,
    repo: str = GITHUB_REPO,
) -> Dict[str, Any]:
    """给 App 端使用的更新检查。

    ``current_version`` 来自 App 自身的 ``versionName``，而不是服务端版本 ——
    App 与服务端可以分别升级，两者版本并不总是一致。
    """
    platform = (platform or "android").lower()
    installed = normalize_version(current_version)
    result: Dict[str, Any] = {
        "platform": platform,
        "current_version": installed or (current_version or ""),
        "latest_version": None,
        "has_update": False,
        "update_info": "",
        "download_url": None,
        "file_name": None,
        "size": 0,
        "release_page_url": None,
    }
    if platform not in SUPPORTED_PLATFORMS:
        result["error"] = f"暂不支持的平台：{platform}"
        return result
    if not installed:
        result["error"] = "无法识别当前 App 版本"
        return result

    info = await fetch_remote_update_info(url=manifest_url, current_version=installed)
    if info is None:
        result["error"] = "Failed to check for updates"
        return result

    latest = normalize_version(info.get("latest_version"))
    result["latest_version"] = latest or info.get("latest_version")
    result["update_info"] = info.get("update_info") or ""
    result["release_page_url"] = info.get("download_url")
    if not latest or compare_versions(latest, installed) <= 0:
        return result

    result["has_update"] = True
    asset = await fetch_release_apk(latest, repo=repo)
    if asset:
        result["download_url"] = asset["download_url"]
        result["size"] = asset["size"]
        result["file_name"] = asset["file_name"]
    else:
        # GitHub 不可达时退回 CI 命名约定，size 未知交由客户端跳过校验。
        result["download_url"] = APK_FALLBACK_URL.format(repo=repo, version=latest)
        result["file_name"] = APK_ASSET_TEMPLATE.format(version=latest)
        result["size"] = 0
    return result
