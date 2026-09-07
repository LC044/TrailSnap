"""Nightly gap coverage for the Tianditu reverse proxy guard and failure path."""

import asyncio
from unittest.mock import MagicMock, patch

import aiohttp
import pytest
from fastapi import HTTPException, Request

from app.api import system as system_api

pytestmark = pytest.mark.smoke


def _request(headers=None):
    return Request({
        "type": "http",
        "method": "GET",
        "scheme": "http",
        "server": ("localhost", 8000),
        "path": "/api/system/map-proxy/api.tianditu.gov.cn/icon.png",
        "query_string": b"tk=test",
        "headers": headers or [(b"host", b"localhost:8000")],
    })


def test_public_origin_falls_back_to_request_scheme_and_host():
    assert system_api._public_request_origin(_request()) == "http://localhost:8000"


def test_map_proxy_rejects_hosts_outside_tianditu_allowlist():
    with pytest.raises(HTTPException) as exc:
        asyncio.run(system_api.proxy_tianditu_resource("evil.example.com", "icon.png", _request()))

    assert exc.value.status_code == 404
    assert exc.value.detail == "Unsupported map host"


def test_map_proxy_maps_upstream_client_error_to_502():
    request = _request([
        (b"host", b"photos.example.com"),
        (b"x-forwarded-proto", b"https,http"),
    ])
    with patch.object(system_api.aiohttp, "ClientSession", MagicMock(side_effect=aiohttp.ClientError("network down"))):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(system_api.proxy_tianditu_resource("api.tianditu.gov.cn", "icon.png", request))

    assert exc.value.status_code == 502
    assert exc.value.detail == "Map service is unavailable"
