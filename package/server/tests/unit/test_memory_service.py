from datetime import datetime, timedelta
from uuid import uuid4

import pytest

from app.db.models.memory import MemoryStatus
from app.db.models.photo import FileType, ImageType, Photo
from app.db.models.photo_metadata import PhotoMetadata
from app.db.models.user import User
from app.schemas.memory import MemoryCreate, MemorySplitPart, MemorySplitRequest
from app.service import memory as memory_service


pytestmark = [pytest.mark.smoke, pytest.mark.module_album]


def _user(db, name="memory-owner"):
    user = User(id=uuid4(), username=name, hashed_password="x")
    db.add(user)
    db.commit()
    return user


def _photo(db, owner_id, captured_at, index, city="杭州"):
    photo = Photo(
        id=uuid4(), owner_id=owner_id, filename=f"memory-{index}.jpg",
        file_path=f"/photos/memory-{index}.jpg", file_type=FileType.image,
        photo_time=captured_at, upload_time=captured_at, size=100,
        width=1200, height=800, is_deleted=False,
    )
    db.add(photo)
    db.flush()
    db.add(PhotoMetadata(photo_id=photo.id, city=city, province="浙江省"))
    return photo


def test_manual_memory_create_is_confirmed_and_owner_scoped(face_sqlite_session):
    db = face_sqlite_session
    owner = _user(db)
    stranger = _user(db, "memory-stranger")
    photos = [_photo(db, owner.id, datetime(2026, 10, 1, 9) + timedelta(hours=i), i) for i in range(3)]
    db.commit()

    row = memory_service.create(db, owner.id, MemoryCreate(
        title="第一次去杭州", story="沿着湖边慢慢走。",
        photo_ids=[photo.id for photo in photos], cover_photo_id=photos[1].id,
        place_names=["杭州", "西湖"],
    ))

    assert row.status == MemoryStatus.CONFIRMED
    assert row.title_source == "user"
    assert row.cover_photo_id == photos[1].id
    assert [item.name for item in row.places] == ["杭州", "西湖"]
    assert len(row.photo_links) == 3
    assert memory_service.get_owned(db, row.id, stranger.id) is None


def test_discovery_groups_continuous_photos_and_does_not_duplicate(face_sqlite_session):
    db = face_sqlite_session
    owner = _user(db)
    start = datetime(2026, 10, 1, 9)
    photos = [_photo(db, owner.id, start + timedelta(minutes=35 * i), i) for i in range(6)]
    _photo(db, owner.id, start + timedelta(days=3), 99, city="上海")
    db.commit()

    created = memory_service.discover(db, owner.id, min_photos=5)
    repeated = memory_service.discover(db, owner.id, min_photos=5)

    assert len(created) == 1
    assert repeated == []
    candidate = created[0]
    assert candidate.status == MemoryStatus.CANDIDATE
    assert len(candidate.photo_links) == len(photos)
    assert candidate.places[0].name == "杭州"
    assert {item.evidence_type for item in candidate.evidence} >= {"time", "place"}


def test_discovery_requires_location_and_excludes_screenshots(face_sqlite_session):
    db = face_sqlite_session
    owner = _user(db)
    start = datetime(2026, 11, 1, 9)
    located = [_photo(db, owner.id, start + timedelta(minutes=20 * i), i) for i in range(5)]
    for index in range(5, 11):
        _photo(db, owner.id, start + timedelta(minutes=20 * index), index, city=None)
    screenshot = _photo(db, owner.id, start + timedelta(minutes=10), 99)
    screenshot.image_type = ImageType.SCREENSHOT
    db.commit()

    created = memory_service.discover(db, owner.id, min_photos=5)

    assert len(created) == 1
    ids = {link.photo_id for link in created[0].photo_links}
    assert ids == {photo.id for photo in located}


def test_ai_story_normalization_removes_reasoning_and_limits_length():
    raw = "<think>内部推理不能展示</think>\n# 一段记忆\n" + ("这是可核实的记忆片段。" * 80)
    story = memory_service._normalize_ai_story(raw)
    assert "内部推理" not in story
    assert not story.startswith("#")
    assert 180 <= len(story) <= 420
    assert story.endswith("。")


@pytest.mark.asyncio
async def test_story_generation_rejects_duplicate_in_progress(face_sqlite_session):
    db = face_sqlite_session
    owner = _user(db)
    photo = _photo(db, owner.id, datetime(2026, 12, 1, 10), 1)
    db.commit()
    row = memory_service.create(db, owner.id, MemoryCreate(title="测试记忆", photo_ids=[photo.id]))
    row.story_generation_status = "generating"
    row.story_generation_started_at = datetime.now()
    db.commit()

    with pytest.raises(Exception) as exc_info:
        await memory_service.generate_story(db, row, owner.id, tone="温暖")

    assert getattr(exc_info.value, "status_code", None) == 409
    data = memory_service.serialize(db, row)
    assert data["story_generation_status"] == "generating"


def test_ignore_then_restore_preserves_candidate_fingerprint(face_sqlite_session):
    db = face_sqlite_session
    owner = _user(db)
    start = datetime(2026, 8, 1, 10)
    for index in range(5):
        _photo(db, owner.id, start + timedelta(minutes=index * 20), index)
    db.commit()
    row = memory_service.discover(db, owner.id, min_photos=5)[0]
    fingerprint = row.candidate_fingerprint

    memory_service.change_status(db, row, MemoryStatus.IGNORED)
    assert memory_service.discover(db, owner.id, min_photos=5) == []
    memory_service.change_status(db, row, MemoryStatus.CANDIDATE)

    assert row.candidate_fingerprint == fingerprint
    assert row.status == MemoryStatus.CANDIDATE


def test_merge_and_split_keep_sources_for_audit(face_sqlite_session):
    db = face_sqlite_session
    owner = _user(db)
    photos = [_photo(db, owner.id, datetime(2026, 7, 1, 8) + timedelta(hours=i), i) for i in range(4)]
    db.commit()
    first = memory_service.create(db, owner.id, MemoryCreate(title="上午", photo_ids=[photos[0].id, photos[1].id]))
    second = memory_service.create(db, owner.id, MemoryCreate(title="下午", photo_ids=[photos[2].id, photos[3].id]))

    merged = memory_service.merge(db, owner.id, [first.id, second.id], title="完整的一天", story=None, cover_photo_id=None)

    assert merged.status == MemoryStatus.CONFIRMED
    assert len(merged.photo_links) == 4
    assert memory_service.get_owned(db, first.id, owner.id).status == MemoryStatus.SUPERSEDED
    assert memory_service.get_owned(db, second.id, owner.id).status == MemoryStatus.SUPERSEDED

    split = memory_service.split(db, owner.id, merged.id, MemorySplitRequest(parts=[
        MemorySplitPart(title="第一段", photo_ids=[photos[0].id, photos[1].id]),
        MemorySplitPart(title="第二段", photo_ids=[photos[2].id, photos[3].id]),
    ]))

    assert [len(item.photo_links) for item in split] == [2, 2]
    assert all(item.status == MemoryStatus.CONFIRMED for item in split)
    assert memory_service.get_owned(db, merged.id, owner.id).status == MemoryStatus.SUPERSEDED
