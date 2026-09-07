"""Nightly gap coverage for App APK cache validation and fallback lookup."""

import asyncio
from unittest.mock import patch

import pytest

from app.service import app_update

pytestmark = pytest.mark.smoke


def _async_return(value):
    async def callback(*_args, **_kwargs):
        return value
    return callback


def test_cache_release_apk_rejects_invalid_version_or_url():
    async def run(version, asset):
        return await app_update.cache_release_apk(version, asset)

    assert asyncio.run(run("", {"download_url": "https://example.com/a.apk"})) is None
    assert asyncio.run(run("1.2.3", {"download_url": "http://example.com/a.apk"})) is None
    assert asyncio.run(run("1.2.3", {})) is None


def test_cache_release_apk_reuses_matching_cached_file():
    cached = r"C:\TrailSnap\app_updates\TrailSnap-1.2.3.apk"
    asset = {"download_url": "https://example.com/TrailSnap-1.2.3.apk", "size": 123}

    with patch.object(app_update, "cached_apk_path", return_value=cached), \
         patch.object(app_update.os.path, "getsize", return_value=123):
        result = asyncio.run(app_update.cache_release_apk("1.2.3", asset))

    assert result == cached


def test_ensure_cached_apk_uses_existing_cache_without_release_lookup():
    cached = "/cache/TrailSnap-1.2.3.apk"
    with patch.object(app_update, "cached_apk_path", return_value=cached), \
         patch.object(app_update, "fetch_release_apk", side_effect=AssertionError("must not fetch")):
        assert asyncio.run(app_update.ensure_cached_apk("1.2.3")) == cached


def test_ensure_cached_apk_falls_back_to_ci_asset_when_release_lookup_fails():
    expected = "/cache/TrailSnap-1.2.3.apk"
    captured = {}

    async def fake_cache(version, asset):
        captured["version"] = version
        captured["asset"] = asset
        return expected

    with patch.object(app_update, "cached_apk_path", return_value=None), \
         patch.object(app_update, "fetch_release_apk", side_effect=_async_return(None)), \
         patch.object(app_update, "cache_release_apk", side_effect=fake_cache):
        result = asyncio.run(app_update.ensure_cached_apk("1.2.3", repo="LC044/TrailSnap"))

    assert result == expected
    assert captured["version"] == "1.2.3"
    assert captured["asset"]["download_url"].startswith("https://github.com/LC044/TrailSnap/releases/download/v1.2.3/")
