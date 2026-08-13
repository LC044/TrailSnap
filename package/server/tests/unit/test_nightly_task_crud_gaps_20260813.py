"""Nightly watch gap coverage for ``app/crud/task.py``.

Targets every public function in the module. Earlier coverage scan showed
22.5% line coverage (79 missed lines) because the only callers live in
routers which the unit suite does not exercise. These tests use
:class:`unittest.mock.MagicMock` so we can validate the SQLAlchemy chain
(filter / order_by / limit) without touching Postgres.
"""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.crud import task as task_crud
from app.db.models.task import (
    CATEGORY_DESCRIPTION_MAP,
    CATEGORY_NAME_MAP,
    DEFAULT_PRIORITIES,
    Task,
    TaskStatus,
    TaskType,
)


pytestmark = [pytest.mark.smoke, pytest.mark.module_task]


# ---------------------------------------------------------------------------
# list_tasks
# ---------------------------------------------------------------------------

def test_list_tasks_orders_by_created_at_desc_and_applies_limit():
    db = MagicMock()
    db.query.return_value.order_by.return_value.limit.return_value.all.return_value = [
        SimpleNamespace(id=uuid4())
    ]

    out = task_crud.list_tasks(db, limit=5)

    assert len(out) == 1
    db.query.assert_called_once_with(Task)
    db.query.return_value.order_by.return_value.limit.assert_called_once_with(5)


def test_list_tasks_filters_by_status_and_type():
    db = MagicMock()
    chain = db.query.return_value.order_by.return_value

    task_crud.list_tasks(
        db, status=TaskStatus.PENDING.value, type=TaskType.OCR.value, limit=10
    )

    # First .filter() applied on the order_by chain; second on the filter return_value.
    assert chain.filter.call_count == 1
    assert chain.filter.return_value.filter.call_count == 1
    chain.filter.return_value.filter.return_value.limit.assert_called_once_with(10)


def test_list_tasks_filters_by_updated_since_with_z_suffix():
    db = MagicMock()
    chain = db.query.return_value.order_by.return_value

    task_crud.list_tasks(db, updated_since="2026-08-13T00:00:00Z", limit=20)

    # Single .filter() applied, then .limit() chained on its return value.
    assert chain.filter.call_count == 1
    chain.filter.return_value.limit.assert_called_once_with(20)


def test_list_tasks_silently_skips_unparseable_updated_since():
    db = MagicMock()
    chain = db.query.return_value.order_by.return_value

    task_crud.list_tasks(db, updated_since="not-a-date", limit=20)

    # Unparseable timestamp is silently ignored - no filter, limit called on order_by chain.
    assert chain.filter.call_count == 0
    chain.limit.assert_called_once_with(20)


# ---------------------------------------------------------------------------
# get_task / get_tasks_by_ids / get_task_by_id_and_owner
# ---------------------------------------------------------------------------

def test_get_task_queries_by_id():
    db = MagicMock()
    expected = SimpleNamespace(id=uuid4())
    db.query.return_value.filter.return_value.first.return_value = expected

    out = task_crud.get_task(db, uuid4())

    assert out is expected
    db.query.assert_called_once_with(Task)


def test_get_tasks_by_ids_filters_with_in():
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = ["x", "y"]

    out = task_crud.get_tasks_by_ids(db, [uuid4(), uuid4()])

    assert out == ["x", "y"]
    db.query.return_value.filter.assert_called_once()


def test_get_task_by_id_and_owner_returns_none_when_missing():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None

    assert task_crud.get_task_by_id_and_owner(db, uuid4(), uuid4()) is None


# ---------------------------------------------------------------------------
# count_tasks_by_status / count_dispatchable_tasks
# ---------------------------------------------------------------------------

def test_count_tasks_by_status_filters_and_counts():
    db = MagicMock()
    db.query.return_value.filter.return_value.count.return_value = 7

    assert task_crud.count_tasks_by_status(db, TaskStatus.FAILED.value) == 7


def test_count_dispatchable_tasks_counts_pending_and_processing_without_paused():
    db = MagicMock()
    chain = db.query.return_value.filter.return_value
    chain.count.return_value = 12

    assert task_crud.count_dispatchable_tasks(db) == 12
    assert chain.filter.call_count == 0


def test_count_dispatchable_tasks_filters_out_paused_types():
    db = MagicMock()
    chain = db.query.return_value.filter.return_value
    chain.filter.return_value.count.return_value = 3

    paused = {TaskType.OCR.value, TaskType.CLASSIFY_IMAGE.value}
    out = task_crud.count_dispatchable_tasks(db, paused_types=paused)

    assert out == 3
    assert chain.filter.call_count == 1


# ---------------------------------------------------------------------------
# get_tasks_by_status / delete_tasks_by_ids / delete_task
# ---------------------------------------------------------------------------

def test_get_tasks_by_status_returns_all():
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [SimpleNamespace()]

    out = task_crud.get_tasks_by_status(db, TaskStatus.PENDING.value)

    assert len(out) == 1


def test_delete_tasks_by_ids_returns_row_count():
    db = MagicMock()
    db.query.return_value.filter.return_value.delete.return_value = 4

    assert task_crud.delete_tasks_by_ids(db, [uuid4(), uuid4()]) == 4


def test_delete_task_commits_after_delete():
    db = MagicMock()
    fake = SimpleNamespace(id=uuid4())

    task_crud.delete_task(db, fake)

    db.delete.assert_called_once_with(fake)
    db.commit.assert_called_once()


# ---------------------------------------------------------------------------
# get_latest_task_by_type_and_owner
# ---------------------------------------------------------------------------

def test_get_latest_task_by_type_and_owner_returns_first_desc():
    db = MagicMock()
    db.query.return_value.filter.return_value.order_by.return_value.first.return_value = (
        SimpleNamespace(id=uuid4())
    )

    out = task_crud.get_latest_task_by_type_and_owner(
        db, TaskType.OCR.value, uuid4(), [TaskStatus.PENDING.value]
    )

    assert out is not None
    db.query.return_value.filter.return_value.order_by.assert_called_once()


# ---------------------------------------------------------------------------
# get_grouped_status - exercise pending/failed merge, paused flag, sort, exception
# ---------------------------------------------------------------------------

def _build_grouped_status_db(pending_counts=None, failed_counts=None, raise_inside=False):
    db = MagicMock()
    pending_counts = pending_counts or {}
    failed_counts = failed_counts or {}
    pending_rows = [(t, c) for t, c in pending_counts.items()]
    failed_rows = [(t, c) for t, c in failed_counts.items()]
    if raise_inside:
        db.query.return_value.filter.return_value.group_by.return_value.all.side_effect = (
            RuntimeError("session closed")
        )
    else:
        db.query.return_value.filter.return_value.group_by.return_value.all.side_effect = (
            [pending_rows, failed_rows]
        )
    return db


def test_get_grouped_status_merges_pending_and_failed_counts():
    db = _build_grouped_status_db(
        pending_counts={TaskType.OCR.value: 2, TaskType.CLASSIFY_IMAGE.value: 5},
        failed_counts={TaskType.OCR.value: 1},
    )

    stats = task_crud.get_grouped_status(db, paused_categories=set())

    assert len(stats) >= 1
    by_category = {row["category"]: row for row in stats}
    ocr = by_category[TaskType.OCR.value]
    assert ocr["pending"] == 2
    assert ocr["failed"] == 1
    assert ocr["status"] == "active"


def test_get_grouped_status_marks_paused_categories():
    db = _build_grouped_status_db(pending_counts={TaskType.OCR.value: 4})

    stats = task_crud.get_grouped_status(db, paused_categories={TaskType.OCR.value})

    by_category = {row["category"]: row for row in stats}
    assert by_category[TaskType.OCR.value]["status"] == "paused"


def test_get_grouped_status_sorts_by_priority_desc():
    db = _build_grouped_status_db(
        pending_counts={
            TaskType.OCR.value: 1,
            TaskType.RECOGNIZE_FACE.value: 1,
        }
    )

    stats = task_crud.get_grouped_status(db, paused_categories=set())

    priorities = [row["priority"] for row in stats]
    assert priorities == sorted(priorities, reverse=True)


def test_get_grouped_status_returns_empty_on_session_error():
    db = _build_grouped_status_db(raise_inside=True)

    assert task_crud.get_grouped_status(db, paused_categories=set()) == []


def test_get_grouped_status_uses_description_and_name_maps():
    db = _build_grouped_status_db()

    stats = task_crud.get_grouped_status(db, paused_categories=set())

    sample = next(r for r in stats if r["category"] == TaskType.OCR.value)
    assert sample["task_name"] == CATEGORY_NAME_MAP[TaskType.OCR.value]
    assert sample["description"] == CATEGORY_DESCRIPTION_MAP[TaskType.OCR.value]


# ---------------------------------------------------------------------------
# add_task / add_tasks
# ---------------------------------------------------------------------------

def test_add_task_resolves_priority_from_default_map():
    db = MagicMock()
    db.refresh.return_value = None

    task = task_crud.add_task(db, TaskType.OCR.value, {"file_id": "f"})


    assert task.priority == DEFAULT_PRIORITIES[TaskType.OCR.value]
    assert task.status == TaskStatus.PENDING
    db.add.assert_called_once()
    db.commit.assert_called_once()


def test_add_task_falls_back_to_zero_for_unknown_type():
    db = MagicMock()
    db.refresh.return_value = None

    task = task_crud.add_task(db, "TOTALLY_UNKNOWN", {})

    assert task.priority == 0


def test_add_tasks_short_circuits_on_empty_list():
    db = MagicMock()

    task_crud.add_tasks(db, [], owner_id=uuid4())

    db.bulk_save_objects.assert_not_called()
    db.commit.assert_not_called()


def test_add_tasks_bulk_persists_with_owner_id_fallback():
    db = MagicMock()
    owner_id = uuid4()

    task_crud.add_tasks(
        db,
        [
            {"type": TaskType.OCR.value, "payload": {"x": 1}},
            {"type": TaskType.CLASSIFY_IMAGE.value, "payload": {"x": 2}, "owner_id": uuid4()},
        ],
        owner_id=owner_id,
    )

    db.bulk_save_objects.assert_called_once()
    saved_objects = db.bulk_save_objects.call_args.args[0]
    assert len(saved_objects) == 2
    assert saved_objects[0].owner_id == owner_id
    assert saved_objects[1].owner_id != owner_id
    db.commit.assert_called_once()


# ---------------------------------------------------------------------------
# cancel_task / retry_task
# ---------------------------------------------------------------------------

def test_cancel_task_sets_status_and_commits():
    db = MagicMock()
    db.refresh.return_value = None
    task = SimpleNamespace(status=TaskStatus.PENDING)

    out = task_crud.cancel_task(db, task)

    assert out is task
    assert task.status == TaskStatus.CANCELLED
    db.commit.assert_called_once()


def test_retry_task_clears_error_and_resets_to_pending():
    db = MagicMock()
    db.refresh.return_value = None
    task = SimpleNamespace(status=TaskStatus.FAILED, error="boom", updated_at=None)

    task_crud.retry_task(db, task)

    assert task.status == TaskStatus.PENDING
    assert task.error is None
    assert isinstance(task.updated_at, datetime)
    db.commit.assert_called_once()


# ---------------------------------------------------------------------------
# retry_all_failed_tasks / delete_failed_tasks
# ---------------------------------------------------------------------------

def test_retry_all_failed_tasks_resets_all_when_no_types_given():
    db = MagicMock()
    chain = db.query.return_value.filter.return_value
    chain.update.return_value = 9

    out = task_crud.retry_all_failed_tasks(db)

    assert out == 9
    chain.update.assert_called_once()
    db.commit.assert_called_once()


def test_retry_all_failed_tasks_filters_by_types_when_provided():
    db = MagicMock()
    chain = db.query.return_value.filter.return_value
    chain.filter.return_value.update.return_value = 2

    out = task_crud.retry_all_failed_tasks(
        db, types=[TaskType.OCR.value, TaskType.CLASSIFY_IMAGE.value]
    )

    assert out == 2
    chain.filter.assert_called_once()


def test_delete_failed_tasks_returns_count_without_types():
    db = MagicMock()
    chain = db.query.return_value.filter.return_value
    chain.delete.return_value = 11

    assert task_crud.delete_failed_tasks(db) == 11
    db.commit.assert_called_once()


def test_delete_failed_tasks_filters_by_types_when_provided():
    db = MagicMock()
    chain = db.query.return_value.filter.return_value
    chain.filter.return_value.delete.return_value = 4

    assert task_crud.delete_failed_tasks(db, types=[TaskType.OCR.value]) == 4
    chain.filter.assert_called_once()
