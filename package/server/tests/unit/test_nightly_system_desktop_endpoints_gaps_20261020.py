"""Desktop secret, safe migration, network and cached update endpoint coverage."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from app.api import system as system_api

pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


@pytest.mark.parametrize('desktop,expected,provided', [
    ('0', 's', 's'), ('1', '', 's'), ('1', 's', None), ('1', 's', 'wrong'),
])
def test_desktop_secret_rejects_unauthorized_calls(monkeypatch, desktop, expected, provided):
    monkeypatch.setenv('TS_DESKTOP', desktop)
    monkeypatch.setenv('TS_DESKTOP_SESSION_SECRET', expected)
    with pytest.raises(HTTPException) as error:
        system_api._require_desktop_secret(provided)
    assert error.value.status_code == 404


def test_independent_extension_endpoints_are_removed():
    paths = {route.path for route in system_api.router.routes}
    assert not any('ai-extension' in path for path in paths)


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
