"""Unit tests for the task-management REST router (app/api/tasks.py).

Covers the four endpoints that wrap ``TaskManager`` / ``crud_task``:

* ``GET  /types`` lists every ``TaskType`` enum value.
* ``GET  /`` delegates to ``crud_task.list_tasks`` with filters.
* ``POST /fast-mode`` toggles ``TaskManager.set_fast_mode``.
* ``GET  /status`` returns ``TaskManager.get_instance().get_status()``.

The SSE endpoint is intentionally not covered here; it relies on
``sse_starlette`` which the existing globals do not need to verify.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api import tasks as tasks_api
from app.db.models.photo import FileType
from app.db.models.task import TaskStatus, TaskType


pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


# ----------------------- GET /types -----------------------


def test_get_task_types_returns_enum_values():
    """``get_task_types`` must wrap a list of {type, description} into BaseResponse.

    Each ``TaskType`` enum is rendered as a dict with ``type`` and a
    human-readable ``description`` string. We assert the response shape and
    that every reported ``type`` is a real ``TaskType`` value.
    """
    from app.db.models.task import TaskType as RealTaskType

    with patch("app.api.tasks.BaseResponse.success") as success:
        result = tasks_api.get_task_types()

    success.assert_called_once()
    payload = success.call_args.kwargs["data"]
    assert isinstance(payload, list)
    assert len(payload) == len(list(RealTaskType))
    valid_values = {t.value for t in RealTaskType}
    for item in payload:
        assert item["type"] in valid_values
        assert isinstance(item["description"], str)


# ----------------------- GET / -----------------------


def test_list_tasks_delegates_to_crud_with_filters():
    """``list_tasks`` must forward every filter arg to ``crud_task.list_tasks``.

    Filters include ``status``, ``type``, ``limit``, and ``updated_since``
    so the client can poll only changed tasks after a reconnect.
    """
    db = MagicMock()
    fake_rows = [{"id": "t1"}, {"id": "t2"}]
    with patch("app.api.tasks.crud_task.list_tasks", return_value=fake_rows) as list_call:
        with patch("app.api.tasks.BaseResponse.success") as success:
            tasks_api.list_tasks(
                status="PENDING",
                type="PROCESS_BASIC",
                limit=10,
                updated_since="2026-07-25T00:00:00",
                db=db,
            )

    list_call.assert_called_once_with(
        db,
        status="PENDING",
        type="PROCESS_BASIC",
        limit=10,
        updated_since="2026-07-25T00:00:00",
    )
    success.assert_called_once_with(data=fake_rows)


def test_list_tasks_passes_defaults_when_no_filters():
    """Default values for status / type / limit reach ``crud_task`` intact."""
    db = MagicMock()
    with patch("app.api.tasks.crud_task.list_tasks", return_value=[]) as list_call:
        with patch("app.api.tasks.BaseResponse.success"):
            tasks_api.list_tasks(status=None, type=None, limit=50, updated_since=None, db=db)

    list_call.assert_called_once_with(
        db, status=None, type=None, limit=50, updated_since=None,
    )


# ----------------------- POST /fast-mode -----------------------


def test_set_fast_mode_calls_task_manager_with_bool():
    """``set_fast_mode`` must invoke ``TaskManager.set_fast_mode(enabled)``.

    Returns ``BaseResponse`` carrying the resulting fast-mode flag so the
    client can show a toast reflecting the toggle.
    """
    fake_manager = MagicMock()

    with patch("app.api.tasks.TaskManager.get_instance", return_value=fake_manager) as get_inst:
        with patch("app.api.tasks.BaseResponse.success") as success:
            tasks_api.set_fast_mode(enabled=True)

    get_inst.assert_called_once_with()
    fake_manager.set_fast_mode.assert_called_once_with(True)
    success.assert_called_once()
    assert success.call_args.kwargs["data"]["fast_mode"] is True
    assert success.call_args.kwargs["data"]["status"] == "success"


# ----------------------- GET /status -----------------------


def test_get_status_returns_singleton_snapshot():
    """``get_status`` must return the TaskManager singleton's snapshot."""
    expected = {"running": 2, "pending": 5, "completed": 10, "failed": 1}
    fake_manager = MagicMock()
    fake_manager.get_status.return_value = expected

    with patch("app.api.tasks.TaskManager.get_instance", return_value=fake_manager) as get_inst:
        with patch("app.api.tasks.BaseResponse.success") as success:
            tasks_api.get_status(db=MagicMock())

    get_inst.assert_called_once_with()
    fake_manager.get_status.assert_called_once_with()
    success.assert_called_once_with(data=expected)


# ----------------------- pause / resume category -----------------------


def test_pause_category_delegates_to_task_manager():
    """``pause_category`` forwards the category string to ``TaskManager``."""
    fake_manager = MagicMock()

    with patch("app.api.tasks.TaskManager.get_instance", return_value=fake_manager) as get_inst:
        with patch("app.api.tasks.BaseResponse.success") as success:
            tasks_api.pause_category(category="OCR")

    get_inst.assert_called_once_with()
    fake_manager.pause_category.assert_called_once_with("OCR")
    success.assert_called_once_with(data={"status": "success"})


def test_resume_category_delegates_to_task_manager():
    fake_manager = MagicMock()

    with patch("app.api.tasks.TaskManager.get_instance", return_value=fake_manager) as get_inst:
        with patch("app.api.tasks.BaseResponse.success") as success:
            tasks_api.resume_category(category="FACE")

    get_inst.assert_called_once_with()
    fake_manager.resume_category.assert_called_once_with("FACE")
    success.assert_called_once_with(data={"status": "success"})


# ----------------------- POST /photo-processing -----------------------


def _query_returning(first=None, all_rows=None):
    query = MagicMock()
    query.filter.return_value = query
    query.order_by.return_value = query
    query.first.return_value = first
    query.all.return_value = [] if all_rows is None else all_rows
    return query


def test_create_photo_processing_task_queues_owned_photo_at_interactive_priority():
    user_id = uuid4()
    photo_id = uuid4()
    photo = SimpleNamespace(
        id=photo_id,
        owner_id=user_id,
        file_type=FileType.image,
        file_path="/photos/example.jpg",
    )
    db = MagicMock()
    db.query.side_effect = [_query_returning(first=photo), _query_returning(all_rows=[])]
    current_user = SimpleNamespace(id=user_id)
    created_task = SimpleNamespace(id=uuid4(), status=TaskStatus.PENDING)
    manager = MagicMock()
    manager.add_task.return_value = created_task

    with (
        patch("app.api.tasks.TaskManager.get_instance", return_value=manager),
        patch("app.api.tasks.BaseResponse.success") as success,
    ):
        tasks_api.create_photo_processing_task(
            tasks_api.PhotoProcessingCreate(
                photo_id=photo_id,
                operation=TaskType.OCR,
                force=True,
            ),
            db=db,
            current_user=current_user,
        )

    manager.add_task.assert_called_once()
    args, kwargs = manager.add_task.call_args
    assert args[0] is db
    assert args[1] == TaskType.OCR
    assert args[2]["photo_id"] == str(photo_id)
    assert args[2]["force"] is True
    assert args[2]["source"] == "lightbox"
    assert kwargs["priority"] == tasks_api.INTERACTIVE_TASK_PRIORITY
    assert kwargs["owner_id"] == user_id
    success.assert_called_once_with(data={"task": created_task, "reused": False})


def test_create_photo_processing_task_reuses_matching_active_task():
    user_id = uuid4()
    photo_id = uuid4()
    photo = SimpleNamespace(
        id=photo_id,
        owner_id=user_id,
        file_type=FileType.image,
        file_path="/photos/example.jpg",
    )
    active_task = SimpleNamespace(
        id=uuid4(),
        status=TaskStatus.PROCESSING,
        payload={"photo_id": str(photo_id)},
    )
    db = MagicMock()
    db.query.side_effect = [
        _query_returning(first=photo),
        _query_returning(all_rows=[active_task]),
    ]

    with (
        patch("app.api.tasks.TaskManager.get_instance") as get_manager,
        patch("app.api.tasks.BaseResponse.success") as success,
    ):
        tasks_api.create_photo_processing_task(
            tasks_api.PhotoProcessingCreate(photo_id=photo_id, operation=TaskType.RECOGNIZE_FACE),
            db=db,
            current_user=SimpleNamespace(id=user_id),
        )

    get_manager.assert_not_called()
    success.assert_called_once_with(data={"task": active_task, "reused": True})


def test_create_photo_processing_task_rejects_missing_or_foreign_photo():
    db = MagicMock()
    db.query.return_value = _query_returning(first=None)

    with pytest.raises(HTTPException) as exc:
        tasks_api.create_photo_processing_task(
            tasks_api.PhotoProcessingCreate(photo_id=uuid4(), operation=TaskType.OCR),
            db=db,
            current_user=SimpleNamespace(id=uuid4()),
        )

    assert exc.value.status_code == 404


def test_create_photo_processing_task_rejects_non_ai_operation():
    with pytest.raises(HTTPException) as exc:
        tasks_api.create_photo_processing_task(
            tasks_api.PhotoProcessingCreate(photo_id=uuid4(), operation=TaskType.EXTRACT_METADATA),
            db=MagicMock(),
            current_user=SimpleNamespace(id=uuid4()),
        )

    assert exc.value.status_code == 400
