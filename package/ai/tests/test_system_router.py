"""Unit tests for the AI service system router (app/routers/system.py).

The router exposes two read-only endpoints (health-check + version) and
only depends on ``app.config.settings``.  Tests build a stripped FastAPI
app that mounts only this router, so no models / databases / downloads
are touched.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import settings
from app.routers import system as ai_system


pytestmark = [pytest.mark.smoke, pytest.mark.module_ai_system]


@pytest.fixture
def ai_system_client():
    app = FastAPI(title="TrailSnap AI - system tests")
    app.include_router(ai_system.router)
    return TestClient(app)


def test_health_check_returns_ok_with_settings_app_name(ai_system_client):
    res = ai_system_client.get("/health-check")
    assert res.status_code == 200
    body = res.json()
    assert body.get("status") == "ok"
    assert body.get("service") == settings.APP_NAME


def test_health_check_does_not_expose_extra_keys(ai_system_client):
    """Smoke: ensure the response payload stays minimal and stable."""
    res = ai_system_client.get("/health-check")
    assert res.status_code == 200
    body = res.json()
    assert set(body.keys()) == {"status", "service"}


def test_version_returns_string_matching_settings_version(ai_system_client):
    res = ai_system_client.get("/version")
    assert res.status_code == 200
    body = res.json()
    assert isinstance(body.get("version"), str)
    assert body["version"] == settings.APP_VERSION
    assert body["version"]  # non-empty


def test_endpoints_remain_independent_no_shared_state_leak(ai_system_client):
    """Calling both endpoints in sequence must not mutate or drain state."""
    health1 = ai_system_client.get("/health-check").json()
    version1 = ai_system_client.get("/version").json()

    # call them again and confirm shape is byte-for-byte consistent
    health2 = ai_system_client.get("/health-check").json()
    version2 = ai_system_client.get("/version").json()

    assert health1 == health2
    assert version1 == version2
