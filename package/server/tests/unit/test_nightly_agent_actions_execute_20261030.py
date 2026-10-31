"""2026-10-30 nightly coverage for the *execution* half of ``app/service/agent/actions.py``.

The 2026-10-29 nightly scan left ``service/agent/actions.py`` at 88.4% with 113
uncovered lines.  Almost every remaining line sits in the module's write path:

* ``_execute_album_repair`` — applies a photo-count / cover fix and records the
  undo payload, plus every stale-state guard;
* ``_execute_photo_context_repair`` — rewrites ``photo_time`` and the location
  snapshot of a photo, plus its stale-state guards;
* ``_execute_album_metadata_repair`` — turns a repair plan into background
  ``VISUAL_DESCRIPTION`` / ``FIND_DUPLICATE_PHOTOS`` tasks;
* ``get_metadata_repair_progress`` / ``retry_metadata_repair_tasks`` /
  ``cancel_metadata_repair_tasks`` / ``continue_metadata_repair_plan`` — the
  progress and retry surface the API exposes for background repairs;
* ``_execute_album_cleanup`` — soft-deletes duplicate photos and removes empty
  albums.

These are exactly the code paths that mutate a user's photo library, so a
silent mistake there is expensive.  The tests below drive the real functions
against a real (in-memory SQLite) library and assert on both the happy path
and on the exact guard messages.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models.agent_action import AgentActionPlan
from app.db.models.album import Album, AlbumPhoto
from app.db.models.image_description import ImageDescription
from app.db.models.photo import FileType, Photo
from app.db.models.photo_metadata import PhotoMetadata
from app.db.models.tag import PhotoTagRelation
from app.db.models.task import Task, TaskStatus, TaskType
from app.db.models.user import User
from app.service.agent import actions


pytestmark = [pytest.mark.smoke, pytest.mark.module_agent]


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False)()
    owner, stranger = uuid.uuid4(), uuid.uuid4()
    session.add_all([
        User(id=owner, username="exec-owner", hashed_password="x"),
        User(id=stranger, username="exec-stranger", hashed_password="x"),
    ])
    session.commit()
    try:
        yield session, owner, stranger
    finally:
        session.close()
        engine.dispose()


def _photo(db, owner, name, when=None, md5=None):
    photo = Photo(
        id=uuid.uuid4(), owner_id=owner, filename=name, file_path=name,
        file_type=FileType.image, size=1, is_deleted=False, photo_time=when, md5=md5,
    )
    db.add(photo)
    db.flush()
    return photo


def _album(db, owner, name, photos=(), num_photos=None, cover=None):
    album = Album(
        id=uuid.uuid4(), name=name, type="user", owner_id=owner,
        num_photos=len(photos) if num_photos is None else num_photos,
        cover_id=cover.id if cover is not None else None,
    )
    db.add(album)
    db.flush()
    for photo in photos:
        db.add(AlbumPhoto(album_id=album.id, photo_id=photo.id))
    db.flush()
    return album


def _plan(db, owner, plan_type, operations, status="proposed"):
    plan = AgentActionPlan(
        id=uuid.uuid4(), user_id=owner, plan_type=plan_type, title="plan",
        status=status, operations=operations, preview={},
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


# ---------------------------------------------------------------------------
# _execute_album_repair
# ---------------------------------------------------------------------------


def test_execute_album_repair_applies_count_and_cover(db):
    session, owner, _ = db
    first = _photo(session, owner, "a.jpg")
    second = _photo(session, owner, "b.jpg")
    album = _album(session, owner, "trip", photos=(first, second), num_photos=5)
    plan = _plan(session, owner, "album_repair", {
        "selected_repair_ids": ["count-1", "cover-1"],
        "repairs": [
            {"id": "count-1", "kind": "album_count", "album_id": str(album.id),
             "before": 5, "after": 2},
            {"id": "cover-1", "kind": "album_cover", "album_id": str(album.id),
             "before": None, "after": str(second.id)},
        ],
    })

    executed = actions._execute_album_repair(session, owner, plan)

    assert executed.status == "executed"
    assert executed.attempt_count == 1
    assert executed.result["applied_repair_count"] == 2
    assert executed.result["affected_album_count"] == 1
    assert executed.undo_data["repairs"][0]["applied_after"] == 2
    session.refresh(album)
    assert album.num_photos == 2
    assert album.cover_id == second.id


def test_execute_album_repair_rejects_an_empty_selection(db):
    session, owner, _ = db
    plan = _plan(session, owner, "album_repair", {"selected_repair_ids": [], "repairs": []})
    with pytest.raises(ValueError, match="修复计划没有选中的修复项"):
        actions._execute_album_repair(session, owner, plan)


def test_execute_album_repair_rejects_a_missing_album(db):
    session, owner, _ = db
    plan = _plan(session, owner, "album_repair", {
        "selected_repair_ids": ["count-1"],
        "repairs": [{"id": "count-1", "kind": "album_count",
                     "album_id": str(uuid.uuid4()), "before": 1, "after": 1}],
    })
    with pytest.raises(ValueError, match="待修复相册不存在或不可修改"):
        actions._execute_album_repair(session, owner, plan)


def test_execute_album_repair_rejects_a_stale_photo_count(db):
    session, owner, _ = db
    photo = _photo(session, owner, "a.jpg")
    album = _album(session, owner, "trip", photos=(photo,), num_photos=9)
    plan = _plan(session, owner, "album_repair", {
        "selected_repair_ids": ["count-1"],
        "repairs": [{"id": "count-1", "kind": "album_count", "album_id": str(album.id),
                     "before": 5, "after": 1}],
    })
    with pytest.raises(ValueError, match="的照片计数已变化，请重新体检"):
        actions._execute_album_repair(session, owner, plan)


def test_execute_album_repair_rejects_a_cover_outside_the_album(db):
    session, owner, _ = db
    inside = _photo(session, owner, "a.jpg")
    outside = _photo(session, owner, "b.jpg")
    album = _album(session, owner, "trip", photos=(inside,))
    plan = _plan(session, owner, "album_repair", {
        "selected_repair_ids": ["cover-1"],
        "repairs": [{"id": "cover-1", "kind": "album_cover", "album_id": str(album.id),
                     "before": None, "after": str(outside.id)}],
    })
    with pytest.raises(ValueError, match="的推荐封面已不在相册中，请重新体检"):
        actions._execute_album_repair(session, owner, plan)


def test_execute_album_repair_rejects_an_unsupported_operation(db):
    session, owner, _ = db
    photo = _photo(session, owner, "a.jpg")
    album = _album(session, owner, "trip", photos=(photo,))
    plan = _plan(session, owner, "album_repair", {
        "selected_repair_ids": ["weird-1"],
        "repairs": [{"id": "weird-1", "kind": "rename", "album_id": str(album.id)}],
    })
    with pytest.raises(ValueError, match="修复计划包含不支持的操作"):
        actions._execute_album_repair(session, owner, plan)


# ---------------------------------------------------------------------------
# _execute_photo_context_repair
# ---------------------------------------------------------------------------


def test_execute_photo_context_repair_rewrites_time_and_location(db):
    session, owner, _ = db
    photo = _photo(session, owner, "a.jpg", when=datetime(2025, 3, 1, 10, 0))
    session.add(PhotoMetadata(photo_id=photo.id, longitude=114.0, latitude=30.0, city="武汉"))
    session.commit()
    plan = _plan(session, owner, "photo_context_repair", {
        "selected_repair_ids": ["time-1", "loc-1"],
        "repairs": [
            {"id": "time-1", "kind": "photo_time", "photo_id": str(photo.id),
             "before": "2025-03-01T10:00:00", "after": "2025-04-02T08:30:00"},
            {"id": "loc-1", "kind": "photo_location", "photo_id": str(photo.id),
             "before": actions._location_snapshot(session.query(PhotoMetadata).filter(
                 PhotoMetadata.photo_id == photo.id).first()),
             "after": {"longitude": 121.0, "latitude": 31.0, "city": "上海", "address": "黄浦区"}},
        ],
    })

    executed = actions._execute_photo_context_repair(session, owner, plan)

    assert executed.status == "executed"
    assert executed.result["applied_repair_count"] == 2
    assert executed.result["affected_photo_count"] == 1
    assert executed.result["reversible"] is True
    session.refresh(photo)
    assert photo.photo_time == datetime(2025, 4, 2, 8, 30)
    metadata = session.query(PhotoMetadata).filter(PhotoMetadata.photo_id == photo.id).first()
    assert metadata.city == "上海"
    assert metadata.address == "黄浦区"


def test_execute_photo_context_repair_rejects_an_empty_selection(db):
    session, owner, _ = db
    plan = _plan(session, owner, "photo_context_repair", {"selected_repair_ids": [], "repairs": []})
    with pytest.raises(ValueError, match="修复计划没有选中的修复项"):
        actions._execute_photo_context_repair(session, owner, plan)


def test_execute_photo_context_repair_rejects_a_missing_photo(db):
    session, owner, _ = db
    plan = _plan(session, owner, "photo_context_repair", {
        "selected_repair_ids": ["time-1"],
        "repairs": [{"id": "time-1", "kind": "photo_time", "photo_id": str(uuid.uuid4()),
                     "before": None, "after": "2025-04-02T08:30:00"}],
    })
    with pytest.raises(ValueError, match="部分待修复照片已不存在，请重新体检"):
        actions._execute_photo_context_repair(session, owner, plan)


def test_execute_photo_context_repair_rejects_a_changed_album_scope(db):
    session, owner, _ = db
    photo = _photo(session, owner, "a.jpg", when=datetime(2025, 3, 1, 10, 0))
    other = _photo(session, owner, "b.jpg", when=datetime(2025, 3, 2, 10, 0))
    album = _album(session, owner, "trip", photos=(photo,))
    plan = _plan(session, owner, "photo_context_repair", {
        "album_id": str(album.id),
        "selected_repair_ids": ["time-1", "time-2"],
        "repairs": [
            {"id": "time-1", "kind": "photo_time", "photo_id": str(photo.id),
             "before": "2025-03-01T10:00:00", "after": "2025-04-02T08:30:00"},
            {"id": "time-2", "kind": "photo_time", "photo_id": str(other.id),
             "before": "2025-03-02T10:00:00", "after": "2025-04-03T08:30:00"},
        ],
    })
    with pytest.raises(ValueError, match="相册照片范围已变化，请重新体检"):
        actions._execute_photo_context_repair(session, owner, plan)


def test_execute_photo_context_repair_rejects_a_stale_time(db):
    session, owner, _ = db
    photo = _photo(session, owner, "a.jpg", when=datetime(2025, 3, 1, 10, 0))
    plan = _plan(session, owner, "photo_context_repair", {
        "selected_repair_ids": ["time-1"],
        "repairs": [{"id": "time-1", "kind": "photo_time", "photo_id": str(photo.id),
                     "before": "2020-01-01T00:00:00", "after": "2025-04-02T08:30:00"}],
    })
    with pytest.raises(ValueError, match="的拍摄时间已变化，请重新体检"):
        actions._execute_photo_context_repair(session, owner, plan)


def test_execute_photo_context_repair_rejects_an_invalid_time(db):
    session, owner, _ = db
    photo = _photo(session, owner, "a.jpg", when=datetime(2025, 3, 1, 10, 0))
    plan = _plan(session, owner, "photo_context_repair", {
        "selected_repair_ids": ["time-1"],
        "repairs": [{"id": "time-1", "kind": "photo_time", "photo_id": str(photo.id),
                     "before": "2025-03-01T10:00:00", "after": "not-a-datetime"}],
    })
    with pytest.raises(ValueError, match="修复计划包含无效的拍摄时间"):
        actions._execute_photo_context_repair(session, owner, plan)


def test_execute_photo_context_repair_rejects_a_stale_location(db):
    session, owner, _ = db
    photo = _photo(session, owner, "a.jpg", when=datetime(2025, 3, 1, 10, 0))
    session.add(PhotoMetadata(photo_id=photo.id, longitude=114.0, latitude=30.0, city="武汉"))
    session.commit()
    plan = _plan(session, owner, "photo_context_repair", {
        "selected_repair_ids": ["loc-1"],
        "repairs": [{"id": "loc-1", "kind": "photo_location", "photo_id": str(photo.id),
                     "before": {"longitude": None, "latitude": None, "city": None,
                                "district": None, "province": None, "country": None,
                                "address": None, "location_api": None, "scene_id": None},
                     "after": {"longitude": 121.0, "latitude": 31.0}}],
    })
    with pytest.raises(ValueError, match="的地点信息已变化，请重新体检"):
        actions._execute_photo_context_repair(session, owner, plan)


def test_execute_photo_context_repair_rejects_an_empty_location(db):
    session, owner, _ = db
    photo = _photo(session, owner, "a.jpg", when=datetime(2025, 3, 1, 10, 0))
    plan = _plan(session, owner, "photo_context_repair", {
        "selected_repair_ids": ["loc-1"],
        "repairs": [{"id": "loc-1", "kind": "photo_location", "photo_id": str(photo.id),
                     "before": {"longitude": None, "latitude": None, "city": None,
                                "district": None, "province": None, "country": None,
                                "address": None, "location_api": None, "scene_id": None},
                     "after": {"city": "只有城市没有坐标"}}],
    })
    with pytest.raises(ValueError, match="修复计划包含无效的地点信息"):
        actions._execute_photo_context_repair(session, owner, plan)


def test_execute_photo_context_repair_rejects_an_unsupported_operation(db):
    session, owner, _ = db
    photo = _photo(session, owner, "a.jpg", when=datetime(2025, 3, 1, 10, 0))
    plan = _plan(session, owner, "photo_context_repair", {
        "selected_repair_ids": ["weird-1"],
        "repairs": [{"id": "weird-1", "kind": "rename", "photo_id": str(photo.id)}],
    })
    with pytest.raises(ValueError, match="修复计划包含不支持的时间或地点操作"):
        actions._execute_photo_context_repair(session, owner, plan)


# ---------------------------------------------------------------------------
# _execute_album_metadata_repair
# ---------------------------------------------------------------------------


def test_execute_album_metadata_repair_creates_visual_description_tasks(db):
    session, owner, _ = db
    photo = _photo(session, owner, "a.jpg")
    plan = _plan(session, owner, "album_metadata_repair", {
        "selected_repair_ids": ["desc-1"],
        "repairs": [{"id": "desc-1", "kind": "visual_description", "label": "补齐视觉描述",
                     "photo_ids": [str(photo.id)]}],
    })

    executed = actions._execute_album_metadata_repair(session, owner, plan)

    assert executed.status == "executed"
    assert executed.result["queued_item_count"] == 1
    task = session.query(Task).filter(Task.type == TaskType.VISUAL_DESCRIPTION).one()
    assert task.payload["photo_id"] == str(photo.id)
    assert task.payload["source"] == "album_doctor"


def test_execute_album_metadata_repair_reuses_an_active_task(db):
    session, owner, _ = db
    photo = _photo(session, owner, "a.jpg")
    existing = Task(
        id=uuid.uuid4(), type=TaskType.VISUAL_DESCRIPTION, status=TaskStatus.PENDING,
        owner_id=owner, payload={"photo_id": str(photo.id), "file_path": photo.file_path},
    )
    session.add(existing)
    session.commit()
    plan = _plan(session, owner, "album_metadata_repair", {
        "selected_repair_ids": ["desc-1"],
        "repairs": [{"id": "desc-1", "kind": "visual_description", "label": "补齐视觉描述",
                     "photo_ids": [str(photo.id)]}],
    })

    executed = actions._execute_album_metadata_repair(session, owner, plan)

    assert executed.result["task_groups"][0]["reused_task_count"] == 1
    assert session.query(Task).filter(Task.type == TaskType.VISUAL_DESCRIPTION).count() == 1
    assert str(existing.id) in executed.result["task_ids"]


def test_execute_album_metadata_repair_creates_a_file_hash_task(db):
    session, owner, _ = db
    photo = _photo(session, owner, "a.jpg")
    plan = _plan(session, owner, "album_metadata_repair", {
        "selected_repair_ids": ["hash-1"],
        "repairs": [{"id": "hash-1", "kind": "file_hash", "label": "补齐文件指纹",
                     "photo_ids": [str(photo.id)]}],
    })

    executed = actions._execute_album_metadata_repair(session, owner, plan)

    assert executed.status == "executed"
    task = session.query(Task).filter(Task.type == TaskType.FIND_DUPLICATE_PHOTOS).one()
    assert task.payload["photo_ids"] == [str(photo.id)]


def test_execute_album_metadata_repair_rejects_an_empty_selection(db):
    session, owner, _ = db
    plan = _plan(session, owner, "album_metadata_repair", {"selected_repair_ids": [], "repairs": []})
    with pytest.raises(ValueError, match="修复计划没有选中的修复项"):
        actions._execute_album_metadata_repair(session, owner, plan)


def test_execute_album_metadata_repair_rejects_a_missing_photo(db):
    session, owner, _ = db
    plan = _plan(session, owner, "album_metadata_repair", {
        "selected_repair_ids": ["desc-1"],
        "repairs": [{"id": "desc-1", "kind": "visual_description", "label": "补齐视觉描述",
                     "photo_ids": [str(uuid.uuid4())]}],
    })
    with pytest.raises(ValueError, match="部分待处理照片已不存在，请重新体检"):
        actions._execute_album_metadata_repair(session, owner, plan)


def test_execute_album_metadata_repair_rejects_a_changed_album_scope(db):
    session, owner, _ = db
    photo = _photo(session, owner, "a.jpg")
    other = _photo(session, owner, "b.jpg")
    album = _album(session, owner, "trip", photos=(photo,))
    plan = _plan(session, owner, "album_metadata_repair", {
        "album_id": str(album.id),
        "selected_repair_ids": ["desc-1"],
        "repairs": [{"id": "desc-1", "kind": "visual_description", "label": "补齐视觉描述",
                     "photo_ids": [str(photo.id), str(other.id)]}],
    })
    with pytest.raises(ValueError, match="相册照片范围已变化，请重新体检"):
        actions._execute_album_metadata_repair(session, owner, plan)


def test_execute_album_metadata_repair_rejects_an_unsupported_task(db):
    session, owner, _ = db
    photo = _photo(session, owner, "a.jpg")
    plan = _plan(session, owner, "album_metadata_repair", {
        "selected_repair_ids": ["other-1"],
        "repairs": [{"id": "other-1", "kind": "ocr", "label": "别的任务",
                     "photo_ids": [str(photo.id)]}],
    })
    with pytest.raises(ValueError, match="修复计划包含不支持的后台任务"):
        actions._execute_album_metadata_repair(session, owner, plan)


# ---------------------------------------------------------------------------
# get_metadata_repair_progress
# ---------------------------------------------------------------------------


def test_get_metadata_repair_progress_rejects_a_missing_plan(db):
    session, owner, _ = db
    with pytest.raises(ValueError, match="操作计划不存在"):
        actions.get_metadata_repair_progress(session, owner, uuid.uuid4())


def test_get_metadata_repair_progress_rejects_a_plan_without_background_work(db):
    session, owner, _ = db
    plan = _plan(session, owner, "album_organize", {}, status="executed")
    with pytest.raises(ValueError, match="该计划没有可查询的后台修复进度"):
        actions.get_metadata_repair_progress(session, owner, plan.id)


def test_get_metadata_repair_progress_reports_completed_and_pending_items(db):
    session, owner, _ = db
    done = _photo(session, owner, "done.jpg")
    todo = _photo(session, owner, "todo.jpg")
    session.add(ImageDescription(photo_id=done.id, description="一只猫"))
    finished = Task(id=uuid.uuid4(), type=TaskType.VISUAL_DESCRIPTION,
                    status=TaskStatus.COMPLETED, owner_id=owner,
                    payload={"photo_id": str(done.id), "action_plan_id": "x"})
    pending = Task(id=uuid.uuid4(), type=TaskType.VISUAL_DESCRIPTION,
                   status=TaskStatus.PENDING, owner_id=owner,
                   payload={"photo_id": str(todo.id), "action_plan_id": "x"})
    session.add_all([finished, pending])
    session.commit()
    plan = _plan(session, owner, "album_metadata_repair", {}, status="executed")
    plan.result = {"task_groups": [{
        "kind": "visual_description", "label": "补齐视觉描述",
        "photo_ids": [str(done.id), str(todo.id)],
        "task_ids": [str(finished.id), str(pending.id)],
    }]}
    session.commit()

    progress = actions.get_metadata_repair_progress(session, owner, plan.id)

    assert progress["total_items"] == 2
    assert progress["completed_items"] == 1
    assert progress["remaining_items"] == 1
    assert progress["status"] == "processing"
    assert progress["groups"][0]["active_tasks"] == 1
    assert progress["can_cancel"] is True
    assert progress["groups"][0]["status"] == "processing"
    assert progress["recheck"]["missing_description"] == 1


def test_get_metadata_repair_progress_counts_completed_file_hashes(db):
    session, owner, _ = db
    hashed = _photo(session, owner, "hashed.jpg", md5="d41d8cd98f00b204e9800998ecf8427e")
    plan = _plan(session, owner, "album_metadata_repair", {}, status="executed")
    plan.result = {"task_groups": [{
        "kind": "file_hash", "label": "补齐文件指纹",
        "photo_ids": [str(hashed.id)], "task_ids": [],
    }]}
    session.commit()

    progress = actions.get_metadata_repair_progress(session, owner, plan.id)

    assert progress["completed_items"] == 1
    assert progress["remaining_items"] == 0
    assert progress["status"] == "completed"
    assert progress["recheck"]["missing_hash"] == 0


# ---------------------------------------------------------------------------
# retry_metadata_repair_tasks / cancel / continue
# ---------------------------------------------------------------------------


def test_retry_metadata_repair_tasks_rejects_a_plan_without_retryable_work(db):
    session, owner, _ = db
    plan = _plan(session, owner, "album_organize", {}, status="executed")
    with pytest.raises(ValueError, match="该计划没有可重试的后台修复任务"):
        actions.retry_metadata_repair_tasks(session, owner, plan.id)


def test_retry_metadata_repair_tasks_rejects_a_plan_without_remaining_work(db):
    session, owner, _ = db
    photo = _photo(session, owner, "a.jpg")
    session.add(ImageDescription(photo_id=photo.id, description="已完成"))
    session.commit()
    plan = _plan(session, owner, "album_metadata_repair", {}, status="executed")
    plan.result = {"task_groups": [{
        "kind": "visual_description", "label": "补齐视觉描述",
        "photo_ids": [str(photo.id)], "task_ids": [],
    }]}
    session.commit()

    with pytest.raises(ValueError, match="没有可重试的失败或未完成任务"):
        actions.retry_metadata_repair_tasks(session, owner, plan.id)


def test_retry_metadata_repair_tasks_requeues_a_failed_task(db):
    session, owner, _ = db
    photo = _photo(session, owner, "a.jpg")
    failed = Task(id=uuid.uuid4(), type=TaskType.VISUAL_DESCRIPTION, status=TaskStatus.FAILED,
                  owner_id=owner, error="boom",
                  payload={"photo_id": str(photo.id), "action_plan_id": "pending-plan"})
    session.add(failed)
    session.commit()
    plan = _plan(session, owner, "album_metadata_repair", {}, status="executed")
    plan.result = {"task_groups": [{
        "kind": "visual_description", "label": "补齐视觉描述",
        "photo_ids": [str(photo.id)], "task_ids": [str(failed.id)],
    }]}
    session.commit()
    failed.payload = {"photo_id": str(photo.id), "action_plan_id": str(plan.id)}
    session.commit()

    retried = actions.retry_metadata_repair_tasks(session, owner, plan.id)

    assert retried.result["retry_count"] == 1
    assert str(failed.id) in retried.result["last_retried_task_ids"]
    session.refresh(failed)
    assert failed.status == TaskStatus.PENDING
    assert failed.error is None


def test_retry_metadata_repair_tasks_creates_a_task_for_uncovered_photos(db):
    session, owner, _ = db
    photo = _photo(session, owner, "a.jpg")
    plan = _plan(session, owner, "album_metadata_repair", {}, status="executed")
    plan.result = {"task_groups": [{
        "kind": "visual_description", "label": "补齐视觉描述",
        "photo_ids": [str(photo.id)], "task_ids": [],
    }]}
    session.commit()

    retried = actions.retry_metadata_repair_tasks(session, owner, plan.id)

    assert retried.result["retry_count"] == 1
    task = session.query(Task).filter(Task.type == TaskType.VISUAL_DESCRIPTION).one()
    assert task.payload["source"] == "album_doctor_retry"
    assert task.payload["action_plan_id"] == str(plan.id)


def test_retry_metadata_repair_tasks_creates_a_file_hash_task(db):
    session, owner, _ = db
    photo = _photo(session, owner, "a.jpg")
    plan = _plan(session, owner, "album_metadata_repair", {}, status="executed")
    plan.result = {"task_groups": [{
        "kind": "file_hash", "label": "补齐文件指纹",
        "photo_ids": [str(photo.id)], "task_ids": [],
    }]}
    session.commit()

    retried = actions.retry_metadata_repair_tasks(session, owner, plan.id)

    assert retried.result["retry_count"] == 1
    task = session.query(Task).filter(Task.type == TaskType.FIND_DUPLICATE_PHOTOS).one()
    assert task.payload["photo_ids"] == [str(photo.id)]


def test_retry_metadata_repair_tasks_skips_an_unknown_group_kind(db):
    session, owner, _ = db
    plan = _plan(session, owner, "album_metadata_repair", {}, status="executed")
    plan.result = {"task_groups": [{"kind": "ocr", "photo_ids": [], "task_ids": []}]}
    session.commit()
    with pytest.raises(ValueError, match="没有可重试的失败或未完成任务"):
        actions.retry_metadata_repair_tasks(session, owner, plan.id)


def test_cancel_metadata_repair_tasks_rejects_a_plan_without_cancellable_work(db):
    session, owner, _ = db
    plan = _plan(session, owner, "album_organize", {}, status="executed")
    with pytest.raises(ValueError, match="该计划没有可取消的后台修复任务"):
        actions.cancel_metadata_repair_tasks(session, owner, plan.id)


def test_cancel_metadata_repair_tasks_cancels_only_its_own_pending_tasks(db):
    session, owner, _ = db
    photo = _photo(session, owner, "a.jpg")
    plan = _plan(session, owner, "album_metadata_repair", {}, status="executed")
    mine = Task(id=uuid.uuid4(), type=TaskType.VISUAL_DESCRIPTION, status=TaskStatus.PENDING,
                owner_id=owner, payload={"photo_id": str(photo.id), "action_plan_id": str(plan.id)})
    theirs = Task(id=uuid.uuid4(), type=TaskType.VISUAL_DESCRIPTION, status=TaskStatus.PENDING,
                   owner_id=owner, payload={"photo_id": str(photo.id), "action_plan_id": "other"})
    session.add_all([mine, theirs])
    plan.result = {"task_ids": [str(mine.id), str(theirs.id)]}
    session.commit()

    outcome = actions.cancel_metadata_repair_tasks(session, owner, plan.id)

    assert outcome["cancelled_count"] == 1
    session.refresh(mine)
    session.refresh(theirs)
    assert mine.status == TaskStatus.CANCELLED
    assert theirs.status == TaskStatus.PENDING


def test_continue_metadata_repair_plan_rejects_a_plan_that_cannot_continue(db):
    session, owner, _ = db
    plan = _plan(session, owner, "album_metadata_repair", {}, status="proposed")
    with pytest.raises(ValueError, match="该计划不能继续下一批"):
        actions.continue_metadata_repair_plan(session, owner, plan.id)

# ---------------------------------------------------------------------------
# _execute_album_cleanup
# ---------------------------------------------------------------------------


def test_execute_album_cleanup_soft_deletes_duplicates_and_removes_empty_albums(db):
    session, owner, _ = db
    keeper = _photo(session, owner, "keeper.jpg", md5="dup-md5")
    duplicate = _photo(session, owner, "dup.jpg", md5="dup-md5")
    album = _album(session, owner, "empty", photos=(), num_photos=0)
    plan = _plan(session, owner, "album_cleanup", {
        "selected_repair_ids": ["dup-1", "empty-1"],
        "repairs": [
            {"id": "dup-1", "kind": "duplicate_photo", "photo_id": str(duplicate.id),
             "keeper_photo_id": str(keeper.id), "md5": "dup-md5"},
            {"id": "empty-1", "kind": "empty_album", "album_id": str(album.id)},
        ],
    })

    executed = actions._execute_album_cleanup(session, owner, plan)

    assert executed.status == "executed"
    assert executed.result["soft_deleted_photo_count"] == 1
    assert executed.result["removed_empty_album_count"] == 1
    assert executed.result["original_files_deleted"] is False
    session.refresh(duplicate)
    assert duplicate.is_deleted is True
    assert duplicate.deleted_at is not None
    session.refresh(keeper)
    assert keeper.is_deleted is False
    assert session.query(Album).filter(Album.id == album.id).first() is None


def test_execute_album_cleanup_rejects_an_empty_selection(db):
    session, owner, _ = db
    plan = _plan(session, owner, "album_cleanup", {"selected_repair_ids": [], "repairs": []})
    with pytest.raises(ValueError, match="清理计划没有选中的项目"):
        actions._execute_album_cleanup(session, owner, plan)


def test_execute_album_cleanup_rejects_a_changed_duplicate_group(db):
    session, owner, _ = db
    keeper = _photo(session, owner, "keeper.jpg", md5="dup-md5")
    duplicate = _photo(session, owner, "dup.jpg", md5="other-md5")
    plan = _plan(session, owner, "album_cleanup", {
        "selected_repair_ids": ["dup-1"],
        "repairs": [{"id": "dup-1", "kind": "duplicate_photo", "photo_id": str(duplicate.id),
                     "keeper_photo_id": str(keeper.id), "md5": "dup-md5"}],
    })
    with pytest.raises(ValueError, match="重复照片分组已经变化，请重新体检"):
        actions._execute_album_cleanup(session, owner, plan)


def test_execute_album_cleanup_rejects_an_album_that_is_no_longer_empty(db):
    session, owner, _ = db
    photo = _photo(session, owner, "a.jpg")
    album = _album(session, owner, "trip", photos=(photo,))
    plan = _plan(session, owner, "album_cleanup", {
        "selected_repair_ids": ["empty-1"],
        "repairs": [{"id": "empty-1", "kind": "empty_album", "album_id": str(album.id)}],
    })
    with pytest.raises(ValueError, match="空相册状态已经变化，请重新体检"):
        actions._execute_album_cleanup(session, owner, plan)


def test_execute_album_cleanup_rejects_an_unsupported_item(db):
    session, owner, _ = db
    plan = _plan(session, owner, "album_cleanup", {
        "selected_repair_ids": ["weird-1"],
        "repairs": [{"id": "weird-1", "kind": "rename"}],
    })
    with pytest.raises(ValueError, match="清理计划包含不支持的项目"):
        actions._execute_album_cleanup(session, owner, plan)


# ---------------------------------------------------------------------------
# execute_plan
# ---------------------------------------------------------------------------


def test_execute_plan_dispatches_to_the_album_repair_executor(db):
    session, owner, _ = db
    photo = _photo(session, owner, "a.jpg")
    album = _album(session, owner, "trip", photos=(photo,), num_photos=1)
    plan = _plan(session, owner, "album_repair", {
        "selected_repair_ids": ["count-1"],
        "repairs": [{"id": "count-1", "kind": "album_count", "album_id": str(album.id),
                     "before": 1, "after": 1}],
    })

    executed = actions.execute_plan(session, owner, plan.id)

    assert executed.status == "executed"
    assert executed.result["applied_repair_count"] == 1


def test_execute_plan_rejects_a_missing_plan(db):
    session, owner, _ = db
    with pytest.raises(ValueError, match="操作计划不存在"):
        actions.execute_plan(session, owner, uuid.uuid4())


def test_execute_plan_rejects_a_plan_that_is_not_proposed(db):
    session, owner, _ = db
    plan = _plan(session, owner, "album_organize", {}, status="executed")
    with pytest.raises(ValueError, match="只有待确认的计划可以执行"):
        actions.execute_plan(session, owner, plan.id)


def test_execute_plan_expires_a_plan_whose_deadline_passed(db):
    session, owner, _ = db
    plan = _plan(session, owner, "album_organize", {})
    plan.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    session.commit()
    with pytest.raises(ValueError, match="操作计划已过期，请重新生成"):
        actions.execute_plan(session, owner, plan.id)
    session.refresh(plan)
    assert plan.status == "expired"


def test_execute_plan_rejects_an_unsupported_plan_type(db):
    session, owner, _ = db
    plan = _plan(session, owner, "smart_album", {})
    with pytest.raises(ValueError, match="不支持的操作计划类型"):
        actions.execute_plan(session, owner, plan.id)


def test_execute_plan_creates_an_album_with_the_selected_photos_and_tags(db):
    session, owner, _ = db
    first = _photo(session, owner, "a.jpg")
    second = _photo(session, owner, "b.jpg")
    plan = _plan(session, owner, "album_organize", {
        "name": "旅行", "description": "一次旅行",
        "photo_ids": [str(first.id), str(second.id)],
        "cover_photo_id": str(first.id), "tags": ["旅行"],
    })

    executed = actions.execute_plan(session, owner, plan.id)

    assert executed.status == "executed"
    assert executed.result["added_photo_count"] == 2
    assert executed.result["tag_relation_count"] == 2
    album = session.query(Album).filter(Album.id == executed.result["album_id"]).one()
    assert album.name == "旅行"
    assert album.cover_id == first.id
    assert album.num_photos == 2
    assert session.query(PhotoTagRelation).filter(
        PhotoTagRelation.photo_id == first.id).count() == 1


def test_execute_plan_rejects_a_cover_outside_the_photo_range(db):
    session, owner, _ = db
    photo = _photo(session, owner, "a.jpg")
    cover = _photo(session, owner, "cover.jpg")
    plan = _plan(session, owner, "album_organize", {
        "name": "旅行", "photo_ids": [str(photo.id)],
        "cover_photo_id": str(cover.id),
    })
    with pytest.raises(ValueError, match="封面照片不在计划范围内"):
        actions.execute_plan(session, owner, plan.id)


def test_execute_plan_updates_an_existing_album(db):
    session, owner, _ = db
    photo = _photo(session, owner, "a.jpg")
    album = _album(session, owner, "旧名字", photos=(), num_photos=0)
    plan = _plan(session, owner, "album_organize", {
        "name": "新名字", "album_id": str(album.id),
        "photo_ids": [str(photo.id)], "cover_photo_id": str(photo.id),
    })

    executed = actions.execute_plan(session, owner, plan.id)

    assert executed.status == "executed"
    session.refresh(album)
    assert album.name == "新名字"
    assert album.cover_id == photo.id
    assert album.num_photos == 1
    assert executed.undo_data["album_before"]["name"] == "旧名字"


def test_execute_plan_rejects_an_album_that_cannot_be_modified(db):
    session, owner, _ = db
    photo = _photo(session, owner, "a.jpg")
    album = _album(session, owner, "trip", photos=(photo,))
    album.type = "smart"
    session.commit()
    plan = _plan(session, owner, "album_organize", {
        "name": "新名字", "album_id": str(album.id),
        "photo_ids": [str(photo.id)], "cover_photo_id": str(photo.id),
    })
    with pytest.raises(ValueError, match="目标相册不存在或不可修改"):
        actions.execute_plan(session, owner, plan.id)
