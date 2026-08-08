"""Nightly gap-fill tests for the task-management REST router."""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api import tasks as tasks_api
from app.db.models.task import TaskStatus, TaskType


pytestmark = [pytest.mark.smoke]


def _user(uid=None):
    return SimpleNamespace(id=uid or uuid4(), is_superuser=False)


def _task_stub(**kwargs):
    base = dict(
        id=kwargs.pop("id", uuid4()),
        type=kwargs.pop("type", TaskType.PROCESS_BASIC.value),
        status=kwargs.pop("status", TaskStatus.PENDING.value),
        priority=kwargs.pop("priority", 0),
        created_at=kwargs.pop("created_at", None),
        updated_at=kwargs.pop("updated_at", None),
        error=kwargs.pop("error", None),
        payload=kwargs.pop("payload", {}),
        total_items=kwargs.pop("total_items", 0),
        processed_items=kwargs.pop("processed_items", 0),
        owner_id=kwargs.pop("owner_id", uuid4()),
    )
    base.update(kwargs)
    return SimpleNamespace(**base)

def test_list_recent_tasks_serialises_with_filter_args():
    user = _user()
    db = MagicMock()
    t1 = _task_stub(type="OCR", status="COMPLETED")
    t2 = _task_stub(type="FACE", status="FAILED")
    with patch("app.api.tasks.crud_task.list_tasks", return_value=[t1, t2]) as list_call:
        with patch("app.api.tasks.BaseResponse.success") as success:
            tasks_api.list_recent_tasks(
                since="2026-08-08T00:00:00",
                limit=50,
                token=None,
                db=db,
                current_user=user,
            )
    list_call.assert_called_once_with(
        db, status=None, type=None, limit=50, updated_since="2026-08-08T00:00:00"
    )
    payload = success.call_args.kwargs["data"]
    assert [row["id"] for row in payload] == [str(t1.id), str(t2.id)]
    assert payload[0]["type"] == "OCR"
    assert payload[1]["status"] == "FAILED"

def test_list_recent_tasks_returns_empty_list_when_no_updates():
    user = _user()
    db = MagicMock()
    with patch("app.api.tasks.crud_task.list_tasks", return_value=[]):
        with patch("app.api.tasks.BaseResponse.success") as success:
            tasks_api.list_recent_tasks(
                since="2026-01-01T00:00:00",
                limit=10,
                token=None,
                db=db,
                current_user=user,
            )
    assert success.call_args.kwargs["data"] == []

def test_get_task_returns_existing_task_when_found():
    db = MagicMock()
    existing = _task_stub()
    with patch("app.api.tasks.crud_task.get_task", return_value=existing) as get_call:
        with patch("app.api.tasks.BaseResponse.success") as success:
            tasks_api.get_task(task_id=existing.id, db=db)
    get_call.assert_called_once_with(db, existing.id)
    success.assert_called_once_with(data=existing)

def test_get_task_returns_synthetic_completed_stub_when_missing():
    db = MagicMock()
    missing_id = uuid4()
    with patch("app.api.tasks.crud_task.get_task", return_value=None):
        with patch("app.api.tasks.BaseResponse.success") as success:
            tasks_api.get_task(task_id=missing_id, db=db)
    payload = success.call_args.kwargs["data"]
    assert payload.id == missing_id
    assert payload.status == TaskStatus.COMPLETED
    assert payload.type == TaskType.PROCESS_BASIC
    assert payload.priority == 0

def test_create_task_delegates_to_task_manager_and_forwards_owner():
    user = _user()
    db = MagicMock()
    payload_in = tasks_api.TaskCreate(type=TaskType.PROCESS_BASIC.value, payload={"k": 1})
    fake_task = _task_stub(owner_id=user.id)
    fake_manager = MagicMock()
    fake_manager.add_task.return_value = fake_task
    with patch("app.api.tasks.TaskManager.get_instance", return_value=fake_manager) as get_inst:
        with patch("app.api.tasks.BaseResponse.success") as success:
            tasks_api.create_task(task_in=payload_in, db=db, current_user=user)
    get_inst.assert_called_once_with()
    fake_manager.add_task.assert_called_once()
    forwarded_payload = fake_manager.add_task.call_args.args[2]
    assert forwarded_payload["user_id"] == str(user.id)
    assert forwarded_payload["k"] == 1
    success.assert_called_once_with(data=fake_task)

def test_create_task_rejects_invalid_task_type_with_400():
    user = _user()
    db = MagicMock()
    payload_in = tasks_api.TaskCreate(type="DEFINITELY_NOT_A_REAL_TYPE", payload={})
    fake_manager = MagicMock()
    with patch("app.api.tasks.TaskManager.get_instance", return_value=fake_manager):
        with pytest.raises(HTTPException) as exc_info:
            tasks_api.create_task(task_in=payload_in, db=db, current_user=user)
    assert exc_info.value.status_code == 400
    assert "Invalid task type" in exc_info.value.detail
    fake_manager.add_task.assert_not_called()

def test_cancel_task_returns_404_when_task_missing():
    db = MagicMock()
    missing = uuid4()
    with patch("app.api.tasks.crud_task.get_task", return_value=None):
        with pytest.raises(HTTPException) as exc_info:
            tasks_api.cancel_task(task_id=missing, db=db)
    assert exc_info.value.status_code == 404

def test_cancel_task_rejects_already_finished_tasks():
    for finished in [TaskStatus.COMPLETED.value, TaskStatus.FAILED.value, TaskStatus.CANCELLED.value]:
        db = MagicMock()
        task = _task_stub(status=finished)
        with patch("app.api.tasks.crud_task.get_task", return_value=task):
            with pytest.raises(HTTPException) as exc_info:
                tasks_api.cancel_task(task_id=task.id, db=db)
        assert exc_info.value.status_code == 400
        assert "finished" in exc_info.value.detail.lower()

def test_cancel_task_delegates_to_crud_on_pending_task():
    db = MagicMock()
    task = _task_stub(status=TaskStatus.PENDING.value)
    cancelled = _task_stub(status=TaskStatus.CANCELLED.value)
    with patch("app.api.tasks.crud_task.get_task", return_value=task):
        with patch("app.api.tasks.crud_task.cancel_task", return_value=cancelled) as do_cancel:
            with patch("app.api.tasks.BaseResponse.success") as success:
                tasks_api.cancel_task(task_id=task.id, db=db)
    do_cancel.assert_called_once_with(db, task)
    success.assert_called_once_with(data=cancelled)

def test_retry_task_returns_404_when_task_missing():
    db = MagicMock()
    with patch("app.api.tasks.crud_task.get_task", return_value=None):
        with pytest.raises(HTTPException) as exc_info:
            tasks_api.retry_task(task_id=uuid4(), db=db)
    assert exc_info.value.status_code == 404

def test_retry_task_rejects_non_failed_tasks():
    for non_failed in [TaskStatus.PENDING.value, TaskStatus.PROCESSING.value, TaskStatus.COMPLETED.value, TaskStatus.CANCELLED.value]:
        db = MagicMock()
        task = _task_stub(status=non_failed)
        with patch("app.api.tasks.crud_task.get_task", return_value=task):
            with pytest.raises(HTTPException) as exc_info:
                tasks_api.retry_task(task_id=task.id, db=db)
        assert exc_info.value.status_code == 400
        assert "failed" in exc_info.value.detail.lower()

def test_retry_task_delegates_to_task_manager_on_failed():
    db = MagicMock()
    task = _task_stub(status=TaskStatus.FAILED.value)
    retried = _task_stub(status=TaskStatus.PENDING.value)
    fake_manager = MagicMock()
    fake_manager.retry_task.return_value = retried
    with patch("app.api.tasks.crud_task.get_task", return_value=task):
        with patch("app.api.tasks.TaskManager.get_instance", return_value=fake_manager):
            with patch("app.api.tasks.BaseResponse.success") as success:
                tasks_api.retry_task(task_id=task.id, db=db)
    fake_manager.retry_task.assert_called_once_with(db, task)
    success.assert_called_once_with(data=retried)

def test_retry_all_failed_tasks_forwards_optional_type_filter():
    db = MagicMock()
    expected = {"retried": 4, "skipped": 1}
    fake_manager = MagicMock()
    fake_manager.retry_all_failed_tasks.return_value = expected
    with patch("app.api.tasks.TaskManager.get_instance", return_value=fake_manager) as get_inst:
        with patch("app.api.tasks.BaseResponse.success") as success:
            tasks_api.retry_all_failed_tasks(types=["OCR", "FACE"], db=db)
    get_inst.assert_called_once_with()
    fake_manager.retry_all_failed_tasks.assert_called_once_with(db, ["OCR", "FACE"])
    success.assert_called_once_with(data=expected)

def test_retry_all_failed_tasks_supports_no_type_filter():
    db = MagicMock()
    fake_manager = MagicMock()
    with patch("app.api.tasks.TaskManager.get_instance", return_value=fake_manager):
        with patch("app.api.tasks.BaseResponse.success") as success:
            tasks_api.retry_all_failed_tasks(types=None, db=db)
    fake_manager.retry_all_failed_tasks.assert_called_once_with(db, None)

def test_delete_failed_tasks_forwards_types_and_returns_count():
    db = MagicMock()
    with patch("app.api.tasks.crud_task.delete_failed_tasks", return_value=7) as do_delete:
        with patch("app.api.tasks.BaseResponse.success") as success:
            tasks_api.delete_failed_tasks(types=["OCR"], db=db)
    do_delete.assert_called_once_with(db, ["OCR"])
    payload = success.call_args.kwargs["data"]
    assert payload["count"] == 7
    assert "Deleted 7" in payload["message"]

def test_delete_failed_tasks_handles_zero_count():
    db = MagicMock()
    with patch("app.api.tasks.crud_task.delete_failed_tasks", return_value=0):
        with patch("app.api.tasks.BaseResponse.success") as success:
            tasks_api.delete_failed_tasks(types=None, db=db)
    payload = success.call_args.kwargs["data"]
    assert payload == {"message": "Deleted 0 failed tasks", "count": 0}
