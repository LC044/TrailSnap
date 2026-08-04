from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.crud import notification


pytestmark = pytest.mark.smoke


def test_serialize_converts_ids_dates_and_read_flag():
    user_id = uuid4()
    created = datetime(2026, 8, 4, 12, 30)
    item = SimpleNamespace(
        id=uuid4(), user_id=user_id, type="SYSTEM", level="info",
        title="Hello", body={"x": 1}, ref_type=None, ref_id=None,
        read=1, created_at=created, read_at=None,
    )

    result = notification._serialize(item)

    assert result["id"] == str(item.id)
    assert result["user_id"] == str(user_id)
    assert result["read"] is True
    assert result["created_at"] == created.isoformat()
    assert result["read_at"] is None


def test_create_notification_flushes_without_commit_when_requested():
    db = MagicMock()
    user_id = uuid4()

    result = notification.create_notification(
        db, user_id, "SYSTEM", "Title", body={"message": "x"}, commit=False
    )

    db.add.assert_called_once_with(result)
    db.flush.assert_called_once_with()
    db.commit.assert_not_called()
    assert result.user_id == user_id
    assert result.read is False


def test_mark_read_rejects_notification_owned_by_another_user():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None

    assert notification.mark_read(db, uuid4(), uuid4()) is False
    db.commit.assert_not_called()
