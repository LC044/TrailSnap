"""Release names and signed updater references use the same public convention."""

import importlib.util
from pathlib import Path

import pytest
import asyncio
from unittest.mock import AsyncMock, patch

pytestmark = [pytest.mark.smoke, pytest.mark.module_system]
ROOT = Path(__file__).resolve().parents[4]
spec = importlib.util.spec_from_file_location("release_assets", ROOT / "scripts/release_assets.py")
names = importlib.util.module_from_spec(spec)
spec.loader.exec_module(names)


@pytest.mark.parametrize("platform,arch,expected", [
    ("win32", "x86_64", "windows-x64"),
    ("darwin", "aarch64", "macos-arm64"),
    ("linux", "amd64", "linux-x64"),
])
def test_platform_aliases_are_only_normalized_in_public_names(platform, arch, expected):
    assert names.asset_name("1.2.3", "desktop", platform, arch, "-portable.zip") == (
        f"TrailSnap-1.2.3-desktop-{expected}-portable.zip"
    )


@pytest.mark.parametrize("component,platform,arch,suffix,expected", [
    ("cli", "windows", "x64", ".exe", "TrailSnap-1.2.3-cli-windows-x64.exe"),
    ("ai-core", "darwin", "arm64", ".tar.gz", "TrailSnap-1.2.3-ai-core-macos-arm64.tar.gz"),
    ("mobile", "android", "universal", "-debug.apk", "TrailSnap-1.2.3-mobile-android-universal-debug.apk"),
])
def test_components_share_one_versioned_convention(component, platform, arch, suffix, expected):
    assert names.asset_name("1.2.3", component, platform, arch, suffix) == expected


@pytest.mark.parametrize("platform,arch,files", [
    ("windows", "x86_64", [("nsis/TrailSnap_1.2.3_x64-setup.exe", "-setup.exe")]),
    ("macos", "aarch64", [("dmg/TrailSnap_1.2.3_aarch64.dmg", ".dmg"),
                          ("macos/TrailSnap.app.tar.gz", "-update.app.tar.gz")]),
    ("linux", "x86_64", [("appimage/TrailSnap_1.2.3_amd64.AppImage", ".AppImage"),
                         ("deb/TrailSnap_1.2.3_amd64.deb", ".deb")]),
])
def test_normalize_desktop_preserves_bytes_and_signature(tmp_path, platform, arch, files):
    for relative, _ in files:
        source = tmp_path / relative
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(b"artifact")
        source.with_name(source.name + ".sig").write_bytes(b"signature")
    names.normalize_desktop(tmp_path, "1.2.3", platform, arch)
    for relative, suffix in files:
        destination = (tmp_path / relative).with_name(names.asset_name("1.2.3", "desktop", platform, arch, suffix))
        assert destination.read_bytes() == b"artifact"
        assert destination.with_name(destination.name + ".sig").read_bytes() == b"signature"
        assert not (tmp_path / relative).exists()
    names.normalize_desktop(tmp_path, "1.2.3", platform, arch)


def test_missing_desktop_artifact_fails_before_publication(tmp_path):
    with pytest.raises(ValueError, match="Expected one"):
        names.normalize_desktop(tmp_path, "1.2.3", "windows", "x64")


def test_ai_names_do_not_change_runtime_platform_keys():
    assert names.ai_asset_name("1.2.3", "win32-x64") == "TrailSnap-1.2.3-ai-core-windows-x64.tar.gz"
    assert names.ai_asset_name("1.2.3", "darwin-arm64") == "TrailSnap-1.2.3-ai-core-macos-arm64.tar.gz"


def test_android_fallback_tries_unified_then_legacy_name():
    from app.service import app_update

    with (
        patch.object(app_update, "cached_apk_path", return_value=None),
        patch.object(app_update, "fetch_release_apk", new_callable=AsyncMock, return_value=None),
        patch.object(app_update, "cache_release_apk", new_callable=AsyncMock, side_effect=[None, "/cache/app.apk"]) as cache,
        patch.object(app_update, "prune_app_update_cache"),
    ):
        assert asyncio.run(app_update.ensure_cached_apk("1.2.3")) == "/cache/app.apk"
    urls = [call.args[1]["download_url"] for call in cache.await_args_list]
    assert urls == [
        "https://github.com/LC044/TrailSnap/releases/download/v1.2.3/TrailSnap-1.2.3-mobile-android-universal-debug.apk",
        "https://github.com/LC044/TrailSnap/releases/download/v1.2.3/TrailSnap-1.2.3-debug.apk",
    ]
