"""Unit tests for task-worker queue ordering and lightweight coordination."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.db.models.task import TaskStatus, TaskType
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
        assert task_worker.get_chunk_size(TaskType.VISUAL_DESCRIPTION) == 1
        assert task_worker.get_chunk_size(TaskType.OCR) == 2
        assert task_worker.get_chunk_size(TaskType.PROCESS_BASIC) == 16

    with patch.object(task_worker.system_config.config.task, "concurrency_level", "low"):
        assert task_worker.get_chunk_size(TaskType.SCAN_FOLDER) == 4
        assert task_worker.get_chunk_size(TaskType.VISUAL_DESCRIPTION) == 1
        assert task_worker.get_chunk_size(TaskType.OCR) == 1


def test_auto_concurrency_uses_detected_device_profile(monkeypatch):
    worker = task_worker.TaskWorker()
    monkeypatch.setattr(task_worker.system_config.config.task, "concurrency_level", "auto")
    monkeypatch.setattr(task_worker, "resolve_concurrency_level", lambda _level: "low")

    assert worker._get_concurrency_settings()["ai_consumer"] == 2


def test_worker_drain_stops_new_fetches_without_stopping_consumers():
    worker = task_worker.TaskWorker()
    worker.running = True

    worker.request_drain()

    assert worker.accepting_tasks is False
    assert worker.running is True
    assert worker.is_drained() is True


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


@pytest.mark.asyncio
async def test_completed_event_keeps_task_payload_for_targeted_ui_refresh():
    worker = task_worker.TaskWorker()
    worker._publish = MagicMock()

    task_id = "00000000-0000-0000-0000-000000000123"
    row = MagicMock()
    row.id = task_id
    row.type = TaskType.SCAN_ALBUM
    row.priority = 1
    row.total_items = 0
    row.processed_items = 0
    row.owner_id = "user-123"
    row.created_at = None
    row.payload = {"album_id": "album-123"}

    query = MagicMock()
    query.filter.return_value.all.return_value = [row]
    db = MagicMock()
    db.query.return_value = query

    with (
        patch.object(task_worker.TaskStrategyFactory, "get_strategy", return_value=None),
        patch.object(task_worker.crud_task, "delete_tasks_by_ids"),
        patch.object(task_worker, "SessionLocal", return_value=db),
    ):
        await worker._flush_results([{
            "task_id": task_id,
            "task_type": TaskType.SCAN_ALBUM,
            "status": TaskStatus.COMPLETED,
        }])

    event = worker._publish.call_args.args
    assert event[0] == "task.updated"
    assert event[1]["status"] == TaskStatus.COMPLETED.value
    assert event[1]["payload"] == {"album_id": "album-123"}
    assert event[1]["owner_id"] == "user-123"


@pytest.mark.asyncio
async def test_paused_category_still_executes_interactive_task():
    worker = task_worker.TaskWorker()
    worker.paused_categories = {TaskType.OCR.value}
    worker.result_queue = AsyncMock()

    task = MagicMock()
    task.id = "interactive-ocr"
    task.type = TaskType.OCR.value
    task.priority = task_worker.INTERACTIVE_TASK_PRIORITY
    db = MagicMock()
    strategy = MagicMock()
    strategy.timeout = 30
    strategy.process_batch = AsyncMock(return_value=[])

    with (
        patch.object(task_worker, "SessionLocal", return_value=db),
        patch.object(task_worker.crud_task, "get_tasks_by_ids", return_value=[task]),
        patch.object(task_worker.TaskStrategyFactory, "get_strategy", return_value=strategy),
    ):
        await worker.execute_batch_task_wrapper(
            [{
                "id": task.id,
                "type": task.type,
                "priority": task.priority,
            }],
            "AI",
        )

    strategy.process_batch.assert_awaited_once_with(worker, [task], db)
    db.commit.assert_called_once_with()


def test_transient_failure_is_scheduled_without_becoming_failed():
    worker = task_worker.TaskWorker()
    worker._publish = MagicMock()
    db = MagicMock()
    task = MagicMock()
    task.id = "task-retry"
    task.type = TaskType.OCR
    task.status = TaskStatus.PROCESSING
    task.attempt_count = 0
    task.created_at = None
    task.updated_at = None
    task.next_retry_at = None
    task.error = None
    task.priority = 1
    task.total_items = 0
    task.processed_items = 0
    task.owner_id = None
    task.payload = {}

    assert worker._schedule_retry(db, task, "AI Service error: 429", 3) is True
    assert task.status == TaskStatus.PENDING
    assert task.attempt_count == 1
    assert task.next_retry_at is not None
    assert "自动重试" in task.error
    db.commit.assert_called_once_with()
    worker._publish.assert_called_once()


def test_model_download_wait_does_not_consume_retry_attempts():
    worker = task_worker.TaskWorker()
    worker._publish = MagicMock()
    db = MagicMock()
    task = MagicMock()
    task.id = "task-model-download"
    task.type = TaskType.VISUAL_DESCRIPTION
    task.status = TaskStatus.PROCESSING
    task.attempt_count = 2
    task.created_at = None
    task.updated_at = None
    task.next_retry_at = None
    task.error = None
    task.priority = 1
    task.total_items = 0
    task.processed_items = 0
    task.owner_id = None
    task.payload = {}

    error = "503: LLM model is downloading; model_status=downloading"
    assert worker._schedule_retry(db, task, error, 3) is True
    assert task.status == TaskStatus.PENDING
    assert task.attempt_count == 2
    assert task.next_retry_at is not None
    assert task.error == "AI 大模型正在下载，下载完成后将自动继续"
    assert worker._is_model_preparing_error(error) is True
    db.commit.assert_called_once_with()
    worker._publish.assert_called_once()


@pytest.mark.asyncio
async def test_process_batch_survives_unknown_dimensions():
    """get_image_dimensions 对损坏图 / 无 cv2 视频会返回 (None, None, None)，
    此时开启分辨率过滤不应让整批 PROCESS_BASIC 因 `None < int` 崩溃。"""
    from app.service.tasks.basic import BasicTaskStrategy

    task_id = "00000000-0000-0000-0000-000000000abc"
    user_id = "user-abc"
    file_path = r"E:\fake\bad.png"

    task = MagicMock()
    task.id = task_id
    task.type = TaskType.PROCESS_BASIC
    task.owner_id = user_id
    task.payload = {"file_path": file_path, "user_id": user_id}

    # DB: no pre-existing photo for this file_path
    query = MagicMock()
    query.filter.return_value.first.return_value = None
    db = MagicMock()
    db.query.return_value = query

    # filter enabled with non-zero thresholds — the crash trigger
    filter_cfg = MagicMock()
    filter_cfg.enable = True
    filter_cfg.min_width = 100
    filter_cfg.min_height = 100
    user_cfg = MagicMock()
    user_cfg.filter = filter_cfg

    # cpu batch returns success but unknown dimensions
    batch_results = [{
        "success": True,
        "thumb_path": "/tmp/thumb.webp",
        "meta": {"photo_time": None, "exif_info": None},
        "size": 1234,
        "width": None,
        "height": None,
        "duration": None,
        "file_name": "bad.png",
        "is_motion_photo": False,
        "md5_hash": "abc",
        "color_info": None,
        "task_id": task_id,
    }]

    loop = MagicMock()
    loop.run_in_executor = AsyncMock(return_value=batch_results)

    worker = MagicMock()

    with (
        patch("app.service.tasks.basic.os.path.exists", return_value=True),
        patch("app.service.tasks.basic.config_manager.get_user_config", return_value=user_cfg),
        patch("app.service.tasks.basic.storage._get_storage_root", return_value="/storage/root"),
        patch("app.service.tasks.basic.asyncio.get_running_loop", return_value=loop),
    ):
        results = await BasicTaskStrategy().process_batch(worker, [task], db)

    assert len(results) == 1
    assert results[0]["status"] == "completed"
    # 尺寸未知时不应被按分辨率过滤丢弃，应正常进入 photo_create_data
    assert "photo_create_data" in results[0]["result"]
    assert results[0]["result"]["photo_create_data"]["photo"].width is None
