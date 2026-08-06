"""Unit tests for the toolbox REST router (app/api/toolbox.py).

Covers the duplicate-photo scan / list endpoints plus the similar-photo
task lifecycle, the cleanup shortlist, and the taskkick endpoints used by
``Rename`` / ``Organize`` / ``TimeFromFilename``.

``TaskManager`` and ``crud_task`` are patched so no real task worker is started.
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


def _task(task_type, owner_id=None, status_value=TaskStatus.PENDING.value,
          payload=None, task_id=None):
    return SimpleNamespace(
        id=task_id or uuid4(),
        type=task_type.value if hasattr(task_type, "value") else task_type,
        status=status_value,
        owner_id=owner_id or uuid4(),
        payload=payload or {},
        result=None,
        total_items=0,
        processed_items=0,
        created_at=None,
        updated_at=None,
    )


# =========================================================================
# POST /toolbox/duplicate-photos/scan
# =========================================================================


def test_scan_duplicate_photos_returns_existing_pending_task():
    """If a duplicate-scan task is already pending/processing, return it as-is."""
    user = _user()
    db = MagicMock()
    existing = _task(TaskType.FIND_DUPLICATE_PHOTOS, owner_id=user.id,
                     status_value=TaskStatus.PROCESSING.value)

    with patch.object(
        toolbox_api.crud_task, "get_latest_task_by_type_and_owner", return_value=existing,
    ) as fetch:
        response = toolbox_api.scan_duplicate_photos(db=db, current_user=user)

    fetch.assert_called_once()
    assert response.code == 0
    assert response.data is existing


def test_scan_duplicate_photos_creates_new_task_when_none_pending():
    """When no duplicate-scan task is pending, a fresh task is enqueued."""
    user = _user()
    db = MagicMock()
    new_task = _task(TaskType.FIND_DUPLICATE_PHOTOS, owner_id=user.id)

    with patch.object(
        toolbox_api.crud_task, "get_latest_task_by_type_and_owner", return_value=None,
    ), patch.object(
        toolbox_api.TaskManager, "get_instance",
        return_value=MagicMock(add_task=MagicMock(return_value=new_task)),
    ) as mgr_getter:
        response = toolbox_api.scan_duplicate_photos(db=db, current_user=user)

    mgr_getter.assert_called_once()
    assert response.code == 0
    assert response.data is new_task


# =========================================================================
# GET /toolbox/duplicate-photos
# =========================================================================


def test_get_duplicate_photos_empty_when_no_shared_md5():
    """If no MD5 appears more than once, return an empty list of groups."""
    user = _user()
    db = MagicMock()
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

    md5_counts_chain = (
        db.query.return_value.filter.return_value.group_by.return_value.having.return_value
    )
    md5_counts_chain.all.return_value = [
        SimpleNamespace(md5=md5_a, count=2),
        SimpleNamespace(md5=md5_b, count=2),
    ]

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


# =========================================================================
# similar-photo task endpoints
# =========================================================================


def _similar_latest_db_setup():
    """The endpoint reads ``ImageCluster`` joined with ``PhotoCluster`` + ``Photo``
    when no pending task exists. We arrange that chain to return ``None`` so the
    endpoint short-circuits to ``data=None`` without raising.
    """
    db = MagicMock()
    db.query.return_value.join.return_value.join.return_value.filter.return_value.order_by.return_value.first.return_value = None
    return db


def test_create_similar_photo_task_enqueues_via_task_manager():
    user = _user()
    db = MagicMock()
    new_task = _task(TaskType.SIMILAR_PHOTO_CLUSTERING, owner_id=user.id)

    with patch.object(
        toolbox_api.TaskManager, "get_instance",
        return_value=MagicMock(add_task=MagicMock(return_value=new_task)),
    ):
        response = toolbox_api.create_similar_photo_task(threshold=0.85, db=db, current_user=user)

    assert response.code == 0
    assert response.data is new_task


def test_get_latest_similar_task_returns_pending_when_present():
    user = _user()
    db = MagicMock()
    pending = _task(TaskType.SIMILAR_PHOTO_CLUSTERING, owner_id=user.id)

    with patch.object(
        toolbox_api.crud_task, "get_latest_task_by_type_and_owner", return_value=pending
    ) as fetch:
        response = toolbox_api.get_latest_similar_task(db=db, current_user=user)

    fetch.assert_called_once()
    assert response.data is pending


def test_get_latest_similar_task_returns_none_without_cluster():
    user = _user()
    db = _similar_latest_db_setup()

    with patch.object(toolbox_api.crud_task, "get_latest_task_by_type_and_owner", return_value=None):
        response = toolbox_api.get_latest_similar_task(db=db, current_user=user)

    assert response.code == 0
    assert response.data is None


def test_get_similar_task_returns_synthesised_completed_when_missing():
    """GET /similar/tasks/{id} synthesises a COMPLETED response for unknown ids."""
    user = _user()
    db = MagicMock()
    task_id = uuid4()

    with patch.object(toolbox_api.crud_task, "get_task_by_id_and_owner", return_value=None):
        response = toolbox_api.get_similar_task(task_id=task_id, db=db, current_user=user)

    assert response.code == 0
    assert response.data.id == task_id
    assert response.data.status == TaskStatus.COMPLETED.value


def test_cancel_similar_task_marks_pending_as_cancelled():
    user = _user()
    db = MagicMock()
    pending = _task(TaskType.SIMILAR_PHOTO_CLUSTERING, owner_id=user.id,
                     status_value=TaskStatus.PROCESSING.value)

    with patch.object(toolbox_api.crud_task, "get_task_by_id_and_owner", return_value=pending), \
         patch.object(toolbox_api.crud_task, "delete_task") as delete:
        response = toolbox_api.cancel_similar_task(task_id=uuid4(), db=db, current_user=user)

    assert pending.status == TaskStatus.CANCELLED
    delete.assert_called_once_with(db, pending)
    assert response.code == 0


def test_cancel_similar_task_returns_404_when_neither_in_db_nor_clusters():
    user = _user()
    db = MagicMock()

    with patch.object(toolbox_api.crud_task, "get_task_by_id_and_owner", return_value=None):
        db.query.return_value.filter.return_value.all.return_value = []
        response = toolbox_api.cancel_similar_task(task_id=uuid4(), db=db, current_user=user)

    assert response.code == 404


# =========================================================================
# GET /toolbox/cleanup
# =========================================================================


def test_get_photos_for_cleanup_returns_photos_with_default_asc_order():
    user = _user()
    db = MagicMock()
    photo = SimpleNamespace(id=uuid4(), owner_id=user.id)
    db.query.return_value.join.return_value.filter.return_value.order_by.return_value.offset.return_value.limit.return_value.all.return_value = [photo]

    response = toolbox_api.get_photos_for_cleanup(skip=10, limit=5, sort_by="asc", db=db, current_user=user)

    assert response.code == 0
    assert response.data == [photo]


def test_get_photos_for_cleanup_supports_desc_sort():
    user = _user()
    db = MagicMock()
    db.query.return_value.join.return_value.filter.return_value.order_by.return_value.offset.return_value.limit.return_value.all.return_value = []

    response = toolbox_api.get_photos_for_cleanup(skip=0, limit=20, sort_by="desc", db=db, current_user=user)

    assert response.code == 0


# =========================================================================
# Organize task lifecycle + preview-options
# =========================================================================


def test_start_organize_task_reuses_existing_pending():
    user = _user()
    db = MagicMock()
    existing = _task(TaskType.ORGANIZE_PHOTOS, owner_id=user.id,
                     status_value=TaskStatus.PROCESSING.value)

    with patch.object(toolbox_api.crud_task, "get_latest_task_by_type_and_owner",
                      return_value=existing) as fetch:
        response = toolbox_api.start_organize_task(
            req=toolbox_api.OrganizeRequest(target_root_path="/tmp/photos",
                                             strategy="time", action="copy"),
            db=db, current_user=user,
        )

    fetch.assert_called_once()
    assert response.data is existing


def test_start_organize_task_creates_when_no_existing():
    user = _user()
    db = MagicMock()
    new_task = _task(TaskType.ORGANIZE_PHOTOS, owner_id=user.id,
                     payload={"strategy": "person", "action": "move"})

    with patch.object(toolbox_api.crud_task, "get_latest_task_by_type_and_owner",
                      return_value=None), patch.object(
        toolbox_api.TaskManager, "get_instance",
        return_value=MagicMock(add_task=MagicMock(return_value=new_task)),
    ):
        response = toolbox_api.start_organize_task(
            req=toolbox_api.OrganizeRequest(
                target_root_path="/tmp/photos", strategy="person", action="move",
                location_granularity="province", location_format="nested",
            ),
            db=db, current_user=user,
        )

    assert response.code == 0
    assert response.data is new_task


def test_get_latest_organize_task_includes_completed_in_search():
    user = _user()
    db = MagicMock()
    completed = _task(TaskType.ORGANIZE_PHOTOS, owner_id=user.id,
                      status_value=TaskStatus.COMPLETED.value)
    with patch.object(toolbox_api.crud_task, "get_latest_task_by_type_and_owner",
                      return_value=completed) as fetch:
        response = toolbox_api.get_latest_organize_task(db=db, current_user=user)

    requested_statuses = fetch.call_args.args[3]
    assert TaskStatus.COMPLETED.value in requested_statuses
    assert TaskStatus.FAILED.value in requested_statuses
    assert response.data is completed


def test_organize_preview_options_returns_tag_list_for_category_strategy():
    user = _user()
    db = MagicMock()

    tag_chain = (
        db.query.return_value.join.return_value.join.return_value.filter.return_value.distinct.return_value
    )
    tag_chain.all.return_value = [("beach",), ("sunset",)]
    db.query.return_value.outerjoin.return_value.filter.return_value.first.return_value = None

    response = toolbox_api.get_organize_preview_options(
        req=toolbox_api.OrganizePreviewOptionsRequest(strategy="category"),
        db=db, current_user=user,
    )

    assert response.code == 0
    assert sorted(response.data.options) == ["beach", "sunset"]


def test_organize_preview_options_person_adds_unnamed_sentinel():
    user = _user()
    db = MagicMock()
    identity_chain = (
        db.query.return_value.join.return_value.join.return_value.filter.return_value.distinct.return_value
    )
    identity_chain.all.return_value = [("Alice",)]
    db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(id=uuid4())

    response = toolbox_api.get_organize_preview_options(
        req=toolbox_api.OrganizePreviewOptionsRequest(strategy="person"),
        db=db, current_user=user,
    )

    options = set(response.data.options)
    assert "Alice" in options
    assert "未命名" in options


# =========================================================================
# Rename taskkick endpoints
# =========================================================================


def test_start_rename_task_reuses_existing_pending():
    user = _user()
    db = MagicMock()
    existing = _task(TaskType.BATCH_RENAME, owner_id=user.id)
    with patch.object(toolbox_api.crud_task, "get_latest_task_by_type_and_owner",
                      return_value=existing) as fetch:
        response = toolbox_api.start_rename_task(
            req=toolbox_api.RenameRequest(target_root_path="/tmp"),
            db=db, current_user=user,
        )

    fetch.assert_called_once()
    assert response.data is existing


def test_start_rename_task_enqueues_when_no_pending():
    user = _user()
    db = MagicMock()
    new_task = _task(TaskType.BATCH_RENAME, owner_id=user.id,
                     payload={"target_root_path": "/tmp",
                              "template": "IMG_{date}_{time}"})
    with patch.object(toolbox_api.crud_task, "get_latest_task_by_type_and_owner",
                      return_value=None), patch.object(
        toolbox_api.TaskManager, "get_instance",
        return_value=MagicMock(add_task=MagicMock(return_value=new_task)),
    ):
        response = toolbox_api.start_rename_task(
            req=toolbox_api.RenameRequest(target_root_path="/tmp",
                                          template="IMG_{date}_{time}"),
            db=db, current_user=user,
        )

    assert response.data is new_task


def test_get_latest_rename_task_returns_completed_after_failure():
    user = _user()
    db = MagicMock()
    failed = _task(TaskType.BATCH_RENAME, owner_id=user.id,
                   status_value=TaskStatus.FAILED.value)
    with patch.object(toolbox_api.crud_task, "get_latest_task_by_type_and_owner",
                      return_value=failed) as fetch:
        response = toolbox_api.get_latest_rename_task(db=db, current_user=user)

    requested = fetch.call_args.args[3]
    assert TaskStatus.FAILED.value in requested
    assert response.data is failed


# =========================================================================
# Time-from-filename taskkick endpoints
# =========================================================================


def test_start_time_from_filename_task_reuses_existing_pending():
    user = _user()
    db = MagicMock()
    existing = _task(TaskType.BATCH_TIME_FROM_FILENAME, owner_id=user.id)
    with patch.object(toolbox_api.crud_task, "get_latest_task_by_type_and_owner",
                      return_value=existing) as fetch:
        response = toolbox_api.start_time_from_filename_task(
            req=toolbox_api.TimeFromFilenameRequest(target_root_path="/tmp"),
            db=db, current_user=user,
        )

    fetch.assert_called_once()
    assert response.data is existing


def test_start_time_from_filename_task_enqueues_when_no_pending():
    user = _user()
    db = MagicMock()
    new_task = _task(TaskType.BATCH_TIME_FROM_FILENAME, owner_id=user.id,
                     payload={"target_root_path": "/tmp",
                              "only_missing_metadata": True})
    with patch.object(toolbox_api.crud_task, "get_latest_task_by_type_and_owner",
                      return_value=None), patch.object(
        toolbox_api.TaskManager, "get_instance",
        return_value=MagicMock(add_task=MagicMock(return_value=new_task)),
    ):
        response = toolbox_api.start_time_from_filename_task(
            req=toolbox_api.TimeFromFilenameRequest(
                target_root_path="/tmp", only_missing_metadata=True, make="Canon"),
            db=db, current_user=user,
        )

    assert response.data is new_task


def test_get_latest_time_from_filename_task_returns_latest():
    user = _user()
    db = MagicMock()
    completed = _task(TaskType.BATCH_TIME_FROM_FILENAME, owner_id=user.id,
                      status_value=TaskStatus.COMPLETED.value)
    with patch.object(toolbox_api.crud_task, "get_latest_task_by_type_and_owner",
                      return_value=completed) as fetch:
        response = toolbox_api.get_latest_time_from_filename_task(db=db, current_user=user)

    requested = fetch.call_args.args[3]
    assert TaskStatus.COMPLETED.value in requested
    assert response.data is completed
