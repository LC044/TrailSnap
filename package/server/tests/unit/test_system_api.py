"""Unit tests for the system REST router (app/api/system.py).

Covers the three concerns in this thin module:

- ``/config`` GET + PUT  -- superuser-only, with dict-merge semantics
  on PUT so partial updates (e.g. ``{"security": {"allow_registration": false}}``)
  dont have to re-send every nested key.
- ``/version`` GET       -- returns the package ``VERSION`` constant.
- ``/update-check`` GET  -- wraps ``app.service.update_checker.fetch_remote_update_info``
  and surfaces both the success and the network/parse failure paths.

We patch the ``system_config`` singleton directly so we dont touch
``./data/system_config.json`` on disk and dont depend on FastAPI
``TestClient`` startup.
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.api import system as system_api
from app.core.config_manager import VERSION


pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


def _user(is_superuser=False):
    return SimpleNamespace(id="u-1", is_superuser=is_superuser)


# ----------------------------- /config -----------------------------------


def test_get_system_config_requires_superuser():
    user = _user(is_superuser=False)
    with pytest.raises(HTTPException) as exc_info:
        system_api.get_system_config(current_user=user)
    assert exc_info.value.status_code == 403


def test_get_system_config_returns_dump_for_superuser():
    user = _user(is_superuser=True)
    fake_dump = {"security": {"allow_registration": True}, "task": {}}
    fake_config = SimpleNamespace(model_dump=lambda: fake_dump)

    with patch.object(system_api.system_config, "config", fake_config):
        result = system_api.get_system_config(current_user=user)

    assert result == fake_dump


def test_update_system_config_requires_superuser():
    user = _user(is_superuser=False)
    with pytest.raises(HTTPException) as exc_info:
        system_api.update_system_config(payload={"security": {}}, current_user=user)
    assert exc_info.value.status_code == 403


def _make_settings_factory(captured):
    class _FakeSettings:
        def __init__(self, **kwargs):
            captured["init"] = kwargs
            self._data = kwargs

        def model_dump(self):
            return self._data

    return _FakeSettings


def test_update_system_config_merges_nested_dict_and_saves():
    user = _user(is_superuser=True)
    existing = {
        "security": {"allow_registration": True, "secret_key": "old"},
        "task": {"concurrency_level": "low"},
    }
    payload = {"security": {"allow_registration": False}}

    fake_manager = MagicMock()
    fake_manager.config.model_dump.return_value = existing

    captured = {}
    FakeSettings = _make_settings_factory(captured)

    with patch.object(system_api.system_config, "config", fake_manager.config):
        with patch.object(system_api.system_config, "save") as fake_save:
            with patch("app.core.system_config.SystemSettings", FakeSettings):
                result = system_api.update_system_config(payload=payload, current_user=user)

    assert captured["init"]["security"]["allow_registration"] is False
    assert captured["init"]["security"]["secret_key"] == "old"
    assert captured["init"]["task"]["concurrency_level"] == "low"

    fake_save.assert_called_once_with()
    assert result["status"] == "success"
    assert result["config"] == captured["init"]


def test_update_system_config_replaces_non_dict_fields():
    user = _user(is_superuser=True)
    existing = {
        "security": {"allow_registration": True},
        "recycle_bin": {"retention_days": 7, "cleanup_time": "00:00"},
    }

    fake_manager = MagicMock()
    fake_manager.config.model_dump.return_value = existing

    captured = {}
    FakeSettings = _make_settings_factory(captured)

    with patch.object(system_api.system_config, "config", fake_manager.config):
        with patch.object(system_api.system_config, "save") as fake_save:
            with patch("app.core.system_config.SystemSettings", FakeSettings):
                system_api.update_system_config(
                    payload={"recycle_bin": {"retention_days": 30}}, current_user=user
                )

    assert captured["init"]["recycle_bin"]["retention_days"] == 30
    assert captured["init"]["recycle_bin"]["cleanup_time"] == "00:00"
    fake_save.assert_called_once_with()


def test_task_config_change_restarts_worker():
    user = _user(is_superuser=True)
    fake_manager = MagicMock()
    fake_manager.config.model_dump.return_value = {
        "task": {"concurrency_level": "medium"},
    }
    captured = {}
    FakeSettings = _make_settings_factory(captured)
    task_manager = MagicMock()

    with (
        patch.object(system_api.system_config, "config", fake_manager.config),
        patch.object(system_api.system_config, "save"),
        patch("app.core.system_config.SystemSettings", FakeSettings),
        patch("app.service.task_manager.TaskManager.get_instance", return_value=task_manager),
    ):
        system_api.update_system_config(
            payload={"task": {"concurrency_level": "low"}},
            current_user=user,
        )

    task_manager.restart_worker.assert_called_once_with(graceful=True)


# ----------------------------- /version ----------------------------------


def test_get_version_returns_package_version_constant():
    result = system_api.get_version()
    assert result == {"version": VERSION}
    assert isinstance(result["version"], str) and result["version"]


# ----------------------------- /update-check ------------------------------


def test_check_update_returns_has_update_true_with_payload():
    info = {
        "latest_version": "9.9.9",
        "has_update": True,
        "update_info": "new stuff",
        "download_url": "https://example/dl",
    }

    async def _fake_fetch(**kwargs):
        return info

    with patch("app.api.system.fetch_remote_update_info", side_effect=_fake_fetch):
        result = asyncio.run(system_api.check_update())

    assert result["current_version"] == VERSION
    assert result["latest_version"] == "9.9.9"
    assert result["has_update"] is True
    assert result["update_info"] == "new stuff"
    assert result["download_url"] == "https://example/dl"


def test_check_update_returns_error_payload_when_fetch_returns_none():
    async def _fake_fetch(**kwargs):
        return None

    with patch("app.api.system.fetch_remote_update_info", side_effect=_fake_fetch):
        result = asyncio.run(system_api.check_update())

    assert result["current_version"] == VERSION
    assert result["latest_version"] is None
    assert result["has_update"] is False
    assert result["error"] == "Failed to check for updates"


# ----------------------------- /app-update-check --------------------------


def test_check_app_update_endpoint_passes_client_version_and_platform():
    """App 自更新用的是客户端 versionName，而不是服务端 VERSION。"""
    payload = {"has_update": True, "download_url": "http://dl/apk", "size": 1024}
    captured = {}

    async def _fake_check(current_version, platform):
        captured["current_version"] = current_version
        captured["platform"] = platform
        return payload

    with patch("app.service.app_update.check_app_update", side_effect=_fake_check):
        result = asyncio.run(
            system_api.check_app_update_endpoint(version="0.11.0", platform="android")
        )

    assert captured == {"current_version": "0.11.0", "platform": "android"}
    assert result is payload


def test_check_app_update_endpoint_defaults_to_android():
    async def _fake_check(current_version, platform):
        return {"platform": platform}

    with patch("app.service.app_update.check_app_update", side_effect=_fake_check):
        result = asyncio.run(system_api.check_app_update_endpoint(version="0.12.1"))

    assert result["platform"] == "android"


def test_tianditu_sdk_urls_are_rewritten_to_server_proxy():
    source = (
        'T.w={E:T.Protocol.value+"api.tianditu."+T.Domain,'
        'IPSERVER:T.Protocol.value+"location.tianditu.gov.cn"};'
        'var fallback="https://t3.tianditu.gov.cn/vec_w/wmts";'
    )
    rewritten = system_api._rewrite_tianditu_text(source)

    assert '"/api/system/map-proxy/api.tianditu.gov.cn"' in rewritten
    assert '"/api/system/map-proxy/location.tianditu.gov.cn"' in rewritten
    assert "/api/system/map-proxy/t3.tianditu.gov.cn/vec_w/wmts" in rewritten
    assert "https://t3.tianditu.gov.cn" not in rewritten


def test_map_proxy_uses_public_server_origin_for_browser_key():
    request = Request({
        "type": "http",
        "method": "GET",
        "scheme": "http",
        "server": ("server", 8000),
        "path": "/system/map-proxy/api.tianditu.gov.cn/api",
        "query_string": b"",
        "headers": [
            (b"host", b"server:8000"),
            (b"x-forwarded-proto", b"https"),
            (b"x-forwarded-host", b"photos.example.com"),
        ],
    })

    assert system_api._public_request_origin(request) == "https://photos.example.com"


# ------------------------ /map-proxy UA + caching -------------------------
# 天地图对「浏览器端」Key 按 User-Agent 校验：非浏览器 UA 一律 403 301012
# （"Key权限类型为:浏览器端，请使用浏览器访问"）。代理必须转发 WebView 的
# 真实 UA，缺失时兜底为移动浏览器 UA，绝不能再发合成标识。


def _proxy_request(headers=None):
    return Request({
        "type": "http",
        "method": "GET",
        "scheme": "http",
        "server": ("localhost", 8000),
        "path": "/api/system/map-proxy/t0.tianditu.gov.cn/DataServer",
        "query_string": b"T=vec_w&x=1&y=2&l=3&tk=test",
        "headers": headers or [(b"host", b"localhost:8000")],
    })


def _fake_upstream(status=200, content_type="image/png", body=b"tile-bytes"):
    response = SimpleNamespace(
        status=status,
        headers={"Content-Type": content_type},
        charset=None,
        read=AsyncMock(return_value=body),
    )
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=response)
    context.__aexit__ = AsyncMock(return_value=False)
    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.get = MagicMock(return_value=context)
    return session


class AsyncMock(MagicMock):
    async def __call__(self, *args, **kwargs):
        return super().__call__(*args, **kwargs)


def test_map_proxy_forwards_client_user_agent_to_tianditu():
    """WebView 的真实 UA 必须透传；天地图按 UA 拒绝非浏览器客户端。"""
    request = _proxy_request([
        (b"host", b"localhost:8000"),
        (b"user-agent", b"Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36"),
    ])
    session = _fake_upstream()

    with patch.object(system_api.aiohttp, "ClientSession", MagicMock(return_value=session)):
        asyncio.run(system_api.proxy_tianditu_resource("t0.tianditu.gov.cn", "DataServer", request))

    sent_headers = session.get.call_args.kwargs["headers"]
    assert sent_headers["User-Agent"] == "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36"


def test_map_proxy_falls_back_to_browser_user_agent_when_missing():
    """无 UA（如部分内网探活）时用浏览器 UA 兜底，而不是合成标识。"""
    session = _fake_upstream()

    with patch.object(system_api.aiohttp, "ClientSession", MagicMock(return_value=session)):
        asyncio.run(
            system_api.proxy_tianditu_resource("t0.tianditu.gov.cn", "DataServer", _proxy_request())
        )

    sent_headers = session.get.call_args.kwargs["headers"]
    assert sent_headers["User-Agent"].startswith("Mozilla/5.0")
    assert "TrailSnap-Map-Proxy" not in sent_headers["User-Agent"]


def test_map_proxy_does_not_cache_error_responses():
    """上游 403/5xx 若被缓存，会在 WebView 里毒缓存一天，必须 no-store。"""
    session = _fake_upstream(status=403, content_type="application/json", body=b'{"code":301012}')

    with patch.object(system_api.aiohttp, "ClientSession", MagicMock(return_value=session)):
        response = asyncio.run(
            system_api.proxy_tianditu_resource("t0.tianditu.gov.cn", "DataServer", _proxy_request())
        )

    assert response.status_code == 403
    assert response.headers["cache-control"] == "no-store"


def test_map_proxy_caches_successful_responses():
    session = _fake_upstream(status=200)

    with patch.object(system_api.aiohttp, "ClientSession", MagicMock(return_value=session)):
        response = asyncio.run(
            system_api.proxy_tianditu_resource("t0.tianditu.gov.cn", "DataServer", _proxy_request())
        )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=86400"

