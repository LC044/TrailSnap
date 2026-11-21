"""Task payload serialization guards for the /api/tasks endpoints."""
from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.api.tasks import _serialize_task

pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


def _task(**overrides):
    base = dict(
        id=uuid4(),
        type="scan",
        status="queued",
        priority=5,
        total_items=10,
        processed_items=3,
        error=None,
        owner_id=uuid4(),
        created_at=datetime(2026, 1, 2, 3, 4, 5),
        updated_at=None,
        payload={"folder": "trip"},
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_serialize_task_renders_identifiers_as_strings():
    task = _task()
    result = _serialize_task(task)
    assert result["id"] == str(task.id)
    assert result["owner_id"] == str(task.owner_id)
    assert result["type"] == "scan"
    assert result["status"] == "queued"
    assert result["priority"] == 5


def test_serialize_task_defaults_missing_counters_to_zero():
    result = _serialize_task(_task(total_items=None, processed_items=None))
    assert result["total_items"] == 0
    assert result["processed_items"] == 0


def test_serialize_task_keeps_owner_none_when_task_has_no_owner():
    result = _serialize_task(_task(owner_id=None))
    assert result["owner_id"] is None


def test_serialize_task_defaults_missing_payload_to_empty_mapping():
    result = _serialize_task(_task(payload=None))
    assert result["payload"] == {}


def test_serialize_task_iso_formats_timestamps_and_keeps_error():
    updated = datetime(2026, 2, 3, 4, 5, 6)
    task = _task(updated_at=updated, error="boom")
    result = _serialize_task(task)
    assert result["created_at"] == task.created_at.isoformat()
    assert result["updated_at"] == updated.isoformat()
    assert result["error"] == "boom"


def test_serialize_task_leaves_missing_timestamps_as_none():
    result = _serialize_task(_task(created_at=None, updated_at=None))
    assert result["created_at"] is None
    assert result["updated_at"] is None
