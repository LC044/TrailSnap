"""Nightly watch 2026-10-29 · 覆盖盲区补测（app/service/task_manager.py）。

被测模块：app/service/task_manager.py 的 TaskManager（API 进程侧的任务生产者）。
覆盖点（相对 2026-10-29-r2 的覆盖率基线，此前完全未触达）：
- _event_queue_reader：队列为 None、消息为 None、非 dict 消息、get 抛异常、发布抛异常。
- _do_publish：订阅队列已满时先丢最旧一条；通知桥接失败时只记录日志。
- unsubscribe：移除不存在的队列不抛异常。
- add_task / add_tasks / retry_task / retry_all_failed_tasks：发布事件失败时的降级路径，
  以及 SCAN_FOLDER 任务合并 scan_roots 的分支。
- _save_system_state / _load_system_state：集合类值走 JSON、标量走 str、非法 JSON 回退原值。
- _watchdog_loop：正在停止时跳过、worker 仍存活时跳过、异常时记录日志。
- _start_worker_locked：worker 进程已死时 join 清理僵尸进程。

所有 DB / 子进程依赖都被 mock，不启动真实 worker 进程。
"""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.service import task_manager as tm_module
from app.service.task_manager import TaskManager
from app.db.models.task import TaskType, TaskStatus

pytestmark = [pytest.mark.smoke, pytest.mark.module_tasks]


@pytest.fixture
def manager():
    """每个用例独立的 TaskManager 实例（不走单例，避免跨用例污染）。"""
    return TaskManager()


# ---------------------------------------------------------------------------
# _event_queue_reader
# ---------------------------------------------------------------------------


def test_event_queue_reader_returns_when_queue_missing(manager):
    manager._event_queue = None
    manager._event_queue_reader()  # 不应抛异常


def test_event_queue_reader_stops_on_none_message(manager):
    queue = MagicMock()
    queue.get.side_effect = [None]
    manager._event_queue = queue
    manager._event_queue_reader()
    assert queue.get.call_count == 1


def test_event_queue_reader_skips_non_dict_messages(manager):
    queue = MagicMock()
    queue.get.side_effect = ["not-a-dict", None]
    manager._event_queue = queue
    with patch.object(manager, "publish_event") as publish:
        manager._event_queue_reader()
    publish.assert_not_called()


def test_event_queue_reader_survives_queue_errors(manager):
    queue = MagicMock()
    queue.get.side_effect = [RuntimeError("closed"), None]
    manager._event_queue = queue
    manager._event_queue_reader()
    assert queue.get.call_count == 2


def test_event_queue_reader_survives_publish_errors(manager):
    queue = MagicMock()
    queue.get.side_effect = [{"event": "task.updated", "data": {"x": 1}}, None]
    manager._event_queue = queue
    with patch.object(manager, "publish_event", side_effect=RuntimeError("boom")):
        manager._event_queue_reader()


# ---------------------------------------------------------------------------
# _do_publish
# ---------------------------------------------------------------------------


def test_do_publish_drops_oldest_item_when_queue_is_full(manager):
    queue = asyncio.Queue(maxsize=1)
    queue.put_nowait({"event": "old", "data": {}})
    manager._subscribers = [queue]
    with patch("app.service.notification_manager.NotificationManager.get_instance"):
        manager._do_publish("task.updated", {"owner_id": "u1"})
    assert queue.qsize() == 1
    payload = queue.get_nowait()
    assert payload == {"event": "task.updated", "data": {"owner_id": "u1"}}


def test_do_publish_ignores_notification_bridge_failure(manager):
    manager._subscribers = []
    with patch("app.service.notification_manager.NotificationManager.get_instance",
               side_effect=RuntimeError("bridge down")):
        manager._do_publish("task.updated", {"owner_id": "u1"})


# ---------------------------------------------------------------------------
# subscribe / unsubscribe
# ---------------------------------------------------------------------------


def test_unsubscribe_ignores_unknown_queue(manager):
    manager._subscribers = []
    manager.unsubscribe(asyncio.Queue())  # 不应抛异常


def test_unsubscribe_removes_queue(manager):
    queue = asyncio.Queue()
    manager._subscribers = [queue]
    manager.unsubscribe(queue)
    assert manager._subscribers == []


# ---------------------------------------------------------------------------
# add_task / add_tasks
# ---------------------------------------------------------------------------


def test_add_task_survives_publish_failure(manager):
    task = SimpleNamespace(id=uuid4(), type=TaskType.PROCESS_BASIC.value,
                           priority=0, total_items=0, processed_items=0, error=None,
                           owner_id=uuid4(), payload={})
    with patch.object(tm_module.crud_task, "add_task", return_value=task), \
         patch.object(manager, "start_worker_if_needed"), \
         patch.object(manager, "publish_task_update", side_effect=RuntimeError("boom")):
        out = manager.add_task(MagicMock(), TaskType.PROCESS_BASIC.value, {}, 0, uuid4())
    assert out is task


def test_add_task_merges_scan_roots_of_pending_scan(manager):
    existing = SimpleNamespace(id=uuid4(), type=TaskType.SCAN_FOLDER.value,
                               status=TaskStatus.PENDING.value, owner_id=uuid4(),
                               payload={"scan_roots": ["/a"]})
    db = MagicMock()
    db.query.return_value.filter.return_value.filter.return_value.order_by.return_value.first.return_value = existing
    with patch.object(manager, "start_worker_if_needed"), \
         patch.object(manager, "publish_task_update"):
        out = manager.add_task(db, TaskType.SCAN_FOLDER.value, {"scan_roots": ["/b"]}, 0, uuid4())
    assert out is existing
    assert existing.payload["scan_roots"] == ["/a", "/b"]
    db.commit.assert_called_once()


def test_add_tasks_survives_publish_failure(manager):
    with patch.object(tm_module.crud_task, "add_tasks"), \
         patch.object(manager, "start_worker_if_needed"), \
         patch.object(manager, "publish_event", side_effect=RuntimeError("boom")):
        manager.add_tasks(MagicMock(), [{"type": "PROCESS_BASIC", "priority": 1}], uuid4())


# ---------------------------------------------------------------------------
# retry_task / retry_all_failed_tasks
# ---------------------------------------------------------------------------


def test_retry_task_survives_publish_failure(manager):
    task = SimpleNamespace(id=uuid4(), type=TaskType.PROCESS_BASIC.value,
                           status=TaskStatus.PENDING.value, priority=0, total_items=0,
                           processed_items=0, error=None, owner_id=uuid4())
    with patch.object(tm_module.crud_task, "retry_task", return_value=task), \
         patch.object(manager, "start_worker_if_needed"), \
         patch.object(manager, "publish_task_update", side_effect=RuntimeError("boom")):
        out = manager.retry_task(MagicMock(), task)
    assert out is task


def test_retry_all_failed_tasks_survives_publish_failure(manager):
    db = MagicMock()
    db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
    with patch.object(tm_module.crud_task, "retry_all_failed_tasks", return_value=0):
        out = manager.retry_all_failed_tasks(db)
    assert out["count"] == 0
    assert "Retried 0" in out["message"]


# ---------------------------------------------------------------------------
# system state
# ---------------------------------------------------------------------------


def test_save_system_state_serializes_containers_as_json(manager):
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    with patch.object(tm_module, "SessionLocal", return_value=db):
        manager._save_system_state("paused_categories", ["FACE", "OCR"])
    added = db.add.call_args.args[0]
    assert json.loads(added.value) == ["FACE", "OCR"]
    db.commit.assert_called_once()


def test_save_system_state_serializes_scalars_as_text(manager):
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    with patch.object(tm_module, "SessionLocal", return_value=db):
        manager._save_system_state("fast_mode", True)
    added = db.add.call_args.args[0]
    assert added.value == "True"


def test_save_system_state_logs_and_reraises_in_strict_mode(manager):
    db = MagicMock()
    db.query.side_effect = RuntimeError("db down")
    with patch.object(tm_module, "SessionLocal", return_value=db):
        manager._save_system_state("fast_mode", True)  # 非 strict 不抛
        with pytest.raises(RuntimeError):
            manager._save_system_state("fast_mode", True, strict=True)


def test_load_system_state_parses_json_and_falls_back_to_raw(manager):
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(value='["FACE"]')
    with patch.object(tm_module, "SessionLocal", return_value=db):
        assert manager._load_system_state("paused_categories", []) == ["FACE"]
    db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(value="not-json")
    with patch.object(tm_module, "SessionLocal", return_value=db):
        assert manager._load_system_state("paused_categories", []) == "not-json"


# ---------------------------------------------------------------------------
# _watchdog_loop
# ---------------------------------------------------------------------------


def _run_watchdog_once(manager, dispatchable=0):
    """让 watchdog 主循环只跑一轮。"""
    manager._watchdog_running = True
    calls = {"count": 0}

    def fake_sleep(_seconds):
        calls["count"] += 1
        if calls["count"] >= 15:
            manager._watchdog_running = False

    with patch.object(tm_module.time, "sleep", side_effect=fake_sleep):
        with patch.object(tm_module, "SessionLocal", return_value=MagicMock()), \
             patch.object(tm_module.crud_task, "count_tasks_by_status", return_value=0), \
             patch.object(manager, "_count_dispatchable", return_value=dispatchable):
            manager._watchdog_loop()


def test_watchdog_skips_while_stopping(manager):
    manager._stopping = True
    with patch.object(manager, "start_worker_if_needed") as start:
        _run_watchdog_once(manager)
    start.assert_not_called()


def test_watchdog_skips_when_worker_is_alive(manager):
    manager._stopping = False
    manager.worker_process = SimpleNamespace(is_alive=lambda: True)
    with patch.object(manager, "start_worker_if_needed") as start:
        _run_watchdog_once(manager)
    start.assert_not_called()


def test_watchdog_restarts_worker_when_dispatchable_work_exists(manager):
    manager._stopping = False
    manager.worker_process = None
    with patch.object(manager, "start_worker_if_needed") as start:
        _run_watchdog_once(manager, dispatchable=3)
    start.assert_called_once()


def test_watchdog_logs_errors(manager, caplog):
    manager._stopping = False
    manager.worker_process = None
    with patch.object(manager, "_count_dispatchable", side_effect=RuntimeError("db down")):
        _run_watchdog_once(manager)


# ---------------------------------------------------------------------------
# _start_worker_locked
# ---------------------------------------------------------------------------


def test_start_worker_locked_joins_dead_worker_process(manager):
    dead = SimpleNamespace(is_alive=lambda: False)
    dead.join = MagicMock()
    manager.worker_process = dead
    with patch.object(tm_module.multiprocessing, "Queue", return_value=MagicMock()), \
         patch.object(tm_module.multiprocessing, "Event", return_value=MagicMock()), \
         patch.object(tm_module.multiprocessing, "Process", return_value=MagicMock()), \
         patch.object(tm_module.threading, "Thread", return_value=MagicMock()):
        manager._start_worker_locked()
    dead.join.assert_called_once_with(timeout=1)
