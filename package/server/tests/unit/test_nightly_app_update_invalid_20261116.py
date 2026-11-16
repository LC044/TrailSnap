"""2026-11-16 nightly coverage for ``app/service/app_update.py``.

The 2026-11-16 backend coverage scan reported ``service/app_update.py`` at
95.7% with 8 missed lines:

* the "release lookup returned an invalid payload" branch (line 97) and
  the "release lookup failed" branch (lines 98-99) of
  ``fetch_release_apk``;
* the version normalisation of ``prefetch_latest_app_update`` and the
  call to ``ensure_cached_apk`` (lines 238-240).

A broken or hijacked mirror must never break the update check: the
lookup simply moves on to the next source.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.service import app_update


pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


class _FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status = status

    async def json(self):
        return self._payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False


class _FakeSession:
    def __init__(self, responder):
        self._responder = responder

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False

    def get(self, url, headers=None, timeout=None):
        return self._responder(url)


def _install_session(monkeypatch, responder):
    monkeypatch.setattr(app_update.aiohttp, "ClientSession", lambda *a, **k: _FakeSession(responder))
    async def _no_backoff(_round):
        return None

    monkeypatch.setattr(app_update, "retry_backoff", _no_backoff)


def test_fetch_release_apk_skips_an_invalid_payload(monkeypatch):
    _install_session(monkeypatch, lambda url: _FakeResponse({"assets": "not-a-list"}))

    assert app_update.asyncio.run(app_update.fetch_release_apk("1.2.3")) is None


def test_fetch_release_apk_survives_a_broken_mirror(monkeypatch):
    def _boom(_url):
        raise RuntimeError("connection reset")

    _install_session(monkeypatch, _boom)

    assert app_update.asyncio.run(app_update.fetch_release_apk("1.2.3")) is None


def test_fetch_release_apk_returns_the_apk_asset(monkeypatch):
    payload = {
        "assets": [
            {"name": "TrailSnap-1.2.3-debug.apk", "browser_download_url": "https://x/y.apk", "size": 7},
        ]
    }
    _install_session(monkeypatch, lambda url: _FakeResponse(payload))

    asset = app_update.asyncio.run(app_update.fetch_release_apk("v1.2.3"))

    assert asset is not None
    assert asset["download_url"] == "https://x/y.apk"


def test_fetch_release_apk_rejects_an_invalid_version():
    assert app_update.asyncio.run(app_update.fetch_release_apk("not-a-version")) is None


def test_prefetch_latest_app_update_caches_the_latest_version(monkeypatch):
    seen = {}

    async def _fake_info(**kwargs):
        seen.update(kwargs)
        return {"latest_version": "v2.0.0"}

    async def _fake_ensure(version, repo=app_update.GITHUB_REPO):
        seen["version"] = version
        return "/cache/app.apk"

    monkeypatch.setattr(app_update, "fetch_remote_update_info", _fake_info)
    monkeypatch.setattr(app_update, "ensure_cached_apk", _fake_ensure)

    result = app_update.asyncio.run(app_update.prefetch_latest_app_update())

    assert result == "/cache/app.apk"
    assert seen["version"] == "2.0.0"
    assert seen["current_version"] == "0.0.0"


def test_prefetch_latest_app_update_skips_an_empty_manifest(monkeypatch):
    async def _fake_info(**kwargs):
        return {}

    async def _fake_ensure(version, repo=app_update.GITHUB_REPO):
        raise AssertionError("must not be called without a version")

    monkeypatch.setattr(app_update, "fetch_remote_update_info", _fake_info)
    monkeypatch.setattr(app_update, "ensure_cached_apk", _fake_ensure)

    assert app_update.asyncio.run(app_update.prefetch_latest_app_update()) is None


def test_normalize_version_accepts_only_numeric_versions():
    assert app_update.normalize_version("v1.2.3") == "1.2.3"
    assert app_update.normalize_version("1.2") == "1.2"
    assert app_update.normalize_version("latest") == ""
    assert app_update.normalize_version(None) == ""

