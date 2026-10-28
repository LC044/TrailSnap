"""2026-10-28 nightly coverage for ``app/service/task_manager.py``.

The 2026-10-28 backend coverage scan reported ``service/task_manager.py`` at
78.7% with 86 uncovered lines.  The uncovered code is the *worker lifecycle*:
starting, draining, restarting and stopping the background worker process.

* ``start_worker_if_needed`` -- the lazy start and the snapshot it publishes;
* ``start_worker_for_pending_tasks`` -- the "only spawn when work exists" rule;
* ``stop_worker`` -- graceful terminate, then kill;
* ``drain_for_migration`` -- the "never lose accepted work" drain, including
  the hard failure when the worker exits with a non-zero code;
* ``restart_worker`` -- the immediate and the graceful (draining) restart;
* ``recover_bundled_ai_tasks`` -- the one-time legacy extension cleanup;
* the pause / resume bookkeeping around the persisted category list.

Everything is driven through mocks: no worker process is really spawned.
"""

from __future__ import annotations

import os
import threading
from unittest.mock import MagicMock, patch

import pytest


pytestmark = [pytest.mark.smoke, pytest.mark.module_task]


def _manager():
    from app.service.task_manager import TaskManager

    manager = TaskManager()
    manager.publish_event = MagicMock()
    manager._publish_active_tasks_snapshot = MagicMock()
    return manager


def _process(alive=True, exitcode=0):
    process = MagicMock()
    process.is_alive.return_value = alive
    process.exitcode = exitcode
    return process


# ---------------------------------------------------------------------------
# lazy start
# ---------------------------------------------------------------------------


def test_start_worker_if_needed_publishes_a_snapshot_after_a_start():
    manager = _manager()
    with patch.object(manager, "_start_worker_locked", return_value=True) as start:
        manager.start_worker_if_needed()
    start.assert_called_once()
    manager._publish_active_tasks_snapshot.assert_called_once()


def test_start_worker_if_needed_stays_quiet_when_the_worker_is_already_running():
    manager = _manager()
    with patch.object(manager, "_start_worker_locked", return_value=False):
        manager.start_worker_if_needed()
    manager._publish_active_tasks_snapshot.assert_not_called()


def test_start_worker_if_needed_does_nothing_while_draining():
    manager = _manager()
    manager._migration_draining = True
    with patch.object(manager, "_start_worker_locked", return_value=True) as start:
        manager.start_worker_if_needed()
    start.assert_not_called()


def test_start_worker_if_needed_wakes_a_waiting_worker():
    manager = _manager()
    manager._worker_wake_event = MagicMock()
    with patch.object(manager, "_start_worker_locked", return_value=False):
        manager.start_worker_if_needed()
    manager._worker_wake_event.set.assert_called_once()


def test_start_worker_for_pending_tasks_skips_the_worker_without_work():
    manager = _manager()
    with patch("app.service.task_manager.SessionLocal") as session:
        with patch.object(manager, "_count_dispatchable", return_value=0):
            with patch.object(manager, "start_worker_if_needed") as start:
                assert manager.start_worker_for_pending_tasks() is False
    start.assert_not_called()


def test_start_worker_for_pending_tasks_starts_the_worker_with_work():
    manager = _manager()
    with patch("app.service.task_manager.SessionLocal"):
        with patch.object(manager, "_count_dispatchable", return_value=3):
            with patch.object(manager, "start_worker_if_needed") as start:
                assert manager.start_worker_for_pending_tasks() is True
    start.assert_called_once()


def test_start_worker_locked_reuses_a_live_worker():
    manager = _manager()
    manager.worker_process = _process(alive=True)
    with patch("app.service.task_manager.multiprocessing.Process") as process:
        assert manager._start_worker_locked() is False
    process.assert_not_called()


def test_start_worker_locked_reaps_a_dead_worker():
    manager = _manager()
    dead = _process(alive=False)
    manager.worker_process = dead
    with patch("app.service.task_manager.multiprocessing.Process") as process:
        with patch("app.service.task_manager.multiprocessing.Queue"):
            with patch("app.service.task_manager.multiprocessing.Event"):
                with patch("app.service.task_manager.threading.Thread"):
                    manager._start_worker_locked()
    dead.join.assert_called_once()
    process.assert_called_once()


def test_start_worker_locked_refuses_to_start_while_draining():
    manager = _manager()
    manager._migration_draining = True
    assert manager._start_worker_locked() is False


# ---------------------------------------------------------------------------
# stop / drain
# ---------------------------------------------------------------------------


def test_stop_worker_terminates_a_live_worker():
    manager = _manager()
    process = _process(alive=True)
    manager.worker_process = process
    manager.stop_worker()
    process.terminate.assert_called_once()
    process.join.assert_called_once_with(timeout=5)
    assert manager.worker_process is None
    assert manager._worker_stop_event is None


def test_stop_worker_kills_a_worker_that_ignores_the_terminate():
    manager = _manager()
    process = _process(alive=True)
    # The worker is alive for the terminate check and for the kill check.
    process.is_alive.return_value = True
    manager.worker_process = process
    manager.stop_worker()
    process.terminate.assert_called_once()
    process.kill.assert_called_once()


def test_stop_worker_ignores_a_dead_worker():
    manager = _manager()
    process = _process(alive=False)
    manager.worker_process = process
    manager.stop_worker()
    process.terminate.assert_not_called()
    assert manager.worker_process is None


def test_drain_for_migration_joins_the_worker():
    manager = _manager()
    process = _process(alive=False, exitcode=0)
    manager.worker_process = process
    manager._worker_stop_event = MagicMock()
    manager.drain_for_migration()
    process.join.assert_called_once_with()
    assert manager._migration_draining is True
    assert manager.worker_process is None


def test_drain_for_migration_fails_when_the_worker_crashed():
    manager = _manager()
    process = _process(alive=False, exitcode=3)
    manager.worker_process = process
    with pytest.raises(RuntimeError) as excinfo:
        manager.drain_for_migration()
    assert "后台任务异常退出" in str(excinfo.value)


# ---------------------------------------------------------------------------
# restart
# ---------------------------------------------------------------------------


def test_restart_worker_applies_immediately_without_graceful_drain():
    manager = _manager()
    with patch.object(manager, "stop_worker") as stop:
        with patch.object(manager, "start_worker_if_needed") as start:
            assert manager.restart_worker() == {"status": "applied"}
    stop.assert_called_once()
    start.assert_called_once()


def test_restart_worker_applies_immediately_when_the_worker_is_gone():
    manager = _manager()
    manager.worker_process = _process(alive=False)
    manager._worker_stop_event = MagicMock()
    with patch.object(manager, "stop_worker") as stop:
        with patch.object(manager, "start_worker_if_needed") as start:
            assert manager.restart_worker(graceful=True) == {"status": "applied"}
    stop.assert_called_once()
    start.assert_called_once()


def test_restart_worker_drains_a_running_worker():
    manager = _manager()
    manager.worker_process = _process(alive=True)
    manager._worker_stop_event = MagicMock()
    with patch("app.service.task_manager.threading.Thread") as thread:
        assert manager.restart_worker(graceful=True) == {"status": "draining"}
    thread.assert_called_once()
    manager._worker_stop_event.set.assert_called_once()
    assert manager._restart_requested is True
    manager.publish_event.assert_called_with("task.worker", {"status": "draining"})


def test_restart_worker_reports_draining_while_a_restart_is_running():
    manager = _manager()
    manager.worker_process = _process(alive=True)
    manager._worker_stop_event = MagicMock()
    manager._restart_thread = MagicMock()
    manager._restart_thread.is_alive.return_value = True
    assert manager.restart_worker(graceful=True) == {"status": "draining"}


def test_finish_graceful_restart_terminates_a_stuck_worker():
    manager = _manager()
    process = _process(alive=True)
    manager._restart_requested = True
    with patch.object(manager, "_start_worker_locked", return_value=False):
        manager._finish_graceful_restart(process)
    process.terminate.assert_called_once()
    manager.publish_event.assert_called_with("task.worker", {"status": "applied"})


def test_finish_graceful_restart_restarts_the_worker_when_asked():
    manager = _manager()
    process = _process(alive=False)
    manager._restart_requested = True
    manager.worker_process = process
    with patch.object(manager, "_start_worker_locked", return_value=True) as start:
        manager._finish_graceful_restart(process)
    start.assert_called_once()


# ---------------------------------------------------------------------------
# watchdog
# ---------------------------------------------------------------------------


def test_start_watchdog_starts_a_single_thread():
    manager = _manager()
    with patch("app.service.task_manager.threading.Thread") as thread:
        manager.start_watchdog()
        manager.start_watchdog()
    thread.assert_called_once()
    assert manager._watchdog_running is True


def test_stop_watchdog_joins_the_thread():
    manager = _manager()
    manager._watchdog_running = True
    manager._watchdog_thread = MagicMock()
    manager._watchdog_thread.is_alive.return_value = True
    manager.stop_watchdog()
    manager._watchdog_thread.join.assert_called_once_with(timeout=2)
    assert manager._watchdog_running is False


# ---------------------------------------------------------------------------
# bundled AI recovery
# ---------------------------------------------------------------------------


def test_recover_bundled_ai_tasks_is_skipped_outside_the_desktop():
    manager = _manager()
    with patch.dict(os.environ, {"TS_DESKTOP_BUNDLED_AI": "0"}):
        with patch("app.service.desktop_ai.recover_legacy_extension_waits") as recover:
            manager.recover_bundled_ai_tasks()
    recover.assert_not_called()


def test_recover_bundled_ai_tasks_runs_on_the_desktop():
    manager = _manager()
    with patch.dict(os.environ, {"TS_DESKTOP_BUNDLED_AI": "1"}):
        with patch("app.service.desktop_ai.recover_legacy_extension_waits") as recover:
            with patch("app.service.task_manager.SessionLocal"):
                manager.recover_bundled_ai_tasks()
    recover.assert_called_once()


# ---------------------------------------------------------------------------
# persisted category state
# ---------------------------------------------------------------------------


def test_load_system_state_falls_back_to_the_default_on_failure():
    manager = _manager()
    session = MagicMock()
    session.query.side_effect = RuntimeError("db down")
    with patch("app.service.task_manager.SessionLocal", return_value=session):
        assert manager._load_system_state("paused_categories", ["SCAN_FOLDER"]) == ["SCAN_FOLDER"]


def test_load_system_state_parses_a_json_value():
    manager = _manager()
    state = MagicMock()
    state.value = '["SCAN_FOLDER"]'
    session = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = state
    with patch("app.service.task_manager.SessionLocal", return_value=session):
        assert manager._load_system_state("paused_categories", []) == ["SCAN_FOLDER"]


def test_save_system_state_raises_in_strict_mode():
    manager = _manager()
    session = MagicMock()
    session.query.side_effect = RuntimeError("db down")
    with patch("app.service.task_manager.SessionLocal", return_value=session):
        with pytest.raises(RuntimeError):
            manager._save_system_state("fast_mode", True, strict=True)


def test_save_system_state_swallows_errors_without_strict_mode():
    manager = _manager()
    session = MagicMock()
    session.query.side_effect = RuntimeError("db down")
    with patch("app.service.task_manager.SessionLocal", return_value=session):
        manager._save_system_state("fast_mode", True)


def test_pause_category_publishes_the_new_state():
    manager = _manager()
    with patch.object(manager, "_load_system_state", return_value=[]):
        with patch.object(manager, "_save_system_state") as save:
            manager.pause_category("SCAN_FOLDER")
    save.assert_called_once_with("paused_categories", ["SCAN_FOLDER"])
    manager.publish_event.assert_called_with("task.category", {"category": "SCAN_FOLDER", "status": "paused"})


def test_resume_category_reactivates_and_starts_the_worker():
    manager = _manager()
    with patch.object(manager, "_load_system_state", return_value=["SCAN_FOLDER"]):
        with patch.object(manager, "_save_system_state") as save:
            with patch.object(manager, "start_worker_if_needed") as start:
                manager.resume_category("SCAN_FOLDER")
    save.assert_called_once_with("paused_categories", [])
    start.assert_called_once()
    manager.publish_event.assert_called_with("task.category", {"category": "SCAN_FOLDER", "status": "active"})


def test_resume_category_ignores_an_unknown_category():
    manager = _manager()
    with patch.object(manager, "_load_system_state", return_value=[]):
        with patch.object(manager, "_save_system_state") as save:
            with patch.object(manager, "start_worker_if_needed") as start:
                manager.resume_category("SCAN_FOLDER")
    save.assert_not_called()
    start.assert_not_called()


def test_get_grouped_status_refreshes_the_paused_categories():
    manager = _manager()
    with patch.object(manager, "_load_system_state", return_value=["SCAN_FOLDER"]):
        with patch("app.service.task_manager.crud_task.get_grouped_status", return_value={"scan": 1}) as grouped:
            assert manager.get_grouped_status(MagicMock()) == {"scan": 1}
    assert manager.paused_categories == {"SCAN_FOLDER"}

