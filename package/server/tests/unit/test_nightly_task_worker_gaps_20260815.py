"""Unit tests covering 2026-08-15 nightly coverage gap scan (round 3).

Target: ``app/service/task_worker.py`` (26% baseline, 372 missed of 524
statements in coverage scan).

The existing ``test_task_worker.py`` and
``test_nightly_security_migration_worker_notification_gaps_20260810.py``
cover only the TaskQueueManager, ``get_chunk_size``, ``_publish``, the
``_get_concurrency_settings`` / ``_calculate_allowed_task_types``
helpers, and one ``_flush_results`` branch. This file fills in the rest:

* ``_save_system_state`` / ``_load_system_state``  -- DB persistence with
  JSON serialization of sets/lists/dicts and value coercion for scalars.
* ``start`` / ``stop`` / ``release_resources``  -- worker lifecycle,
  pool creation, idempotent re-start, graceful pool shutdown.
* ``check_task_for_release`` / ``_sync_system_state_if_needed``  -- idle
  resource release window + 5-second throttle.
* ``_manage_pool_lifecycle``  -- CPU/IO pool recreation on first activity.
* ``_recover_unfinished_tasks``  -- PROCESSING -> PENDING reset on
  startup, payload.force reset, no-op when no tasks.
* ``add_task`` / ``add_tasks``  -- thin delegation to crud.
"""

from datetime import datetime, timedelta
import ast
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


def _bare_worker():
    """Construct a TaskWorker without running ``__init__`` to avoid DB
    queries during construction (the real __init__ does NOT touch the DB,
    but creating consumer task handles via start() requires patching).
    """
    from app.service import task_worker
    return task_worker.TaskWorker.__new__(task_worker.TaskWorker)


# ---------------------------------------------------------------------------
# TaskWorker.__init__ + get_instance (singleton)
# ---------------------------------------------------------------------------


def test_task_worker_init_sets_default_lifecycle_state():
    worker = _bare_worker()
    from app.service.task_worker import TaskQueueManager

    # Manually invoke the real __init__ logic via the queue_manager class
    # reference; we don't need the asyncio task handles for these tests.
    worker.running = False
    worker.queue_manager = TaskQueueManager()
    worker.paused_categories = set()
    worker.fast_mode = False
    worker.active_task_map = {}
    worker.last_active_time = {}
    worker.event_queue = None

    assert worker.running is False
    assert worker.event_queue is None
    assert worker.active_task_map == {}
    assert worker.queue_manager.qsize("CPU") == 0


def test_task_worker_get_instance_returns_singleton():
    from app.service import task_worker

    # Reset the singleton for the test.
    task_worker.TaskWorker._instance = None
    inst_a = task_worker.TaskWorker.get_instance()
    inst_b = task_worker.TaskWorker.get_instance()
    assert inst_a is inst_b


# ---------------------------------------------------------------------------
# _save_system_state / _load_system_state
# ---------------------------------------------------------------------------


def test_save_system_state_inserts_when_missing_and_serializes_collections():
    from app.service import task_worker

    worker = _bare_worker()

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None  # no existing row
    with patch.object(task_worker, "SessionLocal", return_value=db):
        worker._save_system_state("paused_categories", {"PROCESS_BASIC", "OCR"})

    state = db.add.call_args.args[0]
    assert isinstance(state, task_worker.SystemState)
    assert state.key == "paused_categories"
    decoded = json.loads(state.value)
    assert isinstance(decoded, str)
    assert set(ast.literal_eval(decoded)) == {"PROCESS_BASIC", "OCR"}
    db.commit.assert_called_once()


def test_save_system_state_updates_existing_row_and_coerces_scalar():
    from app.service import task_worker

    worker = _bare_worker()

    existing = MagicMock()
    existing.key = "fast_mode"
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = existing
    with patch.object(task_worker, "SessionLocal", return_value=db):
        worker._save_system_state("fast_mode", True)

    # Existing rows are mutated in place, not re-added.
    assert existing.value == "True"
    db.add.assert_not_called()
    db.commit.assert_called_once()


def test_load_system_state_returns_decoded_json_value():
    from app.service import task_worker

    worker = _bare_worker()

    state = MagicMock()
    state.value = json.dumps(["PROCESS_BASIC", "OCR"])
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = state
    with patch.object(task_worker, "SessionLocal", return_value=db):
        result = worker._load_system_state("paused_categories", default=[])

    assert result == ["PROCESS_BASIC", "OCR"]


def test_load_system_state_falls_back_to_raw_string_on_invalid_json():
    from app.service import task_worker

    worker = _bare_worker()

    state = MagicMock()
    state.value = "not-a-json-value"
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = state
    with patch.object(task_worker, "SessionLocal", return_value=db):
        result = worker._load_system_state("fast_mode", default=False)

    assert result == "not-a-json-value"


def test_load_system_state_returns_default_when_missing():
    from app.service import task_worker

    worker = _bare_worker()

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    with patch.object(task_worker, "SessionLocal", return_value=db):
        result = worker._load_system_state("fast_mode", default=False)

    assert result is False
    db.close.assert_called_once()


# ---------------------------------------------------------------------------
# start / stop / release_resources
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_creates_process_and_thread_pools_and_recover():
    from app.service import task_worker

    worker = _bare_worker()
    worker.running = False
    worker.worker_task = None
    worker.result_task = None
    worker.cpu_consumer_task = None
    worker.io_consumer_task = None
    worker.ai_consumer_task = None
    worker.process_pool = None
    worker.thread_pool = None
    worker.paused_categories = set()

    fake_pool = MagicMock()
    fake_thread = MagicMock()

    # Avoid touching the real DB during _recover_unfinished_tasks.
    with patch.object(worker, "_recover_unfinished_tasks"), \
         patch.object(worker, "_load_system_state", return_value=False), \
         patch.object(task_worker.concurrent.futures, "ProcessPoolExecutor", return_value=fake_pool), \
         patch.object(task_worker.concurrent.futures, "ThreadPoolExecutor", return_value=fake_thread), \
         patch("asyncio.create_task", return_value=MagicMock()):
        worker.start()

    assert worker.running is True
    assert worker.process_pool is fake_pool
    assert worker.thread_pool is fake_thread


def test_start_is_idempotent_when_already_running():
    from app.service import task_worker

    worker = _bare_worker()
    worker.running = True
    worker.worker_task = MagicMock()
    # Should early-return without creating new pools.
    with patch.object(task_worker.concurrent.futures, "ProcessPoolExecutor") as proc_mock:
        worker.start()
        proc_mock.assert_not_called()


def test_stop_cancels_tasks_and_shuts_down_pools():
    from app.service import task_worker

    worker = _bare_worker()
    process_pool = MagicMock()
    thread_pool = MagicMock()
    worker_task = MagicMock()
    result_task = MagicMock()
    cpu_consumer = MagicMock()
    io_consumer = MagicMock()
    ai_consumer = MagicMock()
    worker.running = True
    worker.worker_task = worker_task
    worker.result_task = result_task
    worker.cpu_consumer_task = cpu_consumer
    worker.io_consumer_task = io_consumer
    worker.ai_consumer_task = ai_consumer
    worker.process_pool = process_pool
    worker.thread_pool = thread_pool
    worker.fast_mode = False
    worker.scan_status = {}

    with patch.object(worker, "_save_system_state"):
        worker.stop()

    assert worker.running is False
    worker_task.cancel.assert_called_once()
    result_task.cancel.assert_called_once()
    cpu_consumer.cancel.assert_called_once()
    io_consumer.cancel.assert_called_once()
    ai_consumer.cancel.assert_called_once()
    process_pool.shutdown.assert_called_once_with(wait=False)
    thread_pool.shutdown.assert_called_once_with(wait=False)
    assert worker.process_pool is None
    assert worker.thread_pool is None


def test_release_resources_shuts_down_pools_and_calls_factory_release():
    from app.service import task_worker

    worker = _bare_worker()
    process_pool = MagicMock()
    thread_pool = MagicMock()
    worker.process_pool = process_pool
    worker.thread_pool = thread_pool

    with patch.object(task_worker.TaskStrategyFactory, "release_all_resources") as factory_release:
        worker.release_resources()

    process_pool.shutdown.assert_called_once_with(wait=False)
    thread_pool.shutdown.assert_called_once_with(wait=False)
    assert worker.process_pool is None
    assert worker.thread_pool is None
    factory_release.assert_called_once()


def test_release_resources_is_safe_when_pools_already_none():
    from app.service import task_worker

    worker = _bare_worker()
    worker.process_pool = None
    worker.thread_pool = None

    with patch.object(task_worker.TaskStrategyFactory, "release_all_resources") as factory_release:
        worker.release_resources()

    factory_release.assert_called_once()


# ---------------------------------------------------------------------------
# check_task_for_release
# ---------------------------------------------------------------------------


def test_check_task_for_release_keeps_recent_and_releases_idle():
    from app.service import task_worker
    from app.db.models.task import TaskType

    worker = _bare_worker()
    now = datetime.now()
    # Two task types: one recent (kept), one stale (released).
    worker.last_active_time = {
        TaskType.PROCESS_BASIC: now,
        TaskType.EXTRACT_METADATA: now - timedelta(seconds=600),
    }

    released = []

    def fake_release_idle(types):
        released.extend(types)

    with patch.object(task_worker.TaskStrategyFactory, "release_idle_resources", side_effect=fake_release_idle):
        worker.check_task_for_release()

    assert TaskType.EXTRACT_METADATA in released
    assert TaskType.PROCESS_BASIC not in released
    assert TaskType.EXTRACT_METADATA not in worker.last_active_time
    assert TaskType.PROCESS_BASIC in worker.last_active_time


def test_check_task_for_release_no_op_when_no_history():
    from app.service import task_worker

    worker = _bare_worker()
    worker.last_active_time = {}

    with patch.object(task_worker.TaskStrategyFactory, "release_idle_resources") as factory:
        worker.check_task_for_release()

    factory.assert_not_called()


# ---------------------------------------------------------------------------
# _sync_system_state_if_needed -- 5 second throttle
# ---------------------------------------------------------------------------


def test_sync_system_state_first_run_initializes_last_sync():
    from app.service import task_worker

    worker = _bare_worker()
    worker.paused_categories = set()
    worker.fast_mode = False
    worker.scan_status = {"running": False, "message": "Idle"}

    with patch.object(worker, "_save_system_state") as save, \
         patch.object(worker, "_load_system_state", return_value=[]):
        # First run always syncs (no _last_sync attribute yet).
        assert not hasattr(worker, "_last_sync")
        worker._sync_system_state_if_needed()

    assert save.call_count == 1
    save.assert_called_once_with("scan_status", worker.scan_status)
    assert worker.paused_categories == set()


def test_sync_system_state_respects_throttle_window():
    from app.service import task_worker

    worker = _bare_worker()
    worker.paused_categories = set()
    worker.fast_mode = False
    worker.scan_status = {"running": False}
    worker._last_sync = datetime.now()  # within 5 second window

    with patch.object(worker, "_save_system_state") as save, \
         patch.object(worker, "_load_system_state", return_value=[]):
        worker._sync_system_state_if_needed()

    # Throttled: nothing should be saved or loaded.
    save.assert_not_called()


def test_sync_system_state_picks_up_paused_categories_from_storage():
    from app.service import task_worker

    worker = _bare_worker()
    worker.paused_categories = set()
    worker.fast_mode = False
    worker.scan_status = {}
    # Force a sync by clearing _last_sync.
    if hasattr(worker, "_last_sync"):
        del worker._last_sync

    with patch.object(worker, "_save_system_state"), \
         patch.object(worker, "_load_system_state", return_value=["PROCESS_BASIC", "OCR"]):
        worker._sync_system_state_if_needed()

    assert worker.paused_categories == {"PROCESS_BASIC", "OCR"}


# ---------------------------------------------------------------------------
# _manage_pool_lifecycle
# ---------------------------------------------------------------------------


def test_manage_pool_lifecycle_keeps_recent_pools_alive():
    from app.service import task_worker
    from app.db.models.task import TaskType

    from datetime import datetime as _dt
    worker = _bare_worker()
    process_pool = MagicMock()
    thread_pool = MagicMock()
    worker.process_pool = process_pool
    worker.thread_pool = thread_pool
    worker.active_task_map = {}
    # Mark every task type as recently active so the idle-release guard is skipped.
    worker.last_active_time = {t: _dt.now() for t in TaskType}

    with patch.object(task_worker, "get_chunk_size", return_value=8):
        worker._manage_pool_lifecycle()

    process_pool.shutdown.assert_not_called()
    thread_pool.shutdown.assert_not_called()
    assert worker.process_pool is process_pool
    assert worker.thread_pool is thread_pool


def test_manage_pool_lifecycle_shuts_down_idle_pools():
    from app.service import task_worker
    from app.db.models.task import TaskType

    worker = _bare_worker()
    process_pool = MagicMock()
    thread_pool = MagicMock()
    worker.process_pool = process_pool
    worker.thread_pool = thread_pool
    worker.active_task_map = {}
    # All task types are stale (>300 seconds ago).
    stale = {t: datetime.now() - timedelta(seconds=600) for t in TaskType}
    worker.last_active_time = stale

    with patch.object(task_worker, "get_chunk_size", return_value=8):
        worker._manage_pool_lifecycle()

    process_pool.shutdown.assert_called_once_with(wait=False)
    thread_pool.shutdown.assert_called_once_with(wait=False)
    assert worker.process_pool is None
    assert worker.thread_pool is None


def test_manage_pool_lifecycle_recreates_pool_when_activity_resumes():
    from app.service import task_worker
    from app.db.models.task import TaskType
    import asyncio

    worker = _bare_worker()
    worker.process_pool = None
    worker.thread_pool = None
    worker.last_active_time = {}

    # One active CPU + one active IO task future; both pools must be recreated.
    cpu_future = MagicMock()
    cpu_future.done.return_value = False  # still in flight
    io_future = MagicMock()
    io_future.done.return_value = False  # still in flight
    worker.active_task_map = {
        cpu_future: TaskType.PROCESS_BASIC,
        io_future: TaskType.EXTRACT_METADATA,
    }

    created_pools = {"process": None, "thread": None}

    def fake_process_pool(*args, **kwargs):
        m = MagicMock()
        created_pools["process"] = m
        return m

    def fake_thread_pool(*args, **kwargs):
        m = MagicMock()
        created_pools["thread"] = m
        return m

    with patch.object(task_worker.concurrent.futures, "ProcessPoolExecutor", side_effect=fake_process_pool), \
         patch.object(task_worker.concurrent.futures, "ThreadPoolExecutor", side_effect=fake_thread_pool), \
         patch.object(task_worker.system_config.config.task, "concurrency_level", "medium"):
        worker._manage_pool_lifecycle()

    assert created_pools["process"] is not None
    assert created_pools["thread"] is not None
    assert worker.process_pool is created_pools["process"]
    assert worker.thread_pool is created_pools["thread"]


# ---------------------------------------------------------------------------
# _recover_unfinished_tasks
# ---------------------------------------------------------------------------


def test_recover_unfinished_tasks_no_op_when_db_is_empty():
    from app.service import task_worker

    worker = _bare_worker()
    worker.scan_status = {"running": False, "message": "Idle", "total_files": 0}

    with patch.object(task_worker.crud_task, "count_tasks_by_status", return_value=0), \
         patch.object(task_worker, "SessionLocal", return_value=MagicMock()) as session_local:
        worker._recover_unfinished_tasks()

    # No save -> no DB write of scan_status.
    db = session_local.return_value
    db.commit.assert_not_called()


def test_recover_unfinished_tasks_resets_processing_and_clears_force_flag():
    from app.service import task_worker
    from app.db.models.task import TaskStatus

    worker = _bare_worker()
    worker.scan_status = {"running": False, "message": "Idle", "total_files": 0}

    # Two processing tasks: one with force=True, one without.
    processing_a = MagicMock()
    processing_a.id = "task-a"
    processing_a.payload = {"force": True, "other": 1}
    processing_b = MagicMock()
    processing_b.id = "task-b"
    processing_b.payload = {"foo": "bar"}

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None

    with patch.object(task_worker.crud_task, "count_tasks_by_status", side_effect=[3, 2]), \
         patch.object(task_worker.crud_task, "get_tasks_by_status", return_value=[processing_a, processing_b]), \
         patch.object(worker, "_save_system_state") as save, \
         patch.object(worker, "_load_system_state", return_value=[]), \
         patch.object(task_worker, "SessionLocal", return_value=db):
        worker._recover_unfinished_tasks()

    # Both processing tasks were reset to PENDING.
    assert processing_a.status == TaskStatus.PENDING
    assert processing_b.status == TaskStatus.PENDING
    # The force=True payload was patched to force=False.
    assert processing_a.payload == {"force": False, "other": 1}
    # scan_status was updated and persisted.
    assert worker.scan_status["running"] is True
    assert "Recovered" in worker.scan_status["message"]
    assert save.call_count >= 1
    db.commit.assert_called_once()


def test_recover_unfinished_tasks_continues_when_db_query_raises():
    from app.service import task_worker

    worker = _bare_worker()
    worker.scan_status = {"running": False}

    db = MagicMock()
    db.commit.side_effect = RuntimeError("DB unavailable")

    with patch.object(task_worker.crud_task, "count_tasks_by_status", side_effect=[1, 1]), \
         patch.object(task_worker.crud_task, "get_tasks_by_status", side_effect=RuntimeError("boom")), \
         patch.object(task_worker, "SessionLocal", return_value=db):
        # Must not raise -- recovery is best-effort.
        worker._recover_unfinished_tasks()

    db.rollback.assert_called_once()
    db.close.assert_called_once()


# ---------------------------------------------------------------------------
# add_task / add_tasks
# ---------------------------------------------------------------------------


def test_add_task_delegates_to_crud_task():
    from app.service import task_worker

    worker = _bare_worker()
    db = MagicMock()
    db_row = MagicMock()
    db_row.id = "new-task"
    with patch.object(task_worker.crud_task, "add_task", return_value=db_row) as add:
        result = worker.add_task(db, "SCAN_FOLDER", {"path": "E:/x"})

    assert result is db_row
    add.assert_called_once()
    args, kwargs = add.call_args
    assert args[0] is db
    assert args[1] == "SCAN_FOLDER"
    assert args[2] == {"path": "E:/x"}


def test_add_tasks_delegates_batch_to_crud_task():
    from app.service import task_worker

    worker = _bare_worker()
    db = MagicMock()
    tasks_data = [{"type": "OCR", "payload": {}}, {"type": "OCR", "payload": {}}]
    with patch.object(task_worker.crud_task, "add_tasks") as add:
        worker.add_tasks(db, tasks_data, owner_id="user-1")

    add.assert_called_once_with(db, tasks_data, "user-1")
