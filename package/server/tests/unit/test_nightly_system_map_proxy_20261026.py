"""Nightly coverage for the map proxy guards of ``app/api/system.py`` (2026-10-26).

The 2026-10-26 backend coverage scan listed ``api/system.py`` at 78.7% with
51 missed lines.  The missed lines sat in the guards that protect the
Tianditu reverse proxy:

* ``_map_user_id`` never rejected an unreadable token, a token without the
  ``map_proxy`` scope or a token without a subject
* ``_proxy_tianditu_resource`` never reported a missing database session
  (500), an account without any map API key (400) or an ajaxproxy request
  without exactly one target (400)
* the upstream failure of the proxy never turned into the documented
  502 "Map service is unavailable"

The proxy must never become an open relay, so every guard is asserted here.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.requests import Request

pytestmark = [pytest.mark.smoke]


def _request(query_string=b"", headers=None, path="/api/system/map-proxy/map-token/api.tianditu.gov.cn/api"):
    return Request({
        "type": "http",
        "method": "GET",
        "scheme": "http",
        "server": ("localhost", 8000),
        "path": path,
        "query_string": query_string,
        "headers": headers or [(b"host", b"localhost:8000")],
    })


def _map_token(payload=None):
    from jose import jwt

    from app.core.system_config import system_config

    body = payload if payload is not None else {"scope": "map_proxy", "sub": "user-1"}
    return jwt.encode(
        body,
        system_config.config.security.secret_key,
        algorithm=system_config.config.security.algorithm,
    )


# ---------------------------------------------------------------------------
# _map_user_id
# ---------------------------------------------------------------------------


def test_map_user_id_rejects_an_unreadable_token():
    from app.api import system as system_api
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        system_api._map_user_id("not-a-jwt")

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Invalid map access token"


def test_map_user_id_rejects_a_token_without_the_map_proxy_scope():
    from app.api import system as system_api
    from fastapi import HTTPException

    token = _map_token({"scope": "photos:read", "sub": "user-1"})

    with pytest.raises(HTTPException) as exc_info:
        system_api._map_user_id(token)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Invalid map access token"


def test_map_user_id_rejects_a_token_without_a_subject():
    from app.api import system as system_api
    from fastapi import HTTPException

    token = _map_token({"scope": "map_proxy"})

    with pytest.raises(HTTPException) as exc_info:
        system_api._map_user_id(token)

    assert exc_info.value.status_code == 403


def test_map_user_id_returns_the_subject():
    from app.api import system as system_api

    assert system_api._map_user_id(_map_token()) == "user-1"


# ---------------------------------------------------------------------------
# _proxy_tianditu_resource guards
# ---------------------------------------------------------------------------


def test_proxy_rejects_an_unsupported_host():
    from app.api import system as system_api
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(system_api._proxy_tianditu_resource("evil.example.com", "api", _request()))

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Unsupported map host"


def test_proxy_reports_a_missing_database_session():
    from app.api import system as system_api
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(system_api._proxy_tianditu_resource(
            "api.tianditu.gov.cn", "api", _request(), map_token="map-token", db=None,
        ))

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Map configuration is unavailable"


def test_proxy_reports_a_missing_map_api_key():
    from app.api import system as system_api
    from fastapi import HTTPException

    config = SimpleNamespace(map=SimpleNamespace(api_keys=[]))

    with patch.object(system_api, "_map_user_id", return_value="u-1"), \
         patch.object(system_api.config_manager, "get_user_config", return_value=config):
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(system_api._proxy_tianditu_resource(
                "api.tianditu.gov.cn", "api", _request(), map_token="map-token", db=MagicMock(),
            ))

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Map API Key is missing"


def test_proxy_rejects_an_ajaxproxy_request_without_a_target():
    from app.api import system as system_api
    from fastapi import HTTPException

    config = SimpleNamespace(map=SimpleNamespace(api_keys=["server-secret"]))

    with patch.object(system_api, "_map_user_id", return_value="u-1"), \
         patch.object(system_api.config_manager, "get_user_config", return_value=config), \
         patch.object(system_api.random, "choice", return_value="server-secret"):
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(system_api._proxy_tianditu_resource(
                "api.tianditu.gov.cn", "apiserver/ajaxproxy", _request(),
                map_token="map-token", db=MagicMock(),
            ))

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Invalid map proxy target"


def test_proxy_turns_an_upstream_failure_into_a_502():
    from app.api import system as system_api
    from fastapi import HTTPException
    import aiohttp

    config = SimpleNamespace(map=SimpleNamespace(api_keys=["server-secret"]))
    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)

    def _boom(*_args, **_kwargs):
        raise aiohttp.ClientError("upstream is down")

    session.get = MagicMock(side_effect=_boom)

    with patch.object(system_api, "_map_user_id", return_value="u-1"), \
         patch.object(system_api.config_manager, "get_user_config", return_value=config), \
         patch.object(system_api.random, "choice", return_value="server-secret"), \
         patch.object(system_api.aiohttp, "ClientSession", MagicMock(return_value=session)):
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(system_api._proxy_tianditu_resource(
                "api.tianditu.gov.cn", "api", _request(), map_token="map-token", db=MagicMock(),
            ))

    assert exc_info.value.status_code == 502
    assert exc_info.value.detail == "Map service is unavailable"


def test_proxy_turns_a_broken_session_into_a_502():
    from app.api import system as system_api
    from fastapi import HTTPException
    import aiohttp

    config = SimpleNamespace(map=SimpleNamespace(api_keys=["server-secret"]))

    with patch.object(system_api, "_map_user_id", return_value="u-1"), \
         patch.object(system_api.config_manager, "get_user_config", return_value=config), \
         patch.object(system_api.random, "choice", return_value="server-secret"), \
         patch.object(system_api.aiohttp, "ClientSession",
                      MagicMock(side_effect=aiohttp.ClientError("no socket"))):
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(system_api._proxy_tianditu_resource(
                "api.tianditu.gov.cn", "api", _request(), map_token="map-token", db=MagicMock(),
            ))

    assert exc_info.value.status_code == 502
    assert exc_info.value.detail == "Map service is unavailable"
