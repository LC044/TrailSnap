"""Unit tests for the toolbox REST router (app/api/toolbox.py).

Covers the duplicate-photo scan / list endpoints. ``TaskManager`` and
``crud_task`` are patched so no real task worker is started.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.api import toolbox as toolbox_api
from app.db.models.task import TaskStatus, TaskType


pytestmark = [pytest.mark.smoke, pytest.mark.module_toolbox]


def _user(uid=None):
    return SimpleNamespace(id=uid or uuid4())


def _task(owner_id=None, status_value=TaskStatus.PENDING.value):
    return SimpleNamespace(
        id=uuid4(),
        type=TaskType.FIND_DUPLICATE_PHOTOS.value,
        status=status_value,
        owner_id=owner_id or uuid4(),
        payload={},
        result=None,
        total_items=0,
        processed_items=0,
        created_at=None,
        updated_at=None,
    )


# -------------------- POST /toolbox/duplicate-photos/scan --------------------


def test_scan_duplicate_photos_returns_existing_pending_task():
    """If a duplicate-scan task is already pending/processing, return it as-is."""
    user = _user()
    db = MagicMock()
    existing = _task(owner_id=user.id, status_value=TaskStatus.PROCESSING.value)

    with patch.object(
        toolbox_api.crud_task,
        "get_latest_task_by_type_and_owner",
        return_value=existing,
    ) as fetch:
        response = toolbox_api.scan_duplicate_photos(db=db, current_user=user)

    fetch.assert_called_once()
    assert response.code == 0
    assert response.data is existing


def test_scan_duplicate_photos_creates_new_task_when_none_pending():
    """When no duplicate-scan task is pending, a fresh task is enqueued."""
    user = _user()
    db = MagicMock()
    new_task = _task(owner_id=user.id)

    with patch.object(
        toolbox_api.crud_task,
        "get_latest_task_by_type_and_owner",
        return_value=None,
    ), patch.object(
        toolbox_api.TaskManager,
        "get_instance",
        return_value=MagicMock(add_task=MagicMock(return_value=new_task)),
    ) as mgr_getter:
        response = toolbox_api.scan_duplicate_photos(db=db, current_user=user)

    mgr_getter.assert_called_once()
    assert response.code == 0
    assert response.data is new_task


# -------------------- GET /toolbox/duplicate-photos --------------------


def test_get_duplicate_photos_empty_when_no_shared_md5():
    """If no MD5 appears more than once, return an empty list of groups."""
    user = _user()
    db = MagicMock()
    # First .all() call returns the md5-counts query result (empty).
    db.query.return_value.filter.return_value.group_by.return_value.having.return_value.all.return_value = []

    response = toolbox_api.get_duplicate_photos(db=db, current_user=user)

    assert response.code == 0
    assert response.data == []


def test_get_duplicate_photos_groups_rows_by_md5():
    """Photos sharing an MD5 are grouped together under that MD5."""
    user = _user()
    db = MagicMock()

    md5_a, md5_b = "md5-aaa", "md5-bbb"
    photo_a1 = SimpleNamespace(id=uuid4(), md5=md5_a, owner_id=user.id)
    photo_a2 = SimpleNamespace(id=uuid4(), md5=md5_a, owner_id=user.id)
    photo_b1 = SimpleNamespace(id=uuid4(), md5=md5_b, owner_id=user.id)
    photo_b2 = SimpleNamespace(id=uuid4(), md5=md5_b, owner_id=user.id)

    # First chain: group_by + having returns the MD5 list with counts.
    md5_counts_chain = (
        db.query.return_value.filter.return_value.group_by.return_value.having.return_value
    )
    md5_counts_chain.all.return_value = [
        SimpleNamespace(md5=md5_a, count=2),
        SimpleNamespace(md5=md5_b, count=2),
    ]

    # Second chain: photos filtered by md5.in_(...) -> order_by -> all.
    photos_chain = db.query.return_value.filter.return_value
    photos_chain.order_by.return_value.all.return_value = [
        photo_a1, photo_a2, photo_b1, photo_b2,
    ]

    response = toolbox_api.get_duplicate_photos(db=db, current_user=user)

    assert response.code == 0
    assert len(response.data) == 2
    by_md5 = {g["md5"]: g["photos"] for g in response.data}
    assert sorted(p.id for p in by_md5[md5_a]) == sorted([photo_a1.id, photo_a2.id])
    assert sorted(p.id for p in by_md5[md5_b]) == sorted([photo_b1.id, photo_b2.id])
