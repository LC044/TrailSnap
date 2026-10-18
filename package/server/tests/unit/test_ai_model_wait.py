from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.db.models.task import TaskStatus, TaskType
from app.service import ai_model_state as state, task_worker

pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


def snapshot(status):
    return {"models": [{"id": "face", "name": "人脸模型", "status": status}],
            "tasks": {"face": {"selected": "face"}}}


@pytest.mark.parametrize("status,word", [("pending", "尚未下载"), ("downloading", "正在下载"),
                                         ("failed", "下载失败")])
def test_selected_model_wait_status(status, word):
    assert word in state.model_wait_reason(snapshot(status), TaskType.RECOGNIZE_FACE)
    assert state.model_wait_reason(snapshot(status), TaskType.CLASSIFY_IMAGE) is None


def test_ready_and_legacy_catalog_do_not_block():
    assert state.model_wait_reason(snapshot("ready"), TaskType.RECOGNIZE_FACE) is None
    assert state.model_wait_reason({}, TaskType.RECOGNIZE_FACE) is None


def test_ticket_also_requires_ocr():
    data = snapshot("downloading")
    data["tasks"] = {"ocr": {"selected": "face"}}
    assert state.model_wait_reason(data, TaskType.RECOGNIZE_TICKET)


def test_wait_then_ready_executes_without_consuming_attempts(monkeypatch):
    worker = task_worker.TaskWorker()
    worker._publish = MagicMock()
    db = MagicMock()
    task = SimpleNamespace(id="waiting-task", type=TaskType.RECOGNIZE_FACE, owner_id="owner",
                           status=TaskStatus.PENDING, attempt_count=2, priority=1,
                           error=None, next_retry_at=None, created_at=None, updated_at=None,
                           payload={}, total_items=0, processed_items=0)
    strategy = SimpleNamespace(process_batch=AsyncMock(return_value=[]), timeout=10, resource_key="face")
    monkeypatch.setattr(task_worker, "SessionLocal", lambda: db)
    monkeypatch.setattr(task_worker.crud_task, "get_tasks_by_ids", lambda *_: [task])
    monkeypatch.setattr(task_worker.TaskStrategyFactory, "get_strategy", lambda *_: strategy)
    monkeypatch.setattr(worker, "_extension_wait_reason", lambda: None)
    from app.core.config_manager import config_manager
    monkeypatch.setattr(config_manager, "get_user_config", lambda *_: SimpleNamespace(ai=SimpleNamespace(ai_api_url="http://ai")))
    reason = state.model_wait_reason(snapshot("downloading"), task.type)
    with patch.object(state, "get_model_wait_reason", side_effect=[reason, None]):
        infos = [{"id": task.id, "type": task.type}]
        assert worker._execute_batch_sync(infos) == ([], "waiting_for_model")
        assert task.status == TaskStatus.PENDING
        assert task.attempt_count == 2
        assert task.next_retry_at > datetime.now()
        strategy.process_batch.assert_not_awaited()
        assert worker._execute_batch_sync(infos) == ([], "success")
        strategy.process_batch.assert_awaited_once()
        assert task.error is None
        assert task.next_retry_at is None


def test_cache_expires_and_is_scoped_to_service(monkeypatch):
    monkeypatch.setattr(state, "_cache", {})
    now = [0]
    monkeypatch.setattr(state.time, "monotonic", lambda: now[0])
    response = MagicMock()
    response.json.side_effect = [snapshot("downloading"), snapshot("ready"), snapshot("pending")]
    with patch.object(state.requests, "get", return_value=response) as get:
        assert state.get_model_wait_reason("http://one", TaskType.RECOGNIZE_FACE)
        assert state.get_model_wait_reason("http://one", TaskType.RECOGNIZE_FACE)
        assert get.call_count == 1
        now[0] = 6
        assert state.get_model_wait_reason("http://one", TaskType.RECOGNIZE_FACE) is None
        assert state.get_model_wait_reason("http://two", TaskType.RECOGNIZE_FACE)


@pytest.mark.asyncio
async def test_http_detail_and_legacy_not_ready_are_preserved():
    response = SimpleNamespace(status=500, text=AsyncMock(return_value='{"detail":"Face model is not ready yet. Please try again later."}'))
    error = await state.ai_response_error(response)
    assert "AI Service error: 500" in error
    assert "Face model is not ready" in error
    assert task_worker.TaskWorker._is_retryable_error(error)
    assert not task_worker.TaskWorker._is_retryable_error("AI Service error: 500: broken input")


@pytest.mark.asyncio
async def test_non_json_error_is_bounded():
    response = SimpleNamespace(status=500, text=AsyncMock(return_value="x" * 10000))
    assert len(await state.ai_response_error(response)) < 1100


def test_real_backlog_wait_is_scoped_and_visible(face_sqlite_session, monkeypatch):
    from uuid import uuid4
    from app.db.models.task import Task
    from app.db.models.user import User
    from app.crud.task import get_grouped_status
    from app.core.config_manager import config_manager

    db = face_sqlite_session
    owners = [uuid4(), uuid4()]
    for owner in owners:
        db.add(User(id=owner, username=str(owner), settings={}))
    db.commit()
    rows = [Task(type=kind, owner_id=owner, payload={}, attempt_count=2, priority=10)
            for owner, kind in [(owners[0], TaskType.RECOGNIZE_FACE),
                                (owners[0], TaskType.RECOGNIZE_FACE),
                                (owners[0], TaskType.OCR),
                                (owners[1], TaskType.RECOGNIZE_FACE)]]
    db.add_all(rows)
    db.commit()
    monkeypatch.setattr(task_worker, "SessionLocal", lambda: db)
    monkeypatch.setattr(db, "close", lambda: None)
    monkeypatch.setattr(config_manager, "get_user_config", lambda *_: SimpleNamespace(ai=SimpleNamespace(ai_api_url="http://ai")))
    monkeypatch.setattr(state, "get_model_wait_reason", lambda *_: state.model_wait_reason(snapshot("downloading"), TaskType.RECOGNIZE_FACE))
    worker = task_worker.TaskWorker()
    worker._publish = MagicMock()
    monkeypatch.setattr(worker, "_extension_wait_reason", lambda: None)
    assert worker._execute_batch_sync([{"id": rows[0].id, "type": rows[0].type}]) == ([], "waiting_for_model")
    db.expire_all()
    assert all(row.status == TaskStatus.PENDING and row.attempt_count == 2 for row in rows)
    assert all(row.next_retry_at and row.error.startswith(state.WAIT_PREFIX) for row in rows[:2])
    assert all(row.next_retry_at is None and row.error is None for row in rows[2:])
    groups = get_grouped_status(db, set())
    face = next(g for g in groups if g['category'] == TaskType.RECOGNIZE_FACE)
    assert face['failed'] == 0
    assert '正在下载' in face['waiting_reason']
    # User pause is checked before the model probe and is never auto-resumed.
    worker.paused_categories = {TaskType.OCR}
    with patch.object(state, "get_model_wait_reason") as probe:
        assert worker._execute_batch_sync([{"id": rows[2].id, "type": rows[2].type}]) == ([], None)
        probe.assert_not_called()
