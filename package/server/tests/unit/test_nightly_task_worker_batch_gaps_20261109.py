"""Nightly watch 2026-11-09 (round 2): task worker scheduling gaps.

Targets uncovered branches in ``app/service/task_worker.py`` reported by the
2026-11-09 coverage snapshot:

* ``TaskQueueManager.get_lowest_priority`` - the ``-9999`` sentinel used when
  a category has nothing queued.
* ``TaskQueueManager.drain_queued`` - withdrawing reserved batches without
  touching persisted task state.
* ``TaskWorker.execute_batch_task_wrapper`` - the failure path (every task of
  the batch is reported as FAILED) and the adaptive-concurrency bookkeeping
  (success / overload / system pressure).

Every test exercises already-implemented behaviour; no production code changes.
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch
from uuid import uuid4

import pytest

from app.db.models.task import TaskStatus, TaskType
from app.service import task_worker
from app.service.task_worker import TaskQueueManager, TaskWorker

pytestmark = [pytest.mark.smoke]


class _FakeLimiter:
    def __init__(self, fail_on_acquire: bool = False):
        self.in_use = 0
        self.current_limit = 4
        self.fail_on_acquire = fail_on_acquire
        self.events = []

    async def acquire(self):
        if self.fail_on_acquire:
            raise RuntimeError("limiter unavailable")
        self.in_use += 1

    async def release(self):
        self.in_use = max(0, self.in_use - 1)

    async def ensure_capacity(self, floor):
        self.events.append(("ensure_capacity", floor))

    async def record_success(self):
        self.events.append(("record_success",))

    async def record_overload(self, reason, floor=1):
        self.events.append(("record_overload", reason, floor))


def _run(coro):
    return asyncio.run(coro)


# --- queue manager ----------------------------------------------------------

def test_get_lowest_priority_returns_sentinel_for_empty_queue():
    manager = TaskQueueManager()
    assert manager.get_lowest_priority("CPU") == -9999
    assert manager.get_lowest_priority("UNKNOWN") == -9999


def test_get_lowest_priority_reports_the_lowest_queued_priority():
    manager = TaskQueueManager()

    async def scenario():
        await manager.put_batch("CPU", [{"id": 1}], priority=5)
        await manager.put_batch("CPU", [{"id": 2}], priority=1)

    _run(scenario())
    assert manager.get_lowest_priority("CPU") == 1


def test_drain_queued_returns_batches_and_clears_counts():
    manager = TaskQueueManager()

    async def scenario():
        await manager.put_batch("AI", [{"id": 1}, {"id": 2}], priority=3)

    _run(scenario())
    assert manager.item_count("AI") == 2

    drained = manager.drain_queued("AI")
    assert [task["id"] for task in drained] == [1, 2]
    assert manager.item_count("AI") == 0
    assert manager.drain_queued("AI") == []


# --- batch execution wrapper ------------------------------------------------

def _worker_with_limiter(limiter):
    worker = TaskWorker()
    worker._resource_limiter = lambda key: limiter
    worker.batch_pool = None
    return worker


def test_execute_batch_task_wrapper_ignores_empty_batch():
    worker = _worker_with_limiter(_FakeLimiter())
    assert _run(worker.execute_batch_task_wrapper([], "CPU")) is None


def test_execute_batch_task_wrapper_reports_every_task_as_failed_on_error():
    limiter = _FakeLimiter()
    worker = _worker_with_limiter(limiter)
    task_id = uuid4()

    def boom(_task_infos):
        raise RuntimeError("batch exploded")

    with patch.object(TaskWorker, "_execute_batch_sync", side_effect=boom):
        _run(worker.execute_batch_task_wrapper(
            [{"id": task_id, "type": TaskType.PROCESS_BASIC, "resource_key": "cpu"}], "CPU"))

    result = worker.result_queue.get_nowait()
    assert result["task_id"] == task_id
    assert result["status"] == TaskStatus.FAILED
    assert "batch exploded" in result["error"]


def test_execute_batch_task_wrapper_publishes_results_on_success():
    limiter = _FakeLimiter()
    worker = _worker_with_limiter(limiter)
    task_id = uuid4()

    def ok(_task_infos):
        return ([{"task_id": task_id, "status": TaskStatus.COMPLETED}], "success")

    with patch.object(TaskWorker, "_execute_batch_sync", side_effect=ok):
        _run(worker.execute_batch_task_wrapper(
            [{"id": task_id, "type": TaskType.PROCESS_BASIC, "resource_key": "cpu"}], "CPU"))

    result = worker.result_queue.get_nowait()
    assert result["task_id"] == task_id
    assert result["status"] == TaskStatus.COMPLETED


def test_execute_batch_task_wrapper_records_success_when_adaptive_is_enabled():
    limiter = _FakeLimiter()
    worker = _worker_with_limiter(limiter)
    task_id = uuid4()

    def ok(_task_infos):
        return ([{"task_id": task_id, "status": TaskStatus.COMPLETED}], "success")

    with patch.object(TaskWorker, "_execute_batch_sync", side_effect=ok), \
         patch.object(task_worker.system_config.config.task, "adaptive_concurrency", True), \
         patch.object(TaskWorker, "_is_system_overloaded", return_value=False):
        _run(worker.execute_batch_task_wrapper(
            [{"id": task_id, "type": TaskType.PROCESS_BASIC, "resource_key": "cpu"}], "CPU"))

    assert ("record_success",) in limiter.events


def test_execute_batch_task_wrapper_records_overload_for_overload_outcome():
    limiter = _FakeLimiter()
    worker = _worker_with_limiter(limiter)
    task_id = uuid4()

    def overloaded(_task_infos):
        return ([{"task_id": task_id, "status": TaskStatus.FAILED}], "overload")

    with patch.object(TaskWorker, "_execute_batch_sync", side_effect=overloaded), \
         patch.object(task_worker.system_config.config.task, "adaptive_concurrency", True):
        _run(worker.execute_batch_task_wrapper(
            [{"id": task_id, "type": TaskType.PROCESS_BASIC, "resource_key": "cpu"}], "CPU"))

    assert ("record_overload", "transient_failure", 1) in limiter.events


def test_execute_batch_task_wrapper_releases_the_limiter_after_failure():
    limiter = _FakeLimiter(fail_on_acquire=True)
    worker = _worker_with_limiter(limiter)
    task_id = uuid4()

    with patch.object(TaskWorker, "_execute_batch_sync", side_effect=AssertionError("must not run")):
        _run(worker.execute_batch_task_wrapper(
            [{"id": task_id, "type": TaskType.PROCESS_BASIC, "resource_key": "cpu"}], "CPU"))

    result = worker.result_queue.get_nowait()
    assert result["status"] == TaskStatus.FAILED
    assert limiter.in_use == 0

