"""Unit tests for task-worker queue ordering and lightweight coordination."""

from unittest.mock import MagicMock, patch

import pytest

from app.db.models.task import TaskType
from app.service import task_worker


pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


@pytest.mark.asyncio
async def test_task_queue_manager_dequeues_highest_priority_first():
    manager = task_worker.TaskQueueManager()
    low = [{"id": "low"}]
    high = [{"id": "high"}]

    await manager.put_batch("CPU", low, priority=1)
    await manager.put_batch("CPU", high, priority=9)

    assert manager.qsize("CPU") == 2
    assert manager.get_lowest_priority("CPU") == 1
    assert await manager.get_batch("CPU") == high
    assert await manager.get_batch("CPU") == low
    assert await manager.get_batch("UNKNOWN") == []


def test_get_chunk_size_honors_level_and_task_type_overrides():
    with patch.object(task_worker.system_config.config.task, "concurrency_level", "high"):
        assert task_worker.get_chunk_size(TaskType.SCAN_FOLDER) == 8
        assert task_worker.get_chunk_size(TaskType.VISUAL_DESCRIPTION) == 4
        assert task_worker.get_chunk_size(TaskType.PROCESS_BASIC) == 16

    with patch.object(task_worker.system_config.config.task, "concurrency_level", "low"):
        assert task_worker.get_chunk_size(TaskType.SCAN_FOLDER) == 4
        assert task_worker.get_chunk_size(TaskType.VISUAL_DESCRIPTION) == 2


def test_publish_sends_event_envelope_and_swallows_queue_errors():
    worker = task_worker.TaskWorker()
    queue = MagicMock()
    worker.set_event_queue(queue)

    worker._publish("task.completed", {"task_id": "task-1"})

    queue.put_nowait.assert_called_once_with(
        {"event": "task.completed", "data": {"task_id": "task-1"}}
    )

    queue.put_nowait.side_effect = RuntimeError("queue closed")
    worker._publish("task.failed", {"task_id": "task-2"})
