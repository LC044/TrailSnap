"""2026-10-30 nightly coverage for ``app/service/task_worker.py``.

The 2026-10-30 backend scan reported ``service/task_worker.py`` at 90% with 92
uncovered lines.  The uncovered part is concentrated in the *scheduling*
plumbing that decides how work is batched and handed to the worker:

* ``get_chunk_size`` -- the per-task-type batch size, which is the knob that
  decides whether the AI side saturates the CPU or idles it;
* ``TaskQueueManager`` -- the CPU / IO / AI priority queues, including the
  "unknown category" fallbacks and the AI availability gate that must never
  let a lower-priority model overtake the head of the queue;
* ``TaskWorker.CPU_TASKS`` / ``IO_TASKS`` / ``AI_TASKS`` -- the task
  category registry exposed to the API layer.

These are pure in-memory behaviours, so they are cheap to test exactly.
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from app.db.models.task import TaskType
from app.service import task_worker


pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


def _worker_module():
    return task_worker


def _chunk_size(task_type, level="high"):
    with patch.object(task_worker, "resolve_concurrency_level", return_value=level):
        return task_worker.get_chunk_size(task_type)


# ---------------------------------------------------------------------------
# get_chunk_size
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "task_type, expected",
    [
        (TaskType.VISUAL_DESCRIPTION, 1),
        (TaskType.OCR, 2),
        (TaskType.RECOGNIZE_TICKET, 2),
        (TaskType.RECOGNIZE_FACE, 8),
        (TaskType.CLUSTER_FACES, 1),
        (TaskType.DISCOVER_CHAPTERS, 1),
        (TaskType.PROCESS_BASIC, 4),
        (TaskType.EXTRACT_METADATA, 16),
        (TaskType.CLASSIFY_IMAGE, 8),
        (TaskType.IMAGE_EMBEDDING, 8),
    ],
)
def test_chunk_size_on_a_high_concurrency_host(task_type, expected):
    assert _chunk_size(task_type, "high") == expected


def test_chunk_size_falls_back_to_a_smaller_batch_without_high_concurrency():
    assert _chunk_size(TaskType.VISUAL_DESCRIPTION, "medium") == 1
    assert _chunk_size(TaskType.OCR, "medium") == 1
    assert _chunk_size(TaskType.RECOGNIZE_FACE, "medium") == 4
    assert _chunk_size(TaskType.PROCESS_BASIC, "medium") == 4


def test_chunk_size_of_an_unknown_task_type_uses_the_default():
    assert _chunk_size(TaskType.SCAN_FOLDER, "high") == 8
    assert _chunk_size(TaskType.SCAN_FOLDER, "medium") == 4


# ---------------------------------------------------------------------------
# TaskQueueManager
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_queue_manager_round_trips_a_batch():
    manager = task_worker.TaskQueueManager()

    await manager.put_batch("CPU", [{"id": 1}, {"id": 2}], priority=3)

    assert manager.qsize("CPU") == 1
    assert manager.item_count("CPU") == 2
    batch = await manager.get_batch("CPU")
    assert [item["id"] for item in batch] == [1, 2]
    assert manager.item_count("CPU") == 0


@pytest.mark.asyncio
async def test_queue_manager_ignores_an_unknown_category():
    manager = task_worker.TaskQueueManager()

    await manager.put_batch("GPU", [{"id": 1}])

    assert manager.qsize("GPU") == 0
    assert manager.item_count("GPU") == 0
    assert await manager.get_batch("GPU") == []
    assert manager.qsize("GPU") == 0
    assert manager.item_count("GPU") == 0


@pytest.mark.asyncio
async def test_queue_manager_reports_the_lowest_priority():
    manager = task_worker.TaskQueueManager()

    assert manager.get_lowest_priority("CPU") == -9999
    assert manager.get_lowest_priority("GPU") == -9999

    await manager.put_batch("CPU", [{"id": 1}], priority=5)
    await manager.put_batch("CPU", [{"id": 2}], priority=9)

    assert manager.get_lowest_priority("CPU") == 5


@pytest.mark.asyncio
async def test_queue_manager_drains_queued_batches():
    manager = task_worker.TaskQueueManager()
    await manager.put_batch("IO", [{"id": 1}, {"id": 2}])

    drained = manager.drain_queued("IO")

    assert [item["id"] for item in drained] == [1, 2]
    assert manager.qsize("IO") == 0
    assert manager.item_count("IO") == 0


@pytest.mark.asyncio
async def test_queue_manager_task_done_tolerates_an_unknown_category():
    manager = task_worker.TaskQueueManager()

    manager.task_done("GPU")  # must not raise


@pytest.mark.asyncio
async def test_queue_manager_skips_ai_batches_that_are_not_available():
    manager = task_worker.TaskQueueManager()
    await manager.put_batch("AI", [{"id": "batch"}], priority=1)
    seen = []

    def available(items):
        # The first poll reports "the model is still loading"; the gate has to
        # put the batch back instead of dropping it.
        seen.append(items[0]["id"])
        return len(seen) > 1

    batch = await manager.get_available_ai_batch(available)

    assert seen == ["batch", "batch"]
    assert [item["id"] for item in batch] == ["batch"]
    assert manager.item_count("AI") == 0


# ---------------------------------------------------------------------------
# TaskWorker task categories
# ---------------------------------------------------------------------------


def test_worker_exposes_the_task_categories():
    worker = task_worker.TaskWorker()

    assert isinstance(worker.CPU_TASKS, list)
    assert isinstance(worker.IO_TASKS, list)
    assert isinstance(worker.AI_TASKS, list)
    assert set(worker.CPU_TASKS + worker.IO_TASKS + worker.AI_TASKS) <= set(TaskType)


def test_worker_starts_with_the_default_scan_status():
    worker = task_worker.TaskWorker()

    assert worker.scan_status == task_worker.DEFAULT_SCAN_STATUS
    assert worker.accepting_tasks is True
    assert worker.paused_categories == set()


@pytest.mark.asyncio
async def test_completion_context_accumulates_stage_counters():
    worker = task_worker.TaskWorker()
    worker.scan_status = dict(task_worker.DEFAULT_SCAN_STATUS)
    context = task_worker.CompletionContext(worker)

    context.scan_status["processed"] = context.scan_status.get("processed", 0) + 5
    context.apply()

    assert worker.scan_status["processed"] == 5