"""Nightly coverage for ``app/utils/windows_paths.py`` and
``app/service/desktop_maintenance.py`` (2026-10-26).

The 2026-10-26 backend coverage scan listed

* ``utils/windows_paths.py`` at 85.0% -- the Win32 extended-path prefixes and
  the ``PermissionError`` retry of ``publish_directory`` were never exercised
  (they only trigger on Windows, and the CI container runs on Linux);
* ``service/desktop_maintenance.py`` at 84.2% -- the "desktop is verifying an
  update" 503 gate, the draining gate and the in-flight request accounting of
  the migration flow were never exercised.

Both modules are pure ASGI / path helpers, so they are driven directly.
"""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

pytestmark = [pytest.mark.smoke]


# ---------------------------------------------------------------------------
# utils/windows_paths.py
# ---------------------------------------------------------------------------


def test_filesystem_path_is_untouched_on_posix(monkeypatch):
    from app.utils.windows_paths import filesystem_path

    monkeypatch.setattr(os, "name", "posix")
    assert filesystem_path(Path("/tmp/photos")) == "/tmp/photos"


def test_filesystem_path_adds_the_extended_prefix_on_windows(monkeypatch):
    from app.utils.windows_paths import filesystem_path

    monkeypatch.setattr(os, "name", "nt")
    value = filesystem_path(Path("C:/Users/tester/photos"))
    assert value.startswith("\\\\?\\")


def test_filesystem_path_keeps_an_already_extended_path(monkeypatch):
    from app.utils.windows_paths import filesystem_path

    monkeypatch.setattr(os, "name", "nt")
    extended = Path("\\\\?\\C:\\already\\extended")
    assert filesystem_path(extended).startswith("\\\\?\\")


def test_filesystem_path_converts_a_unc_share(monkeypatch):
    from app.utils.windows_paths import filesystem_path

    monkeypatch.setattr(os, "name", "nt")
    value = filesystem_path(Path("//server/share/photos"))
    assert value.startswith("\\\\?\\UNC\\server\\share")


def test_publish_directory_renames_the_source(tmp_path):
    from app.utils.windows_paths import publish_directory

    source = tmp_path / "src"
    source.mkdir()
    target = tmp_path / "dst"

    publish_directory(source, target)

    assert target.exists()
    assert not source.exists()


def test_publish_directory_retries_while_the_target_is_locked(monkeypatch, tmp_path):
    """A scanner holding the target open must not abort the publish."""
    from app.utils import windows_paths

    source = tmp_path / "src"
    source.mkdir()
    target = tmp_path / "dst"

    attempts = {"count": 0}
    real_rename = Path.rename

    def flaky_rename(self, other):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise PermissionError("file is in use")
        return real_rename(self, other)

    # The retry loop only exists on Windows: ``publish_directory`` re-raises
    # the PermissionError straight away when ``os.name != "nt"``. Pretend to
    # be Windows so the retry path is the one under test on every platform
    # (the CI container runs on Linux).
    monkeypatch.setattr(os, "name", "nt")
    monkeypatch.setattr(Path, "rename", flaky_rename)
    # Patch the module level ``time`` reference instead of the stdlib module so
    # the sleeping process wide ``time.sleep`` is left alone.
    monkeypatch.setattr(
        windows_paths,
        "time",
        SimpleNamespace(monotonic=time.monotonic, sleep=lambda _seconds: None),
    )

    windows_paths.publish_directory(source, target)

    assert attempts["count"] == 2
    assert target.exists()


def test_publish_directory_gives_up_after_the_deadline(monkeypatch, tmp_path):
    from app.utils import windows_paths

    source = tmp_path / "src"
    source.mkdir()
    target = tmp_path / "dst"

    clock = {"calls": 0}

    def fake_monotonic():
        clock["calls"] += 1
        # first call builds the deadline, later calls are already past it
        return 0.0 if clock["calls"] == 1 else 100.0

    # Same as above: on POSIX the PermissionError is re-raised before the
    # deadline is ever consulted, so the deadline branch needs a fake Windows.
    monkeypatch.setattr(os, "name", "nt")
    monkeypatch.setattr(Path, "rename", lambda self, other: (_ for _ in ()).throw(PermissionError("locked")))
    monkeypatch.setattr(
        windows_paths,
        "time",
        SimpleNamespace(monotonic=fake_monotonic, sleep=lambda _seconds: None),
    )

    with pytest.raises(PermissionError):
        windows_paths.publish_directory(source, target)


# ---------------------------------------------------------------------------
# service/desktop_maintenance.py
# ---------------------------------------------------------------------------


def _send_once():
    """Collect the ASGI response of a single ``send`` call."""
    captured = {}

    async def send(message):
        captured.update(message)

    return captured, send


def _run_middleware(middleware, scope, app):
    captured, send = _send_once()
    asyncio.run(middleware.middleware(scope, None, send, app))
    return captured


def test_desktop_verification_mode_blocks_the_gallery(monkeypatch):
    from app.service.desktop_maintenance import DesktopMaintenance

    monkeypatch.setenv("TS_DESKTOP_VERIFY", "1")
    maintenance = DesktopMaintenance()

    called = {"app": False}

    async def app(scope, receive, send):
        called["app"] = True

    captured = _run_middleware(
        maintenance,
        {"type": "http", "path": "/api/photos"},
        app,
    )

    assert called["app"] is False
    assert captured["status"] == 503


def test_desktop_verification_mode_lets_the_health_check_through(monkeypatch):
    from app.service.desktop_maintenance import DesktopMaintenance

    monkeypatch.setenv("TS_DESKTOP_VERIFY", "1")
    maintenance = DesktopMaintenance()

    called = {"app": False}

    async def app(scope, receive, send):
        called["app"] = True

    captured = _run_middleware(
        maintenance,
        {"type": "http", "path": "/api/health-check"},
        app,
    )

    assert called["app"] is True
    assert "status" not in captured


def test_draining_rejects_new_requests(monkeypatch):
    from app.service.desktop_maintenance import DesktopMaintenance

    monkeypatch.delenv("TS_DESKTOP_VERIFY", raising=False)
    maintenance = DesktopMaintenance()
    maintenance.draining = True

    async def app(scope, receive, send):
        raise AssertionError("the app must not be reached while draining")

    captured = _run_middleware(
        maintenance,
        {"type": "http", "path": "/api/photos"},
        app,
    )

    assert captured["status"] == 503
    headers = {name.lower(): value for name, value in captured.get("headers", [])}
    assert headers.get(b"retry-after") == b"30"


def test_prepare_migration_is_always_allowed(monkeypatch):
    """The migration trigger itself must not be blocked by the drain gate."""
    from app.service.desktop_maintenance import DesktopMaintenance

    monkeypatch.delenv("TS_DESKTOP_VERIFY", raising=False)
    maintenance = DesktopMaintenance()
    maintenance.draining = True

    called = {"app": False}

    async def app(scope, receive, send):
        called["app"] = True

    _run_middleware(
        maintenance,
        {"type": "http", "path": "/api/system/desktop/prepare-migration"},
        app,
    )

    assert called["app"] is True


def test_in_flight_requests_are_tracked_and_released():
    from app.service.desktop_maintenance import DesktopMaintenance

    maintenance = DesktopMaintenance()
    seen = {}

    async def app(scope, receive, send):
        seen["active"] = maintenance.active

    async def run():
        await maintenance.middleware({"type": "http", "path": "/api/photos"}, None, None, app)

    asyncio.run(run())

    assert seen["active"] == 1
    assert maintenance.active == 0


def test_event_streams_are_not_counted_as_in_flight():
    """SSE subscriptions never finish, so they must not block the drain."""
    from app.service.desktop_maintenance import DesktopMaintenance

    maintenance = DesktopMaintenance()
    seen = {}

    async def app(scope, receive, send):
        seen["active"] = maintenance.active

    async def run():
        await maintenance.middleware({"type": "http", "path": "/api/tasks/events"}, None, None, app)

    asyncio.run(run())

    assert seen["active"] == 0
    assert maintenance.active == 0


def test_prepare_drains_before_migrating(monkeypatch):
    """``prepare`` stops the scheduler, waits for in-flight work, then migrates."""
    from app.service import desktop_maintenance as module

    calls = []

    class Scheduler:
        def stop(self, wait=True):
            calls.append(("scheduler.stop", wait))

    class Manager:
        def drain_for_migration(self):
            calls.append(("manager.drain_for_migration", None))

    def fake_wait_for_initialization():
        calls.append(("wait_for_initialization", None))

    monkeypatch.setattr(
        module.asyncio,
        "to_thread",
        lambda func, *args, **kwargs: asyncio.sleep(0, result=func(*args, **kwargs)),
    )
    monkeypatch.setattr(
        "railway.initialization.wait_for_initialization",
        fake_wait_for_initialization,
    )

    maintenance = module.DesktopMaintenance()
    asyncio.run(maintenance.prepare(Scheduler(), Manager()))

    assert calls[0] == ("scheduler.stop", True)
    assert ("wait_for_initialization", None) in calls
    assert calls[-1] == ("manager.drain_for_migration", None)
    assert maintenance.draining is True
