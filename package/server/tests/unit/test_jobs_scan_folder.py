"""Scheduled and startup gallery scan triggers."""
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.service.jobs import scan_folder

pytestmark = [pytest.mark.smoke, pytest.mark.module_jobs]


@pytest.mark.parametrize("queued", [False, True])
def test_scan_folder_job_uses_shared_queue_guard(monkeypatch, queued, caplog):
    session = MagicMock()
    db = session.__enter__.return_value
    manager = MagicMock()
    manager.try_enqueue_gallery_scan.return_value = queued
    monkeypatch.setattr(scan_folder, "SessionLocal", lambda: session)
    monkeypatch.setattr(scan_folder.TaskManager, "get_instance", lambda: manager)

    with caplog.at_level("INFO"):
        scan_folder.scan_folder_job()

    manager.try_enqueue_gallery_scan.assert_called_once_with(db, {})
    session.__exit__.assert_called_once()
    assert ("enqueued" if queued else "skipping") in caplog.text


def test_scan_folder_job_logs_and_swallows_exception(monkeypatch, caplog):
    monkeypatch.setattr(scan_folder, "SessionLocal", MagicMock(side_effect=RuntimeError("db down")))
    scan_folder.scan_folder_job()
    assert "db down" in caplog.text


def test_startup_retries_until_scan_is_covered(monkeypatch):
    monkeypatch.setattr(scan_folder, "startup_scan_enabled", lambda: True)
    job = MagicMock(side_effect=[False, True])
    monkeypatch.setattr(scan_folder, "startup_scan_folder_job", job)
    scheduler = MagicMock()
    start = datetime(2026, 1, 1, 12)
    clock = MagicMock()
    clock.now.side_effect = [start, start + timedelta(seconds=30)]
    monkeypatch.setattr(scan_folder, "datetime", clock)

    scan_folder.schedule_startup_scan(scheduler)
    initial_name, initial_time, run = scheduler.register_once_job.call_args.args
    job.assert_not_called()
    run()
    retry_name, retry_time, retry = scheduler.register_once_job.call_args.args
    retry()

    assert initial_name == retry_name == "scan_folder_startup"
    assert initial_time == start + timedelta(seconds=30)
    assert retry_time == initial_time + timedelta(seconds=10)
    assert scheduler.register_once_job.call_count == 2
    assert job.call_count == 2


@pytest.mark.parametrize(("desktop", "verify", "enabled", "registered", "expected"), [
    ("0", "0", True, True, True),
    ("1", "0", True, True, True),
    ("1", "1", True, True, False),
    ("0", "0", False, True, False),
    ("0", "0", True, False, False),
])
def test_startup_scan_modes(monkeypatch, desktop, verify, enabled, registered, expected):
    monkeypatch.setenv("TS_DESKTOP", desktop)
    monkeypatch.setenv("TS_DESKTOP_VERIFY", verify)
    monkeypatch.setattr(scan_folder.system_config.config, "scan_on_startup", enabled)
    db = MagicMock()
    db.__enter__.return_value = db
    db.query.return_value.all.return_value = [
        SimpleNamespace(settings={"storage": {"external_directories": ["/gallery"] if registered else []}}),
    ]
    monkeypatch.setattr(scan_folder, "SessionLocal", lambda: db)
    manager = MagicMock()
    monkeypatch.setattr(scan_folder.TaskManager, "get_instance", lambda: manager)

    scan_folder.startup_scan_folder_job()

    if expected:
        manager.try_enqueue_gallery_scan.assert_called_once_with(db, {"import_only": True})
    else:
        manager.try_enqueue_gallery_scan.assert_not_called()
