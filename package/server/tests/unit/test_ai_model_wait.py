from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.db.models.task import TaskStatus, TaskType
from app.service import ai_model_state as state, task_worker

pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


def snapshot(status):
    return {"models": [{"id": "face", "name": "人脸模型", "status": status}],
            "tasks": {"face": {"selected": "face"}}}


@pytest.mark.parametrize('timeout_source', ['read', 'body', 'gateway'])
def test_clip_inference_timeout_exhausts_retry_budget(monkeypatch, timeout_source):
    import requests
    from urllib3.exceptions import ReadTimeoutError

    from app.service import clip_classification

    if timeout_source == 'gateway':
        response = requests.Response()
        response.status_code = 504
        post = MagicMock(return_value=response)
    elif timeout_source == 'body':
        post = MagicMock(side_effect=requests.ConnectionError(
            ReadTimeoutError(None, '/embedding/text', 'response body timed out')
        ))
    else:
        post = MagicMock(side_effect=requests.ReadTimeout('no embedding response'))
    monkeypatch.setattr(clip_classification.requests, 'post', post)
    with pytest.raises(RuntimeError, match=state.INFERENCE_TIMEOUT_PREFIX) as exc:
        clip_classification.category_vector('http://ai', 'clip', ['train'])
    assert post.call_args.kwargs['timeout'] == 120

    worker = task_worker.TaskWorker()
    worker._publish_task_row = MagicMock()
    db = MagicMock()
    task = SimpleNamespace(id='clip', status=TaskStatus.PROCESSING, error=None,
                           next_retry_at=None, attempt_count=0)
    error = str(exc.value)
    assert worker._is_retryable_error(error)
    assert not worker._is_model_preparing_error(error)
    for attempt in (1, 2):
        assert worker._schedule_retry(db, task, error, 3)
        assert task.attempt_count == attempt
        assert task.status == TaskStatus.PENDING
        assert task.error.startswith(state.INFERENCE_TIMEOUT_PREFIX)
        assert task.next_retry_at > datetime.now()
    task.status = TaskStatus.PROCESSING
    task.next_retry_at = None
    assert not worker._schedule_retry(db, task, error, 3)
    assert task.attempt_count == 3
    assert task.next_retry_at is None


@pytest.mark.asyncio
@pytest.mark.parametrize("task_type", [
    TaskType.CLASSIFY_IMAGE, TaskType.RECOGNIZE_FACE, TaskType.OCR,
    TaskType.IMAGE_EMBEDDING, TaskType.RECOGNIZE_TICKET,
])
@pytest.mark.parametrize("http_status", [None, 504])
async def test_photo_model_batch_reports_inference_timeout(
    monkeypatch, face_sqlite_session, tmp_path, task_type, http_status,
):
    from PIL import Image

    from app.core.config_manager import config_manager
    from app.db.models.task import Task
    from app.service import storage
    from test_basic_pipeline_performance import seed

    db = face_sqlite_session
    owner, (photo,) = seed(db, 1)
    image_path = tmp_path / "photo.jpg"
    Image.new("RGB", (8, 8)).save(image_path)
    monkeypatch.setattr(storage, "get_available_photo_path", lambda *_: str(image_path))
    monkeypatch.setattr(config_manager, "get_user_config",
                        lambda *_: SimpleNamespace(ai=SimpleNamespace(ai_api_url="http://ai")))
    response = MagicMock(status=http_status)
    response.text = AsyncMock(return_value="gateway timed out")
    if http_status is None:
        response.__aenter__.side_effect = TimeoutError()
    else:
        response.__aenter__.return_value = response
    session = MagicMock()
    session.__aenter__.return_value = session
    session.post.return_value = response
    monkeypatch.setattr(state.aiohttp, "ClientSession", lambda: session)

    task = Task(type=task_type, owner_id=owner, payload={"photo_id": str(photo.id)})
    db.add(task)
    db.commit()
    strategy = task_worker.TaskStrategyFactory.get_strategy(task_type)
    (result,) = await strategy.process_batch(None, [task], db)

    session.post.assert_called_once()
    assert result["status"] == TaskStatus.FAILED
    assert result["error"].startswith(state.INFERENCE_TIMEOUT_PREFIX)
    assert not task_worker.TaskWorker._is_model_preparing_error(result["error"])


@pytest.mark.parametrize("task_type,category,resource_key", [
    (TaskType.OCR, "AI", "ocr"),
    (TaskType.RECOGNIZE_TICKET, "AI", "tickets"),
    (TaskType.PROCESS_BASIC, "CPU", "basic"),
])
def test_batch_deadline_uses_inference_timeout_only_for_ai(
    monkeypatch, face_sqlite_session, task_type, category, resource_key,
):
    import asyncio

    from app.db.models.task import Task

    async def wait_for_inference(*_):
        await asyncio.Event().wait()

    db = face_sqlite_session
    task = Task(type=task_type, payload={}, attempt_count=2)
    db.add(task)
    db.commit()
    task_id = task.id
    strategy = SimpleNamespace(task_category=category, resource_key=resource_key,
                               timeout=0.01, max_attempts=3, process_batch=wait_for_inference)
    monkeypatch.setattr(task_worker, "SessionLocal", lambda: db)
    monkeypatch.setattr(task_worker.TaskStrategyFactory, "get_strategy", lambda *_: strategy)
    worker = task_worker.TaskWorker()
    worker._publish_task_row = MagicMock()

    (result,), outcome = worker._execute_batch_sync([{"id": task_id, "type": task_type}])

    assert outcome == "overload"
    assert result["status"] == TaskStatus.FAILED
    assert result["error"].startswith(
        state.INFERENCE_TIMEOUT_PREFIX if category == "AI" else "Task timeout after"
    )
    assert db.get(Task, task_id).attempt_count == 3


def test_timeout_classifier_distinguishes_connection_and_openai_read_timeouts():
    import aiohttp
    import httpx
    from openai import APITimeoutError, InternalServerError

    request = httpx.Request("POST", "http://ai/v1/chat/completions")
    wrapped = APITimeoutError(request)
    wrapped.__cause__ = httpx.ConnectTimeout("connect timed out")
    assert state.inference_timeout_error(wrapped) is None
    assert state.inference_timeout_error(aiohttp.ConnectionTimeoutError()) is None

    wrapped.__cause__ = httpx.ReadTimeout("read timed out")
    assert state.inference_timeout_error(wrapped) == state.INFERENCE_TIMEOUT_PREFIX
    response = httpx.Response(504, request=request)
    assert "HTTP 504" in state.inference_timeout_error(
        InternalServerError("gateway timed out", response=response, body=None)
    )


@pytest.mark.parametrize("status,word", [("pending", "尚未下载"), ("downloading", "正在下载"),
                                         ("failed", "下载失败")])
def test_selected_model_wait_status(status, word):
    assert word in state.model_wait_reason(snapshot(status), TaskType.RECOGNIZE_FACE)
    assert state.model_wait_reason(snapshot(status), TaskType.CLASSIFY_IMAGE) is None


def test_ready_and_legacy_catalog_do_not_block():
    assert state.model_wait_reason(snapshot("ready"), TaskType.RECOGNIZE_FACE) is None
    assert state.model_wait_reason({}, TaskType.RECOGNIZE_FACE) is None


@pytest.mark.parametrize('connection', ['builtin', 'external'])
def test_visual_analysis_waits_only_for_builtin_llm(monkeypatch, connection):
    worker = task_worker.TaskWorker()
    worker._publish = MagicMock()
    db = MagicMock()
    task = SimpleNamespace(id='visual', type=TaskType.VISUAL_DESCRIPTION, owner_id='owner',
                           status=TaskStatus.PENDING, attempt_count=2, priority=1, error=None,
                           next_retry_at=None, created_at=None, updated_at=None, payload={},
                           total_items=0, processed_items=0)
    strategy = SimpleNamespace(process_batch=AsyncMock(return_value=[]), timeout=10, resource_key='llm')
    monkeypatch.setattr(task_worker, 'SessionLocal', lambda: db)
    monkeypatch.setattr(task_worker.crud_task, 'get_tasks_by_ids', lambda *_: [task])
    monkeypatch.setattr(task_worker.TaskStrategyFactory, 'get_strategy', lambda *_: strategy)
    from app.core.config_manager import config_manager
    monkeypatch.setattr(config_manager, 'get_user_config', lambda *_: SimpleNamespace(
        ai=SimpleNamespace(ai_api_url='http://local-ai', analysis_connection_id=connection)))
    data = {'models': [{'id': 'llm', 'name': 'MiniCPM', 'status': 'downloading', 'downloadState': 'queued'}],
            'tasks': {'llm': {'selected': 'llm'}}}
    reason = state.model_wait_reason(data, TaskType.VISUAL_DESCRIPTION)
    assert '排队等待下载' in reason
    with patch.object(state, 'get_model_wait_reason', side_effect=[reason, None]) as probe:
        infos = [{'id': task.id, 'type': task.type}]
        if connection == 'builtin':
            assert worker._execute_batch_sync(infos) == ([], 'waiting_for_model')
            assert task.status == TaskStatus.PENDING and task.attempt_count == 2
            strategy.process_batch.assert_not_awaited()
        assert worker._execute_batch_sync(infos) == ([], 'success')
        strategy.process_batch.assert_awaited_once()
        if connection == 'external':
            probe.assert_not_called()


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


@pytest.mark.parametrize("override_url", [None, "http://payload-ai"])
@pytest.mark.parametrize("error", ["Face model is not ready", "图片分类模型 尚未就绪（pending），请在 AI 模型管理中下载"])
def test_inference_not_ready_invalidates_cache_without_consuming_attempt(monkeypatch, override_url, error):
    from app.core.config_manager import config_manager

    worker = task_worker.TaskWorker()
    worker._publish = MagicMock()
    db = MagicMock()
    api_url = override_url or "http://ai"
    task = SimpleNamespace(id="not-ready", type=TaskType.RECOGNIZE_FACE, owner_id="owner",
                           status=TaskStatus.PENDING, attempt_count=2, priority=10,
                           error=None, next_retry_at=None, created_at=None, updated_at=None,
                           payload={"ai_api_url": override_url} if override_url else {},
                           total_items=0, processed_items=0)
    strategy = SimpleNamespace(process_batch=AsyncMock(return_value=[{
        "task_id": task.id, "task_type": task.type, "status": TaskStatus.FAILED,
        "error": "AI Service error: 500: " + error,
    }]), timeout=10, resource_key="test", max_attempts=3)
    monkeypatch.setattr(state, "_cache", {
        api_url + "/ai/models": (state.time.monotonic(), snapshot("ready")),
        "http://other/ai/models": (state.time.monotonic(), snapshot("ready")),
    })
    monkeypatch.setattr(state, "_refreshing", {})
    monkeypatch.setattr(task_worker, "SessionLocal", lambda: db)
    monkeypatch.setattr(task_worker.crud_task, "get_tasks_by_ids", lambda *_: [task])
    monkeypatch.setattr(task_worker.TaskStrategyFactory, "get_strategy", lambda *_: strategy)
    monkeypatch.setattr(config_manager, "get_user_config", lambda *_: SimpleNamespace(
        ai=SimpleNamespace(ai_api_url="http://ai")))
    assert worker._execute_batch_sync([{"id": task.id, "type": task.type}]) == ([], "waiting_for_model")
    assert api_url + "/ai/models" not in state._cache
    assert "http://other/ai/models" in state._cache
    assert task.status == TaskStatus.PENDING
    assert task.attempt_count == 2
    assert task.next_retry_at > datetime.now()


@pytest.mark.parametrize("other_error", ["设备繁忙", state.WAIT_PREFIX + "other model"])
def test_ready_clears_waiting_backlog_without_touching_other_retries(face_sqlite_session, monkeypatch, other_error):
    from datetime import timedelta
    from uuid import uuid4
    from app.core.config_manager import config_manager
    from app.crud.task import get_grouped_status
    from app.db.models.task import Task
    from app.db.models.user import User

    db = face_sqlite_session
    owner, other_owner = uuid4(), uuid4()
    db.add_all([User(id=value, username=str(value), settings={})
                for value in (owner, other_owner)])
    reason = state.WAIT_PREFIX + "Buffalo L 正在下载，完成后自动继续"
    retry_at = datetime.now() + timedelta(seconds=30)
    rows = [Task(type=kind, owner_id=user, payload={}, priority=10,
                 status=status, attempt_count=2, error=error, next_retry_at=retry_at)
            for user, kind, status, error in [
                (owner, TaskType.RECOGNIZE_FACE, TaskStatus.PENDING, reason),
                (owner, TaskType.RECOGNIZE_FACE, TaskStatus.PENDING, reason),
                (other_owner, TaskType.RECOGNIZE_FACE, TaskStatus.PENDING, other_error),
                (owner, TaskType.OCR, TaskStatus.PENDING, reason),
                (owner, TaskType.RECOGNIZE_FACE, TaskStatus.PENDING, "设备繁忙"),
                (owner, TaskType.RECOGNIZE_FACE, TaskStatus.FAILED, reason),
            ]]
    db.add_all(rows)
    db.commit()
    monkeypatch.setattr(task_worker, "SessionLocal", lambda: db)
    monkeypatch.setattr(db, "close", lambda: None)
    monkeypatch.setattr(config_manager, "get_user_config", lambda *_: SimpleNamespace(ai=SimpleNamespace(ai_api_url="http://ai")))
    monkeypatch.setattr(state, "get_model_wait_reason", lambda *_: None)
    strategy = SimpleNamespace(process_batch=AsyncMock(return_value=[]), timeout=10, resource_key="test")
    monkeypatch.setattr(task_worker.TaskStrategyFactory, "get_strategy", lambda *_: strategy)
    worker = task_worker.TaskWorker()
    worker._publish = MagicMock()
    infos = [{"id": rows[0].id, "type": rows[0].type}]

    worker.paused_categories = {TaskType.RECOGNIZE_FACE}
    assert worker._execute_batch_sync(infos) == ([], None)
    db.expire_all()
    assert rows[1].error == reason
    worker.paused_categories = set()
    assert worker._execute_batch_sync(infos) == ([], "success")
    db.expire_all()
    assert rows[0].status == TaskStatus.PROCESSING
    assert rows[1].status == TaskStatus.PENDING
    assert all(row.error is None and row.next_retry_at is None for row in rows[:2])
    assert [row.error for row in rows[2:]] == [other_error, reason, "设备繁忙", reason]
    assert all(row.next_retry_at == retry_at for row in rows[2:])
    assert all(row.attempt_count == 2 for row in rows)
    groups = get_grouped_status(db, set())
    face = next(group for group in groups if group["category"] == TaskType.RECOGNIZE_FACE)
    if other_error.startswith(state.WAIT_PREFIX):
        assert face["waiting_reason"] == other_error
    else:
        assert "waiting_reason" not in face


@pytest.mark.asyncio
async def test_http_detail_and_legacy_not_ready_are_preserved():
    response = SimpleNamespace(status=500, text=AsyncMock(return_value='{"detail":"Face model is not ready yet. Please try again later."}'))
    error = await state.ai_response_error(response)
    assert "AI Service error: 500" in error
    assert "Face model is not ready" in error
    assert task_worker.TaskWorker._is_retryable_error(error)
    assert not task_worker.TaskWorker._is_retryable_error("AI Service error: 500: broken input")


@pytest.mark.asyncio
async def test_service_unavailable_retry_reports_service_without_overwriting_model_state():
    response = SimpleNamespace(status=503, text=AsyncMock(return_value='{"detail":"sidecar restarting"}'))
    error = await state.ai_response_error(response)
    worker = task_worker.TaskWorker()
    worker._publish_task_row = MagicMock()
    task = SimpleNamespace(id="ticket", status=TaskStatus.PROCESSING, error=None,
                           next_retry_at=None, attempt_count=1)

    assert worker._is_retryable_error(error)
    assert worker._schedule_retry(MagicMock(), task, error, 3)
    assert task.status == TaskStatus.PENDING
    assert task.attempt_count == 1
    assert task.next_retry_at > datetime.now()
    assert task.error == "AI 服务尚未就绪（HTTP 503），恢复后自动继续: sidecar restarting"


def test_expired_generic_ticket_retry_no_longer_marks_the_group_waiting(face_sqlite_session):
    from app.crud.task import get_grouped_status
    from app.db.models.task import Task

    db = face_sqlite_session
    future = datetime.now() + timedelta(minutes=1)
    old_retry = Task(type=TaskType.RECOGNIZE_TICKET, status=TaskStatus.PENDING,
                     error=state.MODEL_RETRY_REASON, next_retry_at=future, payload={})
    db.add_all([
        old_retry,
        Task(type=TaskType.RECOGNIZE_TICKET, status=TaskStatus.PENDING, payload={}),
        Task(type=TaskType.OCR, status=TaskStatus.PENDING,
             error=state.WAIT_PREFIX + "PP-OCRv6 Small 正在下载", payload={}),
    ])
    db.commit()
    groups = {row['category']: row for row in get_grouped_status(db, set())}
    assert groups[TaskType.RECOGNIZE_TICKET]['waiting_reason'] == state.MODEL_RETRY_REASON

    old_retry.next_retry_at = datetime.now() - timedelta(seconds=1)
    db.commit()
    groups = {row['category']: row for row in get_grouped_status(db, set())}
    assert groups[TaskType.RECOGNIZE_TICKET]['pending'] == 2
    assert 'waiting_reason' not in groups[TaskType.RECOGNIZE_TICKET]
    assert '正在下载' in groups[TaskType.OCR]['waiting_reason']


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
