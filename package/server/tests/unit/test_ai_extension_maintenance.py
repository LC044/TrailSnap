"""Real SQLite regressions for extension waits, drain and pause preservation."""
import asyncio
import io
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.orm import sessionmaker

from app.db.models.task import Task, TaskStatus, TaskType, INTERACTIVE_TASK_PRIORITY
from app.db.models.user import User
from app.service import task_manager, task_worker
from app.service.ai_extension_state import STATE_KEY, WAIT_INSTALL, WAIT_UPDATE, apply_wait_state
from app.service.desktop_maintenance import DesktopMaintenance

pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


def test_server_declares_its_own_minimum_ai_version_with_desktop_auth(monkeypatch):
    from fastapi import HTTPException
    from app.api.system import desktop_ai_extension_requirements
    from app.core.config_manager import VERSION
    from app.service.ai_extension_state import MINIMUM_AI_EXTENSION_VERSION
    monkeypatch.setenv("TS_DESKTOP", "1")
    monkeypatch.setenv("TS_DESKTOP_SESSION_SECRET", "test-secret")
    with pytest.raises(HTTPException) as denied:
        desktop_ai_extension_requirements("wrong-secret")
    assert denied.value.status_code == 404
    response = desktop_ai_extension_requirements("test-secret")
    assert response.code == 0
    assert response.data == {"serverVersion": VERSION, "minimumAIExtensionVersion": MINIMUM_AI_EXTENSION_VERSION}


@pytest.fixture
def runtime(face_sqlite_session, monkeypatch):
    db = face_sqlite_session
    monkeypatch.setenv("TS_DESKTOP", "1")
    factory = sessionmaker(bind=db.get_bind(), expire_on_commit=False)
    monkeypatch.setattr(task_manager, "SessionLocal", factory)
    monkeypatch.setattr(task_worker, "SessionLocal", factory)
    manager = task_manager.TaskManager()
    manager.publish_event = MagicMock()
    manager.start_worker_for_pending_tasks = MagicMock()
    worker = task_worker.TaskWorker()
    worker._publish = MagicMock()
    owner = uuid4()
    db.add(User(id=owner, username=str(owner), settings={}))
    db.commit()
    return db, manager, worker, owner


def add_task(db, owner, kind=TaskType.OCR, priority=INTERACTIVE_TASK_PRIORITY, attempts=2):
    task = Task(id=uuid4(), owner_id=owner, type=kind, status=TaskStatus.PENDING,
                priority=priority, attempt_count=attempts, payload={})
    db.add(task)
    db.commit()
    return task


@pytest.mark.parametrize("state,reason", [("missing", WAIT_INSTALL), ("maintenance", WAIT_UPDATE), ("waiting_update", WAIT_UPDATE)])
def test_missing_or_maintained_extension_defers_interactive_work_without_attempts(runtime, state, reason):
    db, manager, worker, owner = runtime
    task = add_task(db, owner)
    manager._save_system_state(STATE_KEY, state, strict=True)
    results, outcome = worker._execute_batch_sync([{"id": task.id, "type": task.type}])
    db.expire_all()
    assert results == [] and outcome is None
    assert task.status == TaskStatus.PENDING
    assert task.error == reason
    assert task.attempt_count == 2
    assert task.next_retry_at is None


def test_maintenance_race_returns_a_failed_request_to_pending_without_using_retry_budget(runtime, monkeypatch):
    db, manager, worker, owner = runtime
    task = add_task(db, owner)
    reasons = iter([None, WAIT_UPDATE])
    monkeypatch.setattr(worker, "_extension_wait_reason", lambda: next(reasons))
    async def process(*args):
        return [{"task_id": task.id, "status": TaskStatus.FAILED, "error": "AI Service error: 503"}]
    monkeypatch.setattr(task_worker.TaskStrategyFactory, "get_strategy", lambda _: SimpleNamespace(
        resource_key="test", timeout=1, max_attempts=3, process_batch=process))
    results, _ = worker._execute_batch_sync([{"id": task.id, "type": task.type}])
    db.expire_all()
    assert results == []
    assert task.status == TaskStatus.PENDING and task.attempt_count == 2
    assert task.error == WAIT_UPDATE


def test_install_wakes_tasks_without_clearing_user_pauses(runtime):
    db, manager, worker, owner = runtime
    task = add_task(db, owner, priority=1)
    manager._save_system_state("paused_categories", [TaskType.OCR.value])
    manager.set_ai_extension_state("missing")
    db.expire_all()
    assert task.error == WAIT_INSTALL
    manager.set_ai_extension_state("ready")
    db.expire_all()
    assert task.error is None and task.attempt_count == 2
    assert manager._load_system_state("paused_categories") == [TaskType.OCR.value]
    group = next(g for g in manager.get_grouped_status(db) if g["category"] == TaskType.OCR)
    assert group["status"] == "paused"
    manager.start_worker_for_pending_tasks.assert_called()


def test_drain_blocks_worker_restart_until_result_commit_has_finished(runtime):
    db, manager, worker, owner = runtime
    task = add_task(db, owner)
    draining, committed = threading.Event(), threading.Event()
    process = MagicMock(exitcode=0)
    process.is_alive.return_value = True
    def join():
        assert manager._load_system_state(STATE_KEY) == "maintenance"
        draining.set()
        assert committed.wait(5)
    process.join.side_effect = join
    manager.worker_process = process
    manager._worker_stop_event = threading.Event()
    with ThreadPoolExecutor() as pool:
        future = pool.submit(manager.set_ai_extension_state, "maintenance")
        try:
            assert draining.wait(5)
            assert manager._worker_stop_event.is_set()
            manager.start_worker_if_needed()
            assert manager.worker_process is process
            assert not future.done()
        finally:
            committed.set()
        future.result(timeout=5)
    assert manager.worker_process is None
    manager.set_ai_extension_state("ready")
    assert not manager._ai_extension_draining


def test_only_local_model_work_waits_and_interactive_priority_cannot_bypass(runtime, monkeypatch):
    from app.core.config_manager import config_manager
    db, manager, worker, owner = runtime
    other = uuid4()
    db.add(User(id=other, username=str(other), settings={}))
    db.commit()
    monkeypatch.setattr(config_manager, "get_user_config", lambda user, _db: SimpleNamespace(
        ai=SimpleNamespace(analysis_connection_id="builtin" if user == owner else "remote")))
    local = add_task(db, owner, TaskType.VISUAL_DESCRIPTION)
    remote = add_task(db, other, TaskType.VISUAL_DESCRIPTION)
    ocr = add_task(db, owner, TaskType.OCR)
    manager.set_ai_extension_state("missing")
    db.expire_all()
    assert local.error == WAIT_INSTALL and ocr.error == WAIT_INSTALL
    assert remote.error is None
    worker.paused_categories = {TaskType.OCR.value}
    batches = worker._fetch_tasks_to_queues_sync(list(TaskType), {"AI": 0, "CPU": 0, "IO": 0})
    ids = [row["id"] for _, rows in batches for row in rows]
    assert remote.id in ids and local.id not in ids and ocr.id not in ids


def test_restart_reconstructs_availability_and_preserves_user_pause(runtime, monkeypatch):
    import urllib.request
    db, manager, worker, owner = runtime
    task = add_task(db, owner)
    manager._save_system_state("paused_categories", [TaskType.OCR.value])
    manager._save_system_state(STATE_KEY, "maintenance")
    apply_wait_state(db, "maintenance")
    monkeypatch.setenv("TS_DESKTOP_AI_GATEWAY", "http://127.0.0.1:12345")
    monkeypatch.setattr(urllib.request, "urlopen", lambda *args, **kwargs: io.StringIO(json.dumps({"state": "ready"})))
    manager.recover_ai_extension_state()
    db.expire_all()
    assert manager._load_system_state(STATE_KEY) == "ready"
    assert task.error is None and task.attempt_count == 2
    assert manager._load_system_state("paused_categories") == [TaskType.OCR.value]


@pytest.mark.parametrize("installed,expected", [("0.17.2", "waiting_update"), ("0.17.3-beta.1", "waiting_update"),
    ("0.17.3", "ready"), ("0.17.3+build.5", "ready"), ("0.17.10", "ready"), ("0.18.0", "ready")])
def test_restart_checks_server_minimum_before_dispatching_any_ai(runtime, monkeypatch, installed, expected):
    import urllib.request
    from app.service import ai_extension_state
    monkeypatch.setattr(ai_extension_state, "MINIMUM_AI_EXTENSION_VERSION", "0.17.3")
    db, manager, worker, owner = runtime
    task = add_task(db, owner)
    monkeypatch.setenv("TS_DESKTOP_AI_GATEWAY", "http://127.0.0.1:12345")
    monkeypatch.setattr(urllib.request, "urlopen", lambda *args, **kwargs: io.StringIO(json.dumps(
        {"state": "ready", "installedVersion": installed})))
    manager.recover_ai_extension_state()
    db.expire_all()
    assert manager._load_system_state(STATE_KEY) == expected
    assert task.error == (WAIT_UPDATE if expected == "waiting_update" else None)
    assert task.attempt_count == 2


def test_direct_api_result_commit_is_tracked_and_new_inference_is_rejected():
    async def run():
        maintenance = DesktopMaintenance()
        committed = asyncio.Event()
        responses = []
        async def inference(*args):
            await committed.wait()
        async def send(message):
            responses.append(message)
        scope = {"type": "http", "path": "/api/search/semantic", "method": "POST"}
        active = asyncio.create_task(maintenance.middleware(scope, None, send, inference))
        await asyncio.sleep(0)
        assert maintenance.ai_active == 1
        maintenance.ai_draining = True
        await maintenance.middleware(scope, None, send, inference)
        assert responses[0]["status"] == 503
        assert maintenance.ai_active == 1
        committed.set()
        await active
        assert maintenance.ai_active == 0
    asyncio.run(run())
