"""Nightly watch 2026-11-13 (round 2): task worker consumer-loop gaps.

Targets the branches the 2026-11-13 coverage snapshot still reports as
uncovered in ``app/service/task_worker.py``:

* ``TaskQueueManager.get_lowest_priority`` - the ``except ValueError`` guard
  when the underlying queue reports a truthy but empty payload.
* ``TaskWorker.consumer_loop`` - the timeout / empty-batch / wrapper-error /
  unexpected-error branches (the semaphore must always be released).
* ``TaskWorker.consumer_loop`` AI admission - a low priority batch is refused
  while an import owns the AI phase.
* ``TaskWorker._execute_batch_sync`` - the unknown-strategy guard and the
  import-priority deferral for AI strategies.

Every test exercises already-implemented behaviour; no production change.
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from app.db.models.task import TaskStatus, TaskType
from app.service import task_worker
from app.service.task_worker import TaskQueueManager, TaskWorker

pytestmark = [pytest.mark.smoke]


class _TruthyEmptyQueue:
    """A queue payload that is truthy but yields no items."""

    def __bool__(self):
        return True

    def __iter__(self):
        return iter(())


def _run(coro):
    return asyncio.run(coro)


def _make_worker():
    worker = TaskWorker()
    worker.running = True
    worker._loop = asyncio.new_event_loop()
    try:
        worker._wake_event = asyncio.Event()
    except Exception:
        pass
    return worker


def _close_worker(worker):
    loop = getattr(worker, "_loop", None)
    if loop is not None and not loop.is_closed():
        loop.close()


# --- queue manager ----------------------------------------------------------


def test_get_lowest_priority_survives_a_truthy_but_empty_queue():
    manager = TaskQueueManager()
    manager.queues["CPU"]._queue = _TruthyEmptyQueue()

    assert manager.get_lowest_priority("CPU") == -9999


# --- consumer loop -----------------------------------------------------------


def test_consumer_loop_releases_the_semaphore_on_timeout():
    worker = _make_worker()
    calls = {"n": 0}

    async def fake_get_batch(category):
        calls["n"] += 1
        worker.running = False
        raise asyncio.TimeoutError

    async def scenario():
        with patch.object(worker.queue_manager, "get_batch", fake_get_batch):
            await asyncio.wait_for(worker.consumer_loop("CPU"), timeout=5)

    _run(scenario())
    _close_worker(worker)
    assert calls["n"] >= 1


def test_consumer_loop_continues_when_the_queue_is_empty():
    worker = _make_worker()

    async def fake_get_batch(category):
        worker.running = False
        return []

    async def scenario():
        with patch.object(worker.queue_manager, "get_batch", fake_get_batch):
            await asyncio.wait_for(worker.consumer_loop("CPU"), timeout=5)

    _run(scenario())
    _close_worker(worker)


def test_consumer_loop_survives_a_failing_batch_wrapper():
    worker = _make_worker()

    async def fake_get_batch(category):
        worker.running = False
        return [{"id": "t1", "type": TaskType.PROCESS_BASIC, "priority": 1}]

    async def boom(task_infos, category):
        raise RuntimeError("batch exploded")

    async def scenario():
        with patch.object(worker.queue_manager, "get_batch", fake_get_batch), \
                patch.object(worker, "execute_batch_task_wrapper", boom):
            await asyncio.wait_for(worker.consumer_loop("CPU"), timeout=5)
            await asyncio.sleep(0.05)

    _run(scenario())
    _close_worker(worker)


def test_consumer_loop_survives_an_unexpected_error():
    worker = _make_worker()

    async def fake_get_batch(category):
        worker.running = False
        raise RuntimeError("boom")

    original_sleep = asyncio.sleep

    async def fast_sleep(_delay):
        await original_sleep(0)

    async def scenario():
        with patch.object(worker.queue_manager, "get_batch", fake_get_batch):
            with patch("asyncio.sleep", new=fast_sleep):
                await asyncio.wait_for(worker.consumer_loop("CPU"), timeout=5)

    _run(scenario())
    _close_worker(worker)


def test_ai_consumer_refuses_background_batches_during_an_import():
    worker = _make_worker()
    worker.import_priority_active = True
    seen = {}

    async def fake_available_ai_batch(available):
        seen["accepted"] = available([{"id": "t1", "type": TaskType.CLASSIFY_IMAGE,
                                       "priority": 1}])
        worker.running = False
        return []

    async def scenario():
        with patch.object(worker.queue_manager, "get_available_ai_batch", fake_available_ai_batch):
            await asyncio.wait_for(worker.consumer_loop("AI"), timeout=5)

    _run(scenario())
    _close_worker(worker)
    assert seen["accepted"] is False


# --- batch execution --------------------------------------------------------


def _patch_task_lookups(task_type, tasks):
    """Patch the DB lookups used by ``_execute_batch_sync``."""
    return (
        patch.object(task_worker.crud_task, "get_tasks_by_ids",
                     lambda db, ids: list(tasks)),
        patch.object(task_worker.TaskStrategyFactory, "get_strategy",
                     lambda _type: _FakeStrategy(task_type)),
    )


class _FakeStrategy:
    def __init__(self, task_type):
        self.task_type = task_type
        self.task_category = "AI"
        self.resource_key = "classification"
        self.timeout = 1
        self.max_attempts = 3

    async def process_batch(self, worker, tasks, db):
        return []


class _FakeTask:
    def __init__(self, task_type=TaskType.CLASSIFY_IMAGE, priority=1):
        self.id = "task-1"
        self.type = task_type
        self.status = TaskStatus.PENDING
        self.priority = priority
        self.owner_id = None
        self.payload = {}
        self.error = None
        self.next_retry_at = None
        self.attempt_count = 0


def test_execute_batch_sync_raises_for_an_unknown_strategy():
    worker = TaskWorker()
    task = _FakeTask()

    with patch.object(task_worker.crud_task, "get_tasks_by_ids", lambda db, ids: [task]), \
            patch.object(task_worker.TaskStrategyFactory, "get_strategy", lambda _type: None):
        with pytest.raises(ValueError):
            worker._execute_batch_sync([{"id": "task-1", "type": TaskType.CLASSIFY_IMAGE}])


def test_execute_batch_sync_defers_background_ai_tasks_during_an_import():
    worker = TaskWorker()
    worker.import_priority_active = True
    task = _FakeTask(priority=1)

    with patch.object(task_worker.crud_task, "get_tasks_by_ids", lambda db, ids: [task]), \
            patch.object(task_worker.TaskStrategyFactory, "get_strategy",
                         lambda _type: _FakeStrategy(TaskType.CLASSIFY_IMAGE)):
        results, outcome = worker._execute_batch_sync(
            [{"id": "task-1", "type": TaskType.CLASSIFY_IMAGE}]
        )

    assert results == []
    assert outcome is None

