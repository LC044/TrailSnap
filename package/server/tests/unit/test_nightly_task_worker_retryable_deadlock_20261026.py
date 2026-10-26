"""Nightly regression coverage for transient database errors in the task worker.

The 2026-10-26 E2E run failed in CI while the fixture photos were being
classified:

    psycopg2.errors.DeadlockDetected: deadlock detected
    ...
    [SQL: INSERT INTO photo_tags (...) VALUES (...)]
    File "app/service/tasks/classification.py", line 206, in _process_ai_results
        tag_id = get_tag_id(db, tag_name, photo.owner_id)

Several AI batches run in parallel, each with its own session, so they can
deadlock while inserting ``photo_tags``.  A deadlock is a transient lock cycle:
the transaction that lost is rolled back and the work can simply be retried.
Before this change the worker treated the error as terminal and the whole batch
of photos was failed for good, which aborted the E2E fixture scan with
"必需照片处理失败".

The retry classification itself lives in ``TaskWorker._is_retryable_error``.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.db.models.task import TaskStatus
from app.service import task_worker

pytestmark = [pytest.mark.smoke]


DEADLOCK = (
    "(psycopg2.errors.DeadlockDetected) deadlock detected\n"
    "DETAIL:  Process 97483 waits for AccessShareLock on tuple (0,10) of relation 385602\n"
    "[SQL: INSERT INTO photo_tags (id, tag_name, type, cover_id, owner_id, ...) VALUES (...)]"
)

SERIALIZATION = (
    "(psycopg2.errors.SerializationFailure) could not serialize access due to "
    "concurrent update"
)


def _task(identifier, attempt_count):
    """A task row with the attributes the worker publishes after a retry."""
    return SimpleNamespace(
        id=identifier, type="CLASSIFY_IMAGE", status=TaskStatus.PROCESSING, priority=10,
        total_items=1, processed_items=0, owner_id=None, created_at=None, updated_at=None,
        payload={}, attempt_count=attempt_count, next_retry_at=None, error=None,
    )

def test_a_deadlock_is_retryable():
    assert task_worker.TaskWorker._is_retryable_error(DEADLOCK) is True


def test_a_serialization_failure_is_retryable():
    assert task_worker.TaskWorker._is_retryable_error(SERIALIZATION) is True


def test_a_real_failure_is_not_retryable():
    assert task_worker.TaskWorker._is_retryable_error("AI Service error: 500: broken input") is False


def test_a_deadlock_schedules_the_task_for_a_retry():
    worker = task_worker.TaskWorker.__new__(task_worker.TaskWorker)
    worker._publish = MagicMock()
    db = MagicMock()
    task = _task("task-1", attempt_count=0)

    assert worker._schedule_retry(db, task, DEADLOCK, 3) is True
    assert task.status == TaskStatus.PENDING
    assert task.attempt_count == 1
    assert task.next_retry_at is not None
    assert "重试" in task.error


def test_a_deadlock_stops_after_the_attempt_budget():
    worker = task_worker.TaskWorker.__new__(task_worker.TaskWorker)
    worker._publish = MagicMock()
    db = MagicMock()
    task = _task("task-2", attempt_count=2)

    assert worker._schedule_retry(db, task, DEADLOCK, 3) is False
    assert task.attempt_count == 3
    assert task.status == TaskStatus.PROCESSING

