"""Failure dismissal removes one record and never wins a race with retry."""
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, update
from sqlalchemy.orm import Session

from app.api import tasks as tasks_api
from app.db.models.task import Task, TaskStatus, TaskType

pytestmark = [pytest.mark.smoke]


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Task.__table__.create(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def add_task(db, owner_id, status=TaskStatus.FAILED, **kwargs):
    task = Task(type=TaskType.OCR, owner_id=owner_id, status=status, **kwargs)
    db.add(task)
    db.commit()
    return task


def test_ignore_removes_only_target_and_publishes_after_commit(db):
    user = SimpleNamespace(id=uuid4(), is_superuser=False)
    task = add_task(db, user.id)
    keep = add_task(db, user.id)
    target_id, keep_id = task.id, keep.id
    with patch.object(tasks_api.TaskManager, "get_instance") as manager:
        result = tasks_api.ignore_failed_task(target_id, db, user)
        assert result.code == 0 and result.data == {"count": 1}
        assert db.get(Task, target_id) is None
        assert db.get(Task, keep_id) is not None
        manager.return_value.publish_event.assert_called_once()
        assert tasks_api.ignore_failed_task(target_id, db, user).code == 404


def test_ignore_rejects_other_owner_but_allows_admin(db):
    user = SimpleNamespace(id=uuid4(), is_superuser=False)
    task = add_task(db, uuid4())
    assert tasks_api.ignore_failed_task(task.id, db, user).code == 403
    assert db.get(Task, task.id) is not None
    user.is_superuser = True
    with patch.object(tasks_api.TaskManager, "get_instance"):
        assert tasks_api.ignore_failed_task(task.id, db, user).code == 0


@pytest.mark.parametrize("status", [TaskStatus.PENDING, TaskStatus.PROCESSING, TaskStatus.COMPLETED, TaskStatus.CANCELLED])
def test_ignore_does_not_remove_non_failed_tasks(db, status):
    user = SimpleNamespace(id=uuid4(), is_superuser=False)
    task = add_task(db, user.id, status)
    task_id = task.id
    assert tasks_api.ignore_failed_task(task_id, db, user).code == 409
    assert db.get(Task, task_id).status == status


def test_concurrent_retry_is_protected_by_delete_predicate(db):
    user = SimpleNamespace(id=uuid4(), is_superuser=False)
    task = add_task(db, user.id)
    task_id = task.id

    def retried_between_read_and_delete(*_):
        db.execute(update(Task).where(Task.id == task_id).values(status=TaskStatus.PENDING))
        db.commit()
        return task

    with patch.object(tasks_api.crud_task, "get_task", side_effect=retried_between_read_and_delete):
        assert tasks_api.ignore_failed_task(task_id, db, user).code == 409
    assert db.get(Task, task_id).status == TaskStatus.PENDING


def test_legacy_payload_owner_and_notification_failure(db):
    user = SimpleNamespace(id=uuid4(), is_superuser=False)
    task = add_task(db, None, payload={"user_id": str(user.id)})
    task_id = task.id
    with patch.object(tasks_api.TaskManager, "get_instance", side_effect=RuntimeError("offline")):
        assert tasks_api.ignore_failed_task(task_id, db, user).code == 0
    assert db.get(Task, task_id) is None
