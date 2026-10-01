"""Database-backed contracts for the server refactor."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest

from app.api.search import get_search_suggestions
from app.crud.dashboard import get_dashboard_stats
from app.crud.photo_paths import under_browse_folder, under_directory
from app.db.models.photo import FileType, Photo
from app.db.models.tag import PhotoTag, PhotoTagRelation
from app.db.models.task import TaskType
from app.db.models.user import User
from app.service.tasks.photo_generator import generate_photo_tasks

pytestmark = [pytest.mark.smoke]


def _user(db, name):
    owner = User(id=uuid4(), username=name, hashed_password="x")
    db.add(owner)
    db.flush()
    return owner


def _photo(db, owner, name, *, deleted=False):
    photo = Photo(
        id=uuid4(), owner_id=owner.id, filename=name,
        file_path=f"/photos/{name}", file_type=FileType.image,
        photo_time=datetime(2024, 1, 10), is_deleted=deleted,
    )
    db.add(photo)
    db.flush()
    return photo


@pytest.mark.asyncio
async def test_tag_suggestions_do_not_cross_join_scenes(face_sqlite_session):
    db = face_sqlite_session
    owner = _user(db, "tag-owner")
    other = _user(db, "tag-other")
    db.add_all([
        PhotoTag(tag_name="hiking", owner_id=owner.id),
        PhotoTag(tag_name="hiking-public", owner_id=None),
        PhotoTag(tag_name="hiking-private", owner_id=other.id),
    ])
    db.commit()

    result = await get_search_suggestions(q="hiking", db=db, user=owner)
    tags = {item.value for item in result.data if item.type == "tag"}
    assert tags == {"hiking", "hiking-public"}


def test_dashboard_tag_counts_are_owner_scoped(face_sqlite_session):
    db = face_sqlite_session
    owner = _user(db, "dashboard-owner")
    other = _user(db, "dashboard-other")
    tag = PhotoTag(tag_name="风景", owner_id=owner.id)
    db.add(tag)
    db.flush()
    visible = _photo(db, owner, "visible.jpg")
    removed = _photo(db, owner, "removed.jpg", deleted=True)
    foreign = _photo(db, other, "foreign.jpg")
    db.add_all([
        PhotoTagRelation(photo_id=visible.id, tag_id=tag.id),
        PhotoTagRelation(photo_id=removed.id, tag_id=tag.id),
        PhotoTagRelation(photo_id=foreign.id, tag_id=tag.id),
    ])
    db.commit()

    with patch("app.crud.dashboard.get_identities_with_details", return_value=[]):
        result = get_dashboard_stats(db, owner.id)
    assert result.content.scenery_count == 1
    assert result.content.food_count == 0


def test_photo_task_generator_scopes_owner_and_budget(face_sqlite_session):
    db = face_sqlite_session
    owner = _user(db, "generator-owner")
    other = _user(db, "generator-other")
    for index in range(3):
        _photo(db, owner, f"mine-{index}.jpg")
    _photo(db, other, "not-mine.jpg")
    db.commit()

    batches = []
    worker = SimpleNamespace(add_tasks=lambda _db, entries: batches.extend(entries))
    task = SimpleNamespace(owner_id=owner.id, payload={"force": False})
    generated = generate_photo_tasks(
        db, worker, task, task_type=TaskType.OCR,
        status_key="ocr", priority=1, budget=2, batch_size=1,
    )
    assert generated == 2
    assert len(batches) == 2
    assert all(entry["owner_id"] == owner.id for entry in batches)


def test_folder_predicates_escape_wildcards(face_sqlite_session):
    db = face_sqlite_session
    owner = _user(db, "folder-owner")
    chosen = _photo(db, owner, "trip_2024/one.jpg")
    _photo(db, owner, "tripX2024/two.jpg")
    db.commit()

    rows = db.query(Photo.id).filter(under_browse_folder("trip_2024")).all()
    assert rows == [(chosen.id,)]
    rows = db.query(Photo.id).filter(under_directory("/photos/trip_2024")).all()
    assert rows == [(chosen.id,)]


@pytest.mark.parametrize("force, expected", [(False, 1), (True, 2)])
def test_generator_skips_deleted_video_and_processed(face_sqlite_session, force, expected):
    db = face_sqlite_session
    owner = _user(db, "generator-eligibility")
    pending = _photo(db, owner, "pending.jpg")
    done = _photo(db, owner, "done.jpg")
    done.processed_tasks = {"face": True}
    _photo(db, owner, "deleted.jpg", deleted=True)
    video = _photo(db, owner, "clip.mp4")
    video.file_type = FileType.video
    db.commit()
    entries = []
    task = SimpleNamespace(owner_id=owner.id, payload={"force": force})
    generated = generate_photo_tasks(
        db, SimpleNamespace(add_tasks=lambda _db, batch: entries.extend(batch)), task,
        task_type=TaskType.RECOGNIZE_FACE, status_key="face", priority=2, batch_size=1,
    )
    assert generated == expected
    assert {row["payload"]["photo_id"] for row in entries} == (
        {str(pending.id), str(done.id)} if force else {str(pending.id)}
    )
    assert all(row["payload"]["force"] == force for row in entries)


def test_generator_cursor_survives_deletion_and_commit(face_sqlite_session):
    db = face_sqlite_session
    owner = _user(db, "generator-cursor")
    photos = [_photo(db, owner, f"cursor-{index}.jpg") for index in range(4)]
    db.commit()
    expected = {str(photo.id) for photo in photos}
    entries = []

    def enqueue(_db, batch):
        entries.extend(batch)
        # A concurrent cleanup removes already-visited rows between batches.
        for row in batch:
            db.query(Photo).filter(Photo.id == row["payload"]["photo_id"]).update(
                {Photo.is_deleted: True}, synchronize_session=False,
            )
        db.commit()

    count = generate_photo_tasks(
        db, SimpleNamespace(add_tasks=enqueue),
        SimpleNamespace(owner_id=owner.id, payload={}),
        task_type=TaskType.OCR, status_key="ocr", priority=1, batch_size=1,
    )
    assert count == 4
    assert {row["payload"]["photo_id"] for row in entries} == expected


def test_generator_zero_budget_does_not_enqueue(face_sqlite_session):
    db = face_sqlite_session
    owner = _user(db, "generator-zero")
    _photo(db, owner, "pending.jpg")
    db.commit()
    entries = []
    assert generate_photo_tasks(
        db, SimpleNamespace(add_tasks=lambda _db, batch: entries.extend(batch)),
        SimpleNamespace(owner_id=owner.id, payload={"force": True}),
        task_type=TaskType.OCR, status_key="ocr", priority=1, budget=0,
    ) == 0
    assert entries == []
