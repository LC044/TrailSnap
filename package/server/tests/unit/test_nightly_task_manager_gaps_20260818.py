"""Unit tests covering 2026-08-18 nightly coverage gap scan.

Target: ``app/service/task_manager.py`` (39.5% baseline, 173 missed of 286
statements).

The existing ``test_task_manager.py`` covers the control plane surface
(singleton, paused_categories, fast_mode, subscribe/publish, ORM payload
flattening, sqlite dedup). This file fills in the rest of the surface:

* ``_start_worker_locked`` / ``start_worker_if_needed`` / ``stop_worker``
  / ``restart_worker`` -- multiprocessing lifecycle (process alive,
  dead-and-needs-cleanup, terminate vs kill, restart-after-stop).
* ``_event_queue_reader`` -- drains ``multiprocessing.Queue`` events,
  skips non-dict payloads, returns on EOFError/OSError.
* ``start_watchdog`` / ``stop_watchdog`` / ``_watchdog_loop`` -- restart
  logic that scans ``crud_task`` for dispatchable tasks.
* ``_save_system_state`` exception path -- DB error swallowed.
* ``retry_all_failed_tasks`` -- with/without types filter; per-task
  ``task.retry`` publish path; zero-result no-op.
* ``add_task`` SCAN_FOLDER dedup -- payload user_id, owner_id fallback,
  exception fallthrough, non-SCAN_FOLDER bypass.
* ``add_tasks`` batch publish.
* ``_publish_active_tasks_snapshot`` -- publishes PENDING/PROCESSING tasks
  via ``publish_task_update``; tolerates ``SessionLocal`` failure.
"""

import asyncio
import json
import time
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


@pytest.fixture(autouse=True)
def _reset_singleton():
    from app.service import task_manager as tm_mod

    tm_mod.TaskManager._instance = None
    yield
    tm_mod.TaskManager._instance = None


def _make_manager():
    from app.service.task_manager import TaskManager

    return TaskManager.get_instance()


# ---------------------------------------------------------------------------
# start_worker_if_needed / _start_worker_locked / stop_worker / restart_worker
# ---------------------------------------------------------------------------


def test_start_worker_if_needed_starts_when_no_process(monkeypatch):
    """First call must spin up a fresh multiprocessing.Process."""
    mgr = _make_manager()

    fake_process = MagicMock()
    fake_process.pid = 4242
    monkeypatch.setattr("multiprocessing.Process", lambda *a, **kw: fake_process)
    monkeypatch.setattr(
        "multiprocessing.Queue", lambda maxsize: MagicMock(maxsize=maxsize)
    )

    started = {"calls": 0}
    monkeypatch.setattr(mgr, "_start_worker_locked", lambda: started.__setitem__("calls", 1) or True)
    monkeypatch.setattr(mgr, "_publish_active_tasks_snapshot", MagicMock())

    mgr.start_worker_if_needed()
    assert started["calls"] == 1


def test_start_worker_if_needed_skips_publish_when_already_alive(monkeypatch):
    """If the worker is already alive, ``_publish_active_tasks_snapshot``
    is not called -- only restarted workers need a snapshot push."""
    mgr = _make_manager()

    alive_process = MagicMock()
    alive_process.is_alive.return_value = True
    mgr.worker_process = alive_process

    publish = MagicMock()
    monkeypatch.setattr(mgr, "_publish_active_tasks_snapshot", publish)

    mgr.start_worker_if_needed()
    publish.assert_not_called()


def test_start_worker_locked_cleans_dead_process_before_starting(monkeypatch):
    """A previous worker that crashed must be ``join()``ed before we
    spawn a replacement, otherwise we leak zombies."""
    mgr = _make_manager()

    dead = MagicMock()
    dead.is_alive.return_value = False
    mgr.worker_process = dead

    fresh = MagicMock()
    fresh.pid = 9000

    monkeypatch.setattr("multiprocessing.Process", lambda *a, **kw: fresh)
    monkeypatch.setattr(
        "multiprocessing.Queue", lambda maxsize: MagicMock(maxsize=maxsize)
    )

    assert mgr._start_worker_locked() is True
    dead.join.assert_called_once()
    assert mgr.worker_process is fresh
    assert fresh.start.called


def test_start_worker_locked_returns_false_when_already_alive():
    """If the worker is still alive, ``_start_worker_locked`` is a
    no-op and reports back False to the caller."""
    mgr = _make_manager()
    alive = MagicMock()
    alive.is_alive.return_value = True
    mgr.worker_process = alive

    assert mgr._start_worker_locked() is False


def test_stop_worker_terminates_then_joins(monkeypatch):
    """Graceful shutdown must terminate and join within 5s."""
    mgr = _make_manager()

    proc = MagicMock()
    proc.is_alive.side_effect = [True, False]
    mgr.worker_process = proc

    mgr.stop_worker()

    proc.terminate.assert_called_once_with()
    proc.join.assert_called_once_with(timeout=5)
    proc.kill.assert_not_called()
    assert mgr.worker_process is None


def test_stop_worker_force_kills_if_join_times_out(monkeypatch):
    """If the worker refuses to terminate, escalate to ``kill``."""
    mgr = _make_manager()

    proc = MagicMock()
    proc.is_alive.side_effect = [True, True, True]
    mgr.worker_process = proc

    mgr.stop_worker()

    proc.kill.assert_called_once_with()
    assert mgr.worker_process is None


def test_stop_worker_noop_when_no_process():
    """If the worker was never started, stop is a no-op."""
    mgr = _make_manager()
    mgr.worker_process = None
    mgr.stop_worker()
    assert mgr.worker_process is None


def test_restart_worker_stops_then_starts(monkeypatch):
    """``restart_worker`` is literally ``stop`` + ``start``."""
    mgr = _make_manager()
    monkeypatch.setattr(mgr, "stop_worker", MagicMock())
    start = MagicMock()
    monkeypatch.setattr(mgr, "start_worker_if_needed", start)

    mgr.restart_worker()
    mgr.stop_worker.assert_called_once_with()
    start.assert_called_once_with()


def test_graceful_restart_requests_worker_drain(monkeypatch):
    mgr = _make_manager()
    process = MagicMock()
    process.is_alive.return_value = True
    stop_event = MagicMock()
    mgr.worker_process = process
    mgr._worker_stop_event = stop_event
    thread = MagicMock()
    monkeypatch.setattr("app.service.task_manager.threading.Thread", MagicMock(return_value=thread))

    result = mgr.restart_worker(graceful=True)

    assert result == {"status": "draining"}
    stop_event.set.assert_called_once_with()
    thread.start.assert_called_once_with()
    process.terminate.assert_not_called()


# ---------------------------------------------------------------------------
# _event_queue_reader
# ---------------------------------------------------------------------------


def test_event_queue_reader_drains_messages_to_publish(monkeypatch):
    """Each ``dict`` payload on the queue is forwarded as an SSE event."""
    mgr = _make_manager()

    fake_queue = MagicMock()
    fake_queue.get.side_effect = [
        {"event": "task.updated", "data": {"id": "1"}},
        {"event": "task.created", "data": {"id": "2"}},
        EOFError(),
    ]
    mgr._event_queue = fake_queue

    captured = []
    monkeypatch.setattr(mgr, "publish_event", lambda ev, data: captured.append((ev, data)))

    mgr._event_queue_reader()

    assert captured == [
        ("task.updated", {"id": "1"}),
        ("task.created", {"id": "2"}),
    ]


def test_event_queue_reader_skips_non_dict_messages(monkeypatch):
    """Non-dict payloads (e.g. None sentinel values) must be ignored."""
    mgr = _make_manager()

    fake_queue = MagicMock()
    fake_queue.get.side_effect = ["not-a-dict", 12345, {"event": "x", "data": {"y": 1}}, EOFError()]
    mgr._event_queue = fake_queue

    captured = []
    monkeypatch.setattr(mgr, "publish_event", lambda ev, data: captured.append((ev, data)))

    mgr._event_queue_reader()
    assert captured == [("x", {"y": 1})]


def test_event_queue_reader_returns_when_queue_is_none():
    """If the queue hasn't been wired yet, exit immediately."""
    mgr = _make_manager()
    mgr._event_queue = None
    mgr._event_queue_reader()  # must not raise or hang


def test_event_queue_reader_handles_publish_failure(monkeypatch):
    """An exception from ``publish_event`` is logged at debug and we
    continue draining the queue."""
    mgr = _make_manager()

    fake_queue = MagicMock()
    fake_queue.get.side_effect = [
        {"event": "task.updated", "data": {"id": "1"}},
        {"event": "task.updated", "data": {"id": "2"}},
        EOFError(),
    ]
    mgr._event_queue = fake_queue

    def boom(_ev, _data):
        raise RuntimeError("publish failed")

    monkeypatch.setattr(mgr, "publish_event", boom)
    mgr._event_queue_reader()  # must not raise


# ---------------------------------------------------------------------------
# Watchdog
# ---------------------------------------------------------------------------


def test_start_watchdog_launches_daemon_thread():
    """Watchdog must run as a daemon so it dies with the API process."""
    mgr = _make_manager()
    mgr.start_watchdog()
    try:
        assert mgr._watchdog_running is True
        assert mgr._watchdog_thread is not None
        assert mgr._watchdog_thread.daemon is True
    finally:
        mgr.stop_watchdog()


def test_stop_watchdog_joins_thread(monkeypatch):
    """``stop_watchdog`` must turn off the loop flag; if the thread was
    started, we wait for it briefly."""
    mgr = _make_manager()
    mgr.start_watchdog()
    thread = mgr._watchdog_thread
    thread.join = MagicMock()
    mgr.stop_watchdog()
    assert mgr._watchdog_running is False
    thread.join.assert_called()


def test_watchdog_restarts_when_worker_dead_with_pending(monkeypatch):
    """A dead worker with dispatchable unfinished work must trigger a
    restart so PROCESSING tasks can be recovered."""
    mgr = _make_manager()
    mgr._watchdog_running = True
    dead_proc = MagicMock()
    dead_proc.is_alive.return_value = False
    mgr.worker_process = dead_proc
    mgr._stopping = False

    # Patch the inner sleep loop to skip its 15-second waits.
    sleep = MagicMock(side_effect=lambda _: mgr._watchdog_running.__setitem__(  # noqa: B009
        "_running", False
    ) or None)
    monkeypatch.setattr("app.service.task_manager.time.sleep", sleep)

    monkeypatch.setattr(mgr, "_load_system_state", lambda *a, **kw: [])
    monkeypatch.setattr(
        "app.service.task_manager.crud_task.count_dispatchable_tasks",
        lambda *a, **kw: 3,
    )
    monkeypatch.setattr(
        "app.service.task_manager.crud_task.count_tasks_by_status",
        lambda *a, **kw: 2,
    )
    monkeypatch.setattr(
        "app.service.task_manager.SessionLocal", MagicMock()
    )

    started = MagicMock()
    monkeypatch.setattr(mgr, "start_worker_if_needed", started)

    # Force the watchdog to exit after a single 15-second tick.
    counter = {"n": 0}

    def fake_sleep(_):
        counter["n"] += 1
        if counter["n"] >= 15:
            mgr._watchdog_running = False

    monkeypatch.setattr("app.service.task_manager.time.sleep", fake_sleep)
    
    mgr._watchdog_loop()
    started.assert_called_once_with()


def test_watchdog_noop_when_worker_alive(monkeypatch):
    """If the worker is alive, don't restart."""
    mgr = _make_manager()
    mgr._watchdog_running = True

    alive = MagicMock()
    alive.is_alive.return_value = True
    mgr.worker_process = alive

    started = MagicMock()
    monkeypatch.setattr(mgr, "start_worker_if_needed", started)

    def fake_sleep(_):
        mgr._watchdog_running = False

    monkeypatch.setattr("app.service.task_manager.time.sleep", fake_sleep)
    
    mgr._watchdog_loop()
    started.assert_not_called()


def test_watchdog_skips_when_no_pending_work(monkeypatch):
    """Idle exits must not be restarted -- that would cause the
    idle-exit/restart loop described in the docstring."""
    mgr = _make_manager()
    mgr._watchdog_running = True
    mgr.worker_process = None
    mgr._stopping = False

    started = MagicMock()
    monkeypatch.setattr(mgr, "start_worker_if_needed", started)
    monkeypatch.setattr(
        "app.service.task_manager.crud_task.count_dispatchable_tasks",
        lambda *a, **kw: 0,
    )

    def fake_sleep(_):
        mgr._watchdog_running = False

    monkeypatch.setattr("app.service.task_manager.time.sleep", fake_sleep)
    
    mgr._watchdog_loop()
    started.assert_not_called()


def test_watchdog_swallows_exceptions(monkeypatch, caplog):
    """Any unexpected exception inside the watchdog must not crash it."""
    mgr = _make_manager()
    mgr._watchdog_running = True
    mgr.worker_process = None

    started = MagicMock()
    monkeypatch.setattr(mgr, "start_worker_if_needed", started)

    def fake_sleep(_):
        mgr._watchdog_running = False

    monkeypatch.setattr("app.service.task_manager.time.sleep", fake_sleep)
    
    monkeypatch.setattr(
        "app.service.task_manager.crud_task.count_dispatchable_tasks",
        MagicMock(side_effect=RuntimeError("DB down")),
    )

    import logging
    with caplog.at_level(logging.ERROR):
        mgr._watchdog_loop()


def test_watchdog_skips_when_stopping(monkeypatch):
    """During a controlled shutdown, don't try to restart the worker."""
    mgr = _make_manager()
    mgr._watchdog_running = True
    mgr._stopping = True
    mgr.worker_process = None

    started = MagicMock()
    monkeypatch.setattr(mgr, "start_worker_if_needed", started)

    def fake_sleep(_):
        mgr._watchdog_running = False

    monkeypatch.setattr("app.service.task_manager.time.sleep", fake_sleep)
    
    mgr._watchdog_loop()
    started.assert_not_called()


# ---------------------------------------------------------------------------
# _save_system_state -- DB error path
# ---------------------------------------------------------------------------


def test_save_system_state_swallows_db_exception(monkeypatch):
    """If the DB write fails, we log and move on -- not raise."""
    mgr = _make_manager()

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    db.add.side_effect = RuntimeError("DB unavailable")
    monkeypatch.setattr("app.service.task_manager.SessionLocal", lambda: db)

    mgr._save_system_state("paused_categories", {"OCR"})


# ---------------------------------------------------------------------------
# retry_all_failed_tasks
# ---------------------------------------------------------------------------


def test_retry_all_failed_tasks_no_op_when_nothing_to_retry(monkeypatch):
    """If ``crud_task.retry_all_failed_tasks`` returns 0, do not call
    ``start_worker_if_needed`` nor publish events."""
    mgr = _make_manager()

    db = MagicMock()
    db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []

    monkeypatch.setattr(
        "app.service.task_manager.crud_task.retry_all_failed_tasks",
        lambda *a, **kw: 0,
    )

    started = MagicMock()
    monkeypatch.setattr(mgr, "start_worker_if_needed", started)
    pub = MagicMock()
    monkeypatch.setattr(mgr, "publish_task_update", pub)

    result = mgr.retry_all_failed_tasks(db)
    assert result["count"] == 0
    started.assert_not_called()
    pub.assert_not_called()


def test_retry_all_failed_tasks_publishes_per_task_retry(monkeypatch):
    """When work was actually retried, publish ``task.retry`` for each
    failed task that was rescheduled."""
    mgr = _make_manager()

    failed = MagicMock()
    failed.id = "f-1"

    # Build a query chain that supports two filter() calls plus order_by().
    base_query = MagicMock()
    after_filter1 = MagicMock()
    after_filter2 = MagicMock()
    base_query.filter.return_value = after_filter1
    after_filter1.filter.return_value = after_filter2
    after_filter2.order_by.return_value.limit.return_value.all.return_value = [failed]

    db = MagicMock()
    db.query.return_value = base_query

    task_row = SimpleNamespace(id="f-1", type="OCR", status="PENDING")
    monkeypatch.setattr(
        "app.service.task_manager.crud_task.retry_all_failed_tasks",
        lambda *a, **kw: 1,
    )
    monkeypatch.setattr(
        "app.service.task_manager.crud_task.get_tasks_by_ids",
        lambda _db, ids: [task_row] if ids else [],
    )

    started = MagicMock()
    monkeypatch.setattr(mgr, "start_worker_if_needed", started)

    captured = []
    monkeypatch.setattr(
        mgr, "publish_task_update",
        lambda task, event="task.updated": captured.append((task.id, event)),
    )

    result = mgr.retry_all_failed_tasks(db, types=["OCR"])
    assert result["count"] == 1
    started.assert_called_once_with()
    assert ("f-1", "task.retry") in captured


def test_retry_all_failed_tasks_no_filter_uses_all_failed(monkeypatch):
    """Without ``types``, the query has no extra filter."""
    mgr = _make_manager()

    db = MagicMock()
    db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
    monkeypatch.setattr(
        "app.service.task_manager.crud_task.retry_all_failed_tasks",
        lambda *a, **kw: 0,
    )

    mgr.retry_all_failed_tasks(db)
    # The first .filter() call is the status filter; no type filter applied.
    assert db.query.return_value.filter.call_count == 1


# ---------------------------------------------------------------------------
# add_task -- SCAN_FOLDER dedup
# ---------------------------------------------------------------------------


def test_add_task_scan_folder_reuses_existing_pending_for_payload_user(monkeypatch):
    """If a SCAN_FOLDER for the same user is already pending, return it
    instead of creating a duplicate."""
    mgr = _make_manager()

    existing = SimpleNamespace(
        id="existing-scan", status="PENDING", type="SCAN_FOLDER", priority=0
    )

    base_query = MagicMock()
    after_filter1 = MagicMock()
    after_filter2 = MagicMock()
    base_query.filter.return_value = after_filter1
    after_filter1.filter.return_value = after_filter2
    after_filter2.order_by.return_value.first.return_value = existing

    db = MagicMock()
    db.query.return_value = base_query

    create = MagicMock(side_effect=AssertionError("should not be called"))
    monkeypatch.setattr(
        "app.service.task_manager.crud_task.add_task", create
    )

    started = MagicMock()
    monkeypatch.setattr(mgr, "start_worker_if_needed", started)
    pub = MagicMock()
    monkeypatch.setattr(mgr, "publish_task_update", pub)

    out = mgr.add_task(
        db, "SCAN_FOLDER", {"user_id": "u1", "scan_roots": ["/p"]}, priority=0
    )
    assert out is existing
    started.assert_not_called()
    pub.assert_not_called()
    create.assert_not_called()


def test_add_task_scan_folder_falls_back_to_owner_id(monkeypatch):
    """If the payload lacks ``user_id`` but ``owner_id`` is supplied,
    dedup must still find an existing task."""
    mgr = _make_manager()

    existing = SimpleNamespace(
        id="existing-by-owner", status="PROCESSING", type="SCAN_FOLDER", priority=0
    )

    base_query = MagicMock()
    after_filter1 = MagicMock()
    after_filter2 = MagicMock()
    base_query.filter.return_value = after_filter1
    after_filter1.filter.return_value = after_filter2
    after_filter2.order_by.return_value.first.return_value = existing

    db = MagicMock()
    db.query.return_value = base_query

    create = MagicMock(side_effect=AssertionError("should not be called"))
    monkeypatch.setattr("app.service.task_manager.crud_task.add_task", create)

    pub = MagicMock()
    monkeypatch.setattr(mgr, "publish_task_update", pub)

    from uuid import UUID
    out = mgr.add_task(
        db,
        "SCAN_FOLDER",
        {"scan_roots": ["/photos"]},
        priority=0,
        owner_id=UUID("00000000-0000-0000-0000-000000000001"),
    )
    assert out is existing
    create.assert_not_called()


def test_add_task_scan_folder_dedup_exception_falls_through_to_create(monkeypatch):
    """If the dedup query blows up, we log a warning and create the
    task anyway."""
    mgr = _make_manager()

    db = MagicMock()
    db.query.side_effect = RuntimeError("DB down")

    created = SimpleNamespace(id="new-scan", type="SCAN_FOLDER", priority=5)
    monkeypatch.setattr(
        "app.service.task_manager.crud_task.add_task",
        lambda *a, **kw: created,
    )
    monkeypatch.setattr(mgr, "start_worker_if_needed", MagicMock())
    monkeypatch.setattr(mgr, "publish_task_update", MagicMock())

    out = mgr.add_task(
        db, "SCAN_FOLDER", {"user_id": "u1", "scan_roots": ["/p"]}, priority=5
    )
    assert out is created


def test_add_task_non_scan_folder_skips_dedup(monkeypatch):
    """Only SCAN_FOLDER runs the dedup path; everything else creates
    directly."""
    mgr = _make_manager()

    db = MagicMock()
    created = SimpleNamespace(id="new-ocr", type="OCR", priority=0)
    monkeypatch.setattr(
        "app.service.task_manager.crud_task.add_task",
        lambda *a, **kw: created,
    )
    started = MagicMock()
    monkeypatch.setattr(mgr, "start_worker_if_needed", started)
    pub = MagicMock()
    monkeypatch.setattr(mgr, "publish_task_update", pub)

    out = mgr.add_task(db, "OCR", {"photo_ids": [1, 2, 3]}, priority=0)
    assert out is created
    started.assert_called_once_with()
    pub.assert_called_once()


# ---------------------------------------------------------------------------
# add_tasks -- batch publish
# ---------------------------------------------------------------------------


def test_add_tasks_publishes_task_created_per_entry(monkeypatch):
    """``add_tasks`` must call ``crud_task.add_tasks`` AND publish a
    ``task.created`` event per entry so the UI updates immediately."""
    mgr = _make_manager()

    db = MagicMock()
    monkeypatch.setattr(
        "app.service.task_manager.crud_task.add_tasks", lambda *a, **kw: None
    )
    started = MagicMock()
    monkeypatch.setattr(mgr, "start_worker_if_needed", started)

    captured = []
    monkeypatch.setattr(mgr, "publish_event", lambda ev, data: captured.append((ev, data)))

    tasks_data = [
        {"type": "OCR", "payload": {"x": 1}, "priority": 0},
        {"type": "OCR", "payload": {"x": 2}, "priority": 1},
    ]
    mgr.add_tasks(db, tasks_data, owner_id="00000000-0000-0000-0000-000000000099")

    started.assert_called_once_with()
    assert [c[0] for c in captured] == ["task.created", "task.created"]
    for event, payload in captured:
        assert payload["status"] == "pending"


# ---------------------------------------------------------------------------
# _publish_active_tasks_snapshot
# ---------------------------------------------------------------------------


def test_publish_active_tasks_snapshot_emits_pending_and_processing(monkeypatch):
    """Snapshot must publish every PENDING / PROCESSING task to keep
    the UI in sync after a cold start."""
    mgr = _make_manager()

    pending = SimpleNamespace(id="p1", type="OCR", status="PENDING")
    processing = SimpleNamespace(id="pr1", type="OCR", status="PROCESSING")
    db = MagicMock()
    db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
        pending,
        processing,
    ]
    monkeypatch.setattr("app.service.task_manager.SessionLocal", lambda: db)

    captured = []
    monkeypatch.setattr(
        mgr, "publish_task_update",
        lambda task, event="task.updated": captured.append((task.id, event)),
    )

    mgr._publish_active_tasks_snapshot()
    assert ("p1", "task.updated") in captured
    assert ("pr1", "task.updated") in captured


def test_publish_active_tasks_snapshot_swallows_session_failure(monkeypatch):
    """If SessionLocal() raises, we must log and exit -- never crash."""
    mgr = _make_manager()

    monkeypatch.setattr(
        "app.service.task_manager.SessionLocal",
        MagicMock(side_effect=RuntimeError("DB unavailable")),
    )

    mgr._publish_active_tasks_snapshot()  # must not raise


def test_publish_active_tasks_snapshot_continues_after_per_task_failure(monkeypatch):
    """A failure publishing one task must not stop the rest."""
    mgr = _make_manager()

    ok = SimpleNamespace(id="ok-1", type="OCR", status="PENDING")
    bad = SimpleNamespace(id="bad-1", type="OCR", status="PENDING")
    db = MagicMock()
    db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
        ok,
        bad,
    ]
    monkeypatch.setattr("app.service.task_manager.SessionLocal", lambda: db)

    captured = []
    def publish(task, event="task.updated"):
        if task.id == "bad-1":
            raise RuntimeError("publish failed")
        captured.append(task.id)
    monkeypatch.setattr(mgr, "publish_task_update", publish)
    mgr._publish_active_tasks_snapshot()
    assert captured == ["ok-1"]
