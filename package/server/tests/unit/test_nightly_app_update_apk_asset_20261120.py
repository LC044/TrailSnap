"""APK asset selection for mobile app updates."""
import pytest

from app.service.app_update import _pick_apk_asset

pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


def test_returns_none_when_no_apk_asset_exists():
    assert _pick_apk_asset([{"name": "TrailSnap-1.0.0.zip"}]) is None


def test_returns_none_for_an_empty_asset_list():
    assert _pick_apk_asset([]) is None


def test_prefers_the_release_asset_over_the_debug_asset():
    assets = [
        {"name": "TrailSnap-1.0.0-debug.apk"},
        {"name": "TrailSnap-1.0.0.apk"},
    ]
    assert _pick_apk_asset(assets)["name"] == "TrailSnap-1.0.0.apk"


def test_matches_the_apk_suffix_case_insensitively():
    assets = [{"name": "TrailSnap-1.0.0.APK"}]
    assert _pick_apk_asset(assets)["name"] == "TrailSnap-1.0.0.APK"


def test_ignores_assets_without_a_name():
    assert _pick_apk_asset([{}, {"name": "notes.txt"}]) is None
