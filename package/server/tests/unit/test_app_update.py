"""Unit tests for app/service/app_update.py（手机 App 安装包更新检查）。

覆盖三条主线：
- ``normalize_version``：兼容 ``v0.12.1`` 并拒绝非法版本串。
- ``fetch_release_apk``：从 GitHub Release 资产里挑 APK（正式包优先于 debug 包），
  以及 HTTP 失败 / 无 APK 资产时返回 None。
- ``check_app_update``：无更新、有更新且拿到资产、有更新但 GitHub 不可达
  （回退 CI 命名约定且 size=0）、非法版本、不支持的平台。
"""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


def _run(coro):
    return asyncio.run(coro)


def _async_return(value):
    async def _coro(*_a, **_k):
        return value
    return _coro


def _async_return_ctx(value):
    class _Ctx:
        async def __aenter__(self):
            return value

        async def __aexit__(self, *_a):
            return None

    def _factory(*_a, **_k):
        return _Ctx()

    return _factory


def _fake_session(payload, status=200):
    response = MagicMock()
    response.status = status
    response.json = _async_return(payload)
    session = MagicMock()
    session.get = _async_return_ctx(response)
    session.__aenter__ = _async_return(session)
    session.__aexit__ = _async_return(None)
    return session


# --------------------------- normalize_version ---------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("0.12.1", "0.12.1"),
        ("v0.12.1", "0.12.1"),
        ("V1.0", "1.0"),
        (" 1.2.3 ", "1.2.3"),
        ("1.2.3-beta", ""),
        ("abc", ""),
        ("", ""),
        (None, ""),
    ],
)
def test_normalize_version(raw, expected):
    from app.service.app_update import normalize_version
    assert normalize_version(raw) == expected


# --------------------------- fetch_release_apk ---------------------------


def test_fetch_release_apk_prefers_release_over_debug():
    from app.service import app_update

    payload = {
        "assets": [
            {"name": "TrailSnap-1.0.0-debug.apk", "browser_download_url": "http://dl/debug", "size": 10},
            {"name": "TrailSnap-1.0.0.apk", "browser_download_url": "http://dl/release", "size": 20},
            {"name": "latest.json", "browser_download_url": "http://dl/json", "size": 1},
        ]
    }
    with patch.object(app_update.aiohttp, "ClientSession", MagicMock(return_value=_fake_session(payload))):
        asset = _run(app_update.fetch_release_apk("1.0.0"))

    assert asset == {
        "download_url": "http://dl/release",
        "size": 20,
        "file_name": "TrailSnap-1.0.0.apk",
    }


def test_fetch_release_apk_falls_back_to_debug_asset():
    from app.service import app_update

    payload = {"assets": [{"name": "TrailSnap-1.0.0-debug.apk", "browser_download_url": "http://dl/debug", "size": 33}]}
    with patch.object(app_update.aiohttp, "ClientSession", MagicMock(return_value=_fake_session(payload))):
        asset = _run(app_update.fetch_release_apk("1.0.0"))

    assert asset["download_url"] == "http://dl/debug"
    assert asset["size"] == 33


def test_fetch_release_apk_returns_none_without_apk_asset():
    from app.service import app_update

    payload = {"assets": [{"name": "latest.json", "browser_download_url": "http://dl/json", "size": 1}]}
    with patch.object(app_update.aiohttp, "ClientSession", MagicMock(return_value=_fake_session(payload))):
        assert _run(app_update.fetch_release_apk("1.0.0")) is None


def test_fetch_release_apk_returns_none_on_http_error():
    from app.service import app_update

    with patch.object(app_update.aiohttp, "ClientSession", MagicMock(return_value=_fake_session({}, status=404))):
        assert _run(app_update.fetch_release_apk("1.0.0")) is None


def test_fetch_release_apk_rejects_invalid_version():
    from app.service.app_update import fetch_release_apk
    assert _run(fetch_release_apk("not-a-version")) is None


# ---------------------------- check_app_update ---------------------------


def test_check_app_update_no_update_when_already_latest():
    from app.service import app_update

    info = {"latest_version": "1.0.0", "has_update": False, "update_info": "", "download_url": "http://page"}
    with patch.object(app_update, "fetch_remote_update_info", side_effect=_async_return(info)):
        result = _run(app_update.check_app_update("1.0.0"))

    assert result["has_update"] is False
    assert result["download_url"] is None
    assert result["release_page_url"] == "http://page"


def test_check_app_update_returns_apk_asset_when_newer():
    from app.service import app_update

    info = {
        "latest_version": "1.1.0",
        "has_update": True,
        "update_info": "新功能",
        "download_url": "http://page/v1.1.0",
    }
    with (
        patch.object(app_update, "fetch_remote_update_info", side_effect=_async_return(info)),
        patch.object(app_update, "ensure_cached_apk", side_effect=_async_return("/cache/TrailSnap-1.1.0.apk")),
        patch.object(app_update.os.path, "getsize", return_value=4096),
    ):
        result = _run(app_update.check_app_update("v1.0.0"))

    assert result["has_update"] is True
    assert result["current_version"] == "1.0.0"
    assert result["latest_version"] == "1.1.0"
    assert result["download_url"] == "/api/system/app-update-download/1.1.0"
    assert result["size"] == 4096
    assert result["file_name"] == "TrailSnap-1.1.0.apk"
    assert result["update_info"] == "新功能"


def test_check_app_update_withholds_external_url_when_server_cache_unavailable():
    """缓存失败时不能把 GitHub 地址泄漏给 App。"""
    from app.service import app_update

    info = {"latest_version": "1.1.0", "has_update": True, "update_info": "", "download_url": None}
    with (
        patch.object(app_update, "fetch_remote_update_info", side_effect=_async_return(info)),
        patch.object(app_update, "ensure_cached_apk", side_effect=_async_return(None)),
    ):
        result = _run(app_update.check_app_update("1.0.0", repo="LC044/TrailSnap"))

    assert result["has_update"] is True
    assert result["download_url"] is None
    assert result["file_name"] is None
    assert result["size"] == 0
    assert "尚未缓存" in result["error"]


def test_check_app_update_reports_error_when_manifest_unavailable():
    from app.service import app_update

    with patch.object(app_update, "fetch_remote_update_info", side_effect=_async_return(None)):
        result = _run(app_update.check_app_update("1.0.0"))

    assert result["has_update"] is False
    assert result["error"] == "Failed to check for updates"


def test_check_app_update_rejects_invalid_installed_version():
    from app.service.app_update import check_app_update
    result = _run(check_app_update("unknown"))
    assert result["has_update"] is False
    assert result["error"] == "无法识别当前 App 版本"


def test_check_app_update_rejects_unsupported_platform():
    from app.service.app_update import check_app_update
    result = _run(check_app_update("1.0.0", platform="ios"))
    assert result["has_update"] is False
    assert "ios" in result["error"]
