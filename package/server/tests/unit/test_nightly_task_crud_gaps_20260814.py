"""Unit tests covering 2026-08-14 nightly coverage gap scan.

Modules exercised:
* app/crud/task.py -- list_tasks (status/type/updated_since filters),
  count_dispatchable_tasks (paused vs unpaused), get_grouped_status
  (aggregation + DB-error fallback to empty list), add_task (priority
  lookup), add_tasks (empty + bulk insert), cancel_task, retry_task,
  retry_all_failed_tasks, delete_failed_tasks, delete_tasks_by_ids.
"""
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from app.db.models.task import DEFAULT_PRIORITIES

import pytest


pytestmark = [pytest.mark.smoke]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _make_task(**kw):
    base = {
        "id": uuid4(),
        "type": "PROCESS_BASIC",
        "owner_id": uuid4(),
        "payload": {},
        "status": "pending",
        "created_at": datetime.now(),
        "updated_at": datetime.now(),
        "error": None,
        "priority": 5,
    }
    base.update(kw)
    return SimpleNamespace(**base)


# ===========================================================================
# app/crud/task.py
# ===========================================================================


def test_list_tasks_no_filters_returns_query_results():
    from app.crud import task as crud_task
    rows = [_make_task() for _ in range(3)]
    db = MagicMock()
    chain = db.query.return_value
    chain.order_by.return_value = chain
    chain.limit.return_value = chain
    chain.all.return_value = rows
    out = crud_task.list_tasks(db)
    assert out == rows
    chain.filter.assert_not_called()


def test_list_tasks_with_status_and_type():
    from app.crud import task as crud_task
    rows = [_make_task(status="failed", type="OCR")]
    db = MagicMock()
    chain = db.query.return_value
    chain.order_by.return_value = chain
    chain.filter.return_value = chain
    chain.limit.return_value = chain
    chain.all.return_value = rows
    out = crud_task.list_tasks(db, status="failed", type="OCR", limit=5)
    assert out == rows
    assert chain.filter.call_count == 2


def test_list_tasks_with_iso_z_timestamp_is_parsed():
    from app.crud import task as crud_task
    db = MagicMock()
    chain = db.query.return_value
    chain.order_by.return_value = chain
    chain.filter.return_value = chain
    chain.limit.return_value = chain
    chain.all.return_value = []
    out = crud_task.list_tasks(db, updated_since="2026-01-01T00:00:00Z")
    assert out == []
    assert chain.filter.called


def test_list_tasks_with_invalid_timestamp_is_ignored():
    from app.crud import task as crud_task
    db = MagicMock()
    chain = db.query.return_value
    chain.order_by.return_value = chain
    chain.limit.return_value = chain
    chain.all.return_value = []
    out = crud_task.list_tasks(db, updated_since="not-a-real-timestamp")
    assert out == []
    chain.filter.assert_not_called()


def test_count_dispatchable_tasks_no_pause_set():
    from app.crud import task as crud_task
    db = MagicMock()
    chain = db.query.return_value
    chain.filter.return_value = chain
    chain.count.return_value = 7
    assert crud_task.count_dispatchable_tasks(db) == 7


def test_count_dispatchable_tasks_paused_types_filters_out():
    from app.crud import task as crud_task
    db = MagicMock()
    chain = db.query.return_value
    chain.filter.return_value = chain
    chain.filter.return_value.filter.return_value = chain
    chain.count.return_value = 2
    assert crud_task.count_dispatchable_tasks(db, paused_types={"PROCESS_BASIC"}) == 2


def test_get_grouped_status_returns_categories_sorted_by_priority_desc():
    from app.crud import task as crud_task
    from app.db.models.task import TaskType
    db = MagicMock()
    # Two queries; both return rows
    pending_query = MagicMock()
    pending_query.filter.return_value = pending_query
    pending_query.group_by.return_value = pending_query
    pending_query.all.return_value = [(TaskType.PROCESS_BASIC, 3)]
    failed_query = MagicMock()
    failed_query.filter.return_value = failed_query
    failed_query.group_by.return_value = failed_query
    failed_query.all.return_value = []
    db.query.side_effect = [pending_query, failed_query]

    out = crud_task.get_grouped_status(db, paused_categories={TaskType.RECOGNIZE_FACE})
    # All 9 categories surfaced
    assert len(out) == 9
    priorities = [row["priority"] for row in out]
    assert priorities == sorted(priorities, reverse=True)
    # RECOGNIZE_FACE entry should be marked 'paused'
    recog = next(r for r in out if r["category"] == TaskType.RECOGNIZE_FACE)
    assert recog["status"] == "paused"
    # PROCESS_BASIC should have its pending count from the mocked query
    pb = next(r for r in out if r["category"] == TaskType.PROCESS_BASIC)
    assert pb["pending"] == 3
    assert pb["failed"] == 0
    assert pb["description"]  # non-empty


def test_get_grouped_status_db_error_returns_empty():
    from app.crud import task as crud_task
    db = MagicMock()
    db.query.side_effect = RuntimeError("session closed")
    assert crud_task.get_grouped_status(db, paused_categories=set()) == []


def test_add_task_uses_default_priority_for_type():
    from app.crud import task as crud_task
    from app.db.models.task import TaskType
    db = MagicMock()
    owner = uuid4()
    out = crud_task.add_task(db, type=TaskType.RECOGNIZE_FACE, payload={"x": 1}, owner_id=owner)
    db.add.assert_called_once()
    db.commit.assert_called_once()
    db.refresh.assert_called_once()
    args, _ = db.add.call_args
    created = args[0]
    assert created.type == TaskType.RECOGNIZE_FACE
    assert created.priority == DEFAULT_PRIORITIES[TaskType.RECOGNIZE_FACE]
    assert out is created or out is db.refresh.return_value


def test_add_tasks_empty_input_does_nothing():
    from app.crud import task as crud_task
    db = MagicMock()
    crud_task.add_tasks(db, [])
    db.bulk_save_objects.assert_not_called()
    db.commit.assert_not_called()


def test_add_tasks_bulk_uses_default_priorities():
    from app.crud import task as crud_task
    from app.db.models.task import TaskType
    db = MagicMock()
    owner = uuid4()
    tasks_data = [
        {"type": TaskType.PROCESS_BASIC, "payload": {"i": 1}},
        {"type": TaskType.RECOGNIZE_FACE, "payload": {"i": 2}},
    ]
    crud_task.add_tasks(db, tasks_data, owner_id=owner)
    assert db.bulk_save_objects.called
    args, _ = db.bulk_save_objects.call_args
    saved = args[0]
    assert len(saved) == 2
    # First task uses the default priority from DEFAULT_PRIORITIES
    saved_first = saved[0].priority
    DEFAULT_PRIORITIES_EXPECT = DEFAULT_PRIORITIES[TaskType.PROCESS_BASIC]
    assert saved_first == DEFAULT_PRIORITIES_EXPECT
    db.commit.assert_called_once()


def test_cancel_task_sets_status_to_cancelled():
    from app.crud import task as crud_task
    from app.db.models.task import TaskStatus
    db = MagicMock()
    task = _make_task(status="pending")
    out = crud_task.cancel_task(db, task)
    assert task.status == TaskStatus.CANCELLED
    db.commit.assert_called_once()
    db.refresh.assert_called_once()


def test_retry_task_resets_error_and_status():
    from app.crud import task as crud_task
    from app.db.models.task import TaskStatus
    db = MagicMock()
    task = _make_task(status="failed", error="boom")
    out = crud_task.retry_task(db, task)
    assert task.status == TaskStatus.PENDING
    assert task.error is None
    db.commit.assert_called_once()
    db.refresh.assert_called_once()


def test_retry_all_failed_tasks_with_types_filter():
    from app.crud import task as crud_task
    from app.db.models.task import TaskType
    db = MagicMock()
    chain = db.query.return_value
    chain.filter.return_value = chain
    chain.filter.return_value.filter.return_value = chain
    chain.update.return_value = 4
    out = crud_task.retry_all_failed_tasks(db, types=[TaskType.OCR, TaskType.RECOGNIZE_TICKET])
    assert out == 4
    db.commit.assert_called_once()


def test_retry_all_failed_tasks_no_types():
    from app.crud import task as crud_task
    db = MagicMock()
    chain = db.query.return_value
    chain.filter.return_value = chain
    chain.update.return_value = 9
    out = crud_task.retry_all_failed_tasks(db)
    assert out == 9


def test_delete_failed_tasks_no_types():
    from app.crud import task as crud_task
    db = MagicMock()
    chain = db.query.return_value
    chain.filter.return_value = chain
    chain.delete.return_value = 3
    out = crud_task.delete_failed_tasks(db)
    assert out == 3
    db.commit.assert_called_once()


def test_delete_failed_tasks_with_types_filter():
    from app.crud import task as crud_task
    from app.db.models.task import TaskType
    db = MagicMock()
    chain = db.query.return_value
    chain.filter.return_value = chain
    chain.filter.return_value.filter.return_value = chain
    chain.delete.return_value = 2
    out = crud_task.delete_failed_tasks(db, types=[TaskType.OCR])
    assert out == 2


def test_delete_tasks_by_ids_passes_in_clause():
    from app.crud import task as crud_task
    db = MagicMock()
    chain = db.query.return_value
    chain.filter.return_value = chain
    chain.delete.return_value = 5
    ids = [uuid4(), uuid4()]
    out = crud_task.delete_tasks_by_ids(db, ids)
    assert out == 5


def test_default_scan_status_constant_shape():
    from app.crud.task import DEFAULT_SCAN_STATUS
    assert DEFAULT_SCAN_STATUS["running"] is False
    assert DEFAULT_SCAN_STATUS["added"] == 0
    assert DEFAULT_SCAN_STATUS["message"] == "Idle"
    assert "classified" in DEFAULT_SCAN_STATUS
