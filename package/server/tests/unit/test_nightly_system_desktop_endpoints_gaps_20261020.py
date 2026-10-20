"""Coverage for desktop-only endpoints in app/api/system.py left untested.

Targets the following branches that show as missed in the per-module coverage
report for app/api/system.py (60% -> higher):
  - desktop_ai_extension_requirements GET (lines 34-46) + _require_desktop_secret
    falsy short-circuits (lines 71-77): missing/empty/TS_DESKTOP != 1.
  - set_desktop_ai_extension_state POST (lines 47-69): happy path, the
    "maintenance" drain loop, and exception fallback.
  - prepare_desktop_migration POST (lines 117-138): ready path, already draining
    409, exception fallback.
  - desktop_network GET (lines 140-149): TS_DESKTOP != 1 -> 404, happy LAN urls.
  - download_cached_app_update GET (lines 478-489): invalid version 404, no
    cache 404, cached FileResponse with Cache-Control + nosniff headers.

Mirrors the test_system_api.py style (MagicMock + AsyncMock + monkeypatch via
patch.object / patch), no FastAPI TestClient needed since the module-level
helpers expose the endpoint functions directly.
"""

import asyncio
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api import system as system_api
from app.core.config_manager import VERSION
from app.service.ai_extension_state import MINIMUM_AI_EXTENSION_VERSION


pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


# --------------------------- desktop_ai_extension GET ---------------------


def test_desktop_ai_extension_requirements_returns_payload(monkeypatch):
    """Happy path: the endpoint echoes server version + minimum AI ext version."""
    monkeypatch.setenv("TS_DESKTOP", "1")
    monkeypatch.setenv("TS_DESKTOP_SESSION_SECRET", "s3cr3t")
    response = system_api.desktop_ai_extension_requirements(secret="s3cr3t")
    assert response.code == 0
    assert response.code == 0
    data = response.data
    assert data["serverVersion"] == VERSION
    assert data["minimumAIExtensionVersion"] == MINIMUM_AI_EXTENSION_VERSION


@pytest.mark.parametrize(
    "env_patch,secret_value",
    [
        ({"TS_DESKTOP": "0", "TS_DESKTOP_SESSION_SECRET": "s"}, "s"),
        ({"TS_DESKTOP": "1", "TS_DESKTOP_SESSION_SECRET": ""}, "s"),
        ({"TS_DESKTOP": "1", "TS_DESKTOP_SESSION_SECRET": "s"}, None),
        ({"TS_DESKTOP": "1", "TS_DESKTOP_SESSION_SECRET": "s"}, "wrong"),
    ],
)
def test_desktop_ai_extension_requirements_requires_secret(monkeypatch, env_patch, secret_value):
    """All four falsy branches of _require_desktop_secret must surface 404."""
    monkeypatch.delenv("TS_DESKTOP", raising=False)
    monkeypatch.delenv("TS_DESKTOP_SESSION_SECRET", raising=False)
    for key, value in env_patch.items():
        monkeypatch.setenv(key, value)
    with pytest.raises(HTTPException) as exc:
        system_api.desktop_ai_extension_requirements(secret=secret_value)
    assert exc.value.status_code == 404


# --------------------- set_desktop_ai_extension_state POST -----------------


def _post_extension_state(state, secret="s3cr3t"):
    from app.api.system import AIExtensionStateRequest
    return asyncio.run(
        system_api.set_desktop_ai_extension_state(
            body=AIExtensionStateRequest(state=state),
            secret=secret,
        )
    )


def test_set_desktop_ai_extension_state_happy(monkeypatch):
    monkeypatch.setenv("TS_DESKTOP", "1")
    monkeypatch.setenv("TS_DESKTOP_SESSION_SECRET", "s3cr3t")
    task_manager = MagicMock()
    maintenance = SimpleNamespace(ai_draining=False, ai_active=0)
    with patch("app.service.task_manager.TaskManager.get_instance", return_value=task_manager), \
         patch("app.service.desktop_maintenance.maintenance", maintenance):
        response = _post_extension_state("ready")
    assert response.code == 0
    assert response.data["state"] == "ready"
    assert response.data["ready"] is True
    task_manager.set_ai_extension_state.assert_called_once_with("ready")
    # Non-maintenance state should clear the drain flag.
    assert maintenance.ai_draining is False


def test_set_desktop_ai_extension_state_maintenance_waits_for_ai_idle(monkeypatch):
    monkeypatch.setenv("TS_DESKTOP", "1")
    monkeypatch.setenv("TS_DESKTOP_SESSION_SECRET", "s3cr3t")
    task_manager = MagicMock()
    maintenance = SimpleNamespace(ai_draining=False, ai_active=1)

    sleep_calls = []

    async def fake_sleep(seconds):
        sleep_calls.append(seconds)
        if len(sleep_calls) >= 1:
            maintenance.ai_active = 0  # break the while loop

    with patch("app.service.task_manager.TaskManager.get_instance", return_value=task_manager), \
         patch("app.service.desktop_maintenance.maintenance", maintenance), \
         patch("app.api.system.asyncio.sleep", new=fake_sleep):
        response = _post_extension_state("maintenance")

    assert response.code == 0
    assert response.data["state"] == "maintenance"
    # Set the drain flag before delegating to TaskManager.
    assert maintenance.ai_draining is True
    task_manager.set_ai_extension_state.assert_called_once_with("maintenance")
    # Loop yielded once to wait for the AI queue to drain.
    assert sleep_calls == [0.1]


def test_set_desktop_ai_extension_state_returns_fail_on_exception(monkeypatch):
    monkeypatch.setenv("TS_DESKTOP", "1")
    monkeypatch.setenv("TS_DESKTOP_SESSION_SECRET", "s3cr3t")
    task_manager = MagicMock()
    task_manager.set_ai_extension_state.side_effect = RuntimeError("boom")
    maintenance = SimpleNamespace(ai_draining=False, ai_active=0)
    with patch("app.service.task_manager.TaskManager.get_instance", return_value=task_manager), \
         patch("app.service.desktop_maintenance.maintenance", maintenance):
        response = _post_extension_state("ready")
    assert response.code != 0
    assert "boom" in response.msg


# -------------------------- prepare_desktop_migration ---------------------


def test_prepare_desktop_migration_returns_ready_when_idle(monkeypatch):
    monkeypatch.setenv("TS_DESKTOP", "1")
    monkeypatch.setenv("TS_DESKTOP_SESSION_SECRET", "s3cr3t")
    maintenance = SimpleNamespace(draining=False, active=0, prepare=AsyncMock())

    class _Server:
        should_exit = False

    class _App:
        state = SimpleNamespace(job_scheduler=MagicMock(), desktop_server=_Server())

    request = SimpleNamespace(app=_App())

    with patch("app.service.desktop_maintenance.maintenance", maintenance), \
         patch("app.service.task_manager.TaskManager.get_instance", return_value=MagicMock()), \
         patch("app.api.system.asyncio.create_task") as create_task:
        response = asyncio.run(
            system_api.prepare_desktop_migration(request, secret="s3cr3t")
        )

    assert response.code == 0
    assert response.data["ready"] is True
    maintenance.prepare.assert_awaited_once()
    # A delayed shutdown coroutine is scheduled; the server should be flagged
    # to exit once it runs.
    scheduled = create_task.call_args[0][0]
    asyncio.run(scheduled)
    assert request.app.state.desktop_server.should_exit is True


def test_prepare_desktop_migration_returns_409_when_already_draining(monkeypatch):
    monkeypatch.setenv("TS_DESKTOP", "1")
    monkeypatch.setenv("TS_DESKTOP_SESSION_SECRET", "s3cr3t")
    maintenance = SimpleNamespace(draining=True, active=0, prepare=AsyncMock())
    request = SimpleNamespace(app=SimpleNamespace(
        state=SimpleNamespace(job_scheduler=MagicMock(), desktop_server=SimpleNamespace(should_exit=False))))
    with patch("app.service.desktop_maintenance.maintenance", maintenance), \
         patch("app.service.task_manager.TaskManager.get_instance", return_value=MagicMock()):
        response = asyncio.run(
            system_api.prepare_desktop_migration(request, secret="s3cr3t")
        )
    assert response.code != 0
    assert response.code == 409
    assert "\u5df2\u7ecf\u5728\u7b49\u5f85\u4efb\u52a1\u7ed3\u675f" in response.msg
    maintenance.prepare.assert_not_called()


def test_prepare_desktop_migration_returns_fail_on_exception(monkeypatch):
    monkeypatch.setenv("TS_DESKTOP", "1")
    monkeypatch.setenv("TS_DESKTOP_SESSION_SECRET", "s3cr3t")
    maintenance = SimpleNamespace(draining=False, active=0)
    maintenance.prepare = AsyncMock(side_effect=RuntimeError("drain failed"))
    request = SimpleNamespace(app=SimpleNamespace(
        state=SimpleNamespace(job_scheduler=MagicMock(), desktop_server=SimpleNamespace(should_exit=False))))
    with patch("app.service.desktop_maintenance.maintenance", maintenance), \
         patch("app.service.task_manager.TaskManager.get_instance", return_value=MagicMock()):
        response = asyncio.run(
            system_api.prepare_desktop_migration(request, secret="s3cr3t")
        )
    assert response.code != 0
    assert response.code != 0
    assert "drain failed" in response.msg


# ------------------------------- desktop_network ---------------------------


def test_desktop_network_returns_lan_urls(monkeypatch):
    monkeypatch.setenv("TS_DESKTOP", "1")
    monkeypatch.setenv("TS_DESKTOP_PORT", "3180")
    lan_urls = MagicMock(return_value=["http://10.0.0.2:3180", "http://192.168.1.5:3180"])
    user = SimpleNamespace(id="u-1", is_superuser=False)
    with patch("app.utils.desktop_network.lan_urls", lan_urls):
        response = system_api.desktop_network(current_user=user)
    assert response.code == 0
    assert response.data["port"] == 3180
    assert response.data["urls"] == ["http://10.0.0.2:3180", "http://192.168.1.5:3180"]
    lan_urls.assert_called_once_with(3180)


def test_desktop_network_404_when_not_desktop_mode(monkeypatch):
    monkeypatch.delenv("TS_DESKTOP", raising=False)
    user = SimpleNamespace(id="u-1", is_superuser=False)
    with pytest.raises(HTTPException) as exc:
        system_api.desktop_network(current_user=user)
    assert exc.value.status_code == 404


# -------------------------- download_cached_app_update ---------------------


def test_download_cached_app_update_returns_file_response(monkeypatch, tmp_path):
    monkeypatch.setenv("TS_DESKTOP", "1")
    cached = tmp_path / "TrailSnap-0.18.1.apk"
    cached.write_bytes(b"fake-apk-content")
    with patch(
        "app.service.app_update.cached_apk_path",
        return_value=str(cached),
    ):
        response = asyncio.run(system_api.download_cached_app_update(version="0.18.1"))
    assert response.path == str(cached)
    assert response.headers["Cache-Control"] == "private, max-age=3600"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.media_type == "application/vnd.android.package-archive"


def test_download_cached_app_update_404_when_invalid_version(monkeypatch):
    """Non-semver version strings must normalize to empty and surface 404."""
    with patch("app.service.app_update.cached_apk_path", return_value=None) as cached_path:
        with pytest.raises(HTTPException) as exc:
            asyncio.run(system_api.download_cached_app_update(version="not-a-version"))
    assert exc.value.status_code == 404
    cached_path.assert_called_once_with("")


def test_download_cached_app_update_404_when_no_cache(monkeypatch):
    """Valid version but no cached APK must also surface 404."""
    with patch("app.service.app_update.cached_apk_path", return_value=None):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(system_api.download_cached_app_update(version="0.18.1"))
    assert exc.value.status_code == 404
    assert "App update is not cached" in exc.value.detail
