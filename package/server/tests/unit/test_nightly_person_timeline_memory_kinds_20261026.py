"""Nightly coverage for ``app/service/person_timeline.py`` (2026-10-26).

The 2026-10-26 backend coverage scan listed ``service/person_timeline.py`` at
86.3% with 13 missed lines.  The missed lines were the *kind classifier* of
``confirmed_memories`` (holiday / travel / memory) and the year validation of
``year_detail``.  The frontend E2E suite only exercises the single-person
timeline, so those branches never ran.

These tests use a real SQLite session so the memories are real rows.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from types import SimpleNamespace

import pytest

pytestmark = [pytest.mark.smoke]


@pytest.fixture()
def memories(face_sqlite_session):
    """Three confirmed memories, each linked to one photo."""
    from app.db.models.memory import Memory, MemoryPhoto, MemoryStatus
    from app.db.models.photo import FileType, Photo

    db = face_sqlite_session
    owner_id = uuid.uuid4()

    photos = []
    for index in range(3):
        photo = Photo(
            id=uuid.uuid4(),
            owner_id=owner_id,
            filename=f"m{index}.jpg",
            file_path=f"/photos/m{index}.jpg",
            photo_time=datetime(2024, 5, index + 1, 10, 0),
            file_type=FileType.image,
            size=100,
            width=800,
            height=600,
            duration=0.0,
        )
        db.add(photo)
        photos.append(photo)
    db.flush()

    created = []
    for index, (title, start) in enumerate(
        (
            ("春节家庭聚会", datetime(2024, 2, 10, 8, 0)),
            ("云南旅行", datetime(2024, 7, 20, 8, 0)),
            ("普通的一天", datetime(2024, 9, 1, 8, 0)),
        )
    ):
        memory = Memory(
            id=uuid.uuid4(),
            owner_id=owner_id,
            title=title,
            status=MemoryStatus.CONFIRMED,
            start_time=start,
        )
        db.add(memory)
        db.flush()
        db.add(MemoryPhoto(memory_id=memory.id, photo_id=photos[index].id))
        created.append(memory)

    db.commit()
    return SimpleNamespace(db=db, owner_id=owner_id, photos=photos, memories=created)


def test_confirmed_memories_classifies_holiday_travel_and_plain(memories):
    from app.service.person_timeline import confirmed_memories

    photo_ids = [photo.id for photo in memories.photos]
    items = confirmed_memories(memories.db, memories.owner_id, photo_ids)

    kinds = {item["title"]: item["kind"] for item in items}
    assert kinds["春节家庭聚会"] == "holiday"
    assert kinds["云南旅行"] == "travel"
    assert kinds["普通的一天"] == "memory"


def test_confirmed_memories_are_sorted_by_start_time(memories):
    from app.service.person_timeline import confirmed_memories

    photo_ids = [photo.id for photo in memories.photos]
    items = confirmed_memories(memories.db, memories.owner_id, photo_ids)

    assert [item["start_time"] for item in items] == sorted(
        (item["start_time"] for item in items), reverse=True
    )


def test_confirmed_memories_without_photos_returns_empty(memories):
    from app.service.person_timeline import confirmed_memories

    assert confirmed_memories(memories.db, memories.owner_id, []) == []


def test_year_detail_rejects_an_out_of_range_year(memories):
    from fastapi import HTTPException

    from app.service.person_timeline import year_detail

    with pytest.raises(HTTPException) as exc_info:
        year_detail(
            memories.db,
            memories.owner_id,
            memories.memories[0].id,
            memories.memories[0].id,
            1800,
            0,
            10,
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "年份无效"


def test_year_detail_accepts_a_valid_year(memories):
    from app.service.person_timeline import year_detail

    owner_id = memories.owner_id
    first = uuid.uuid4()
    second = uuid.uuid4()

    detail = year_detail(memories.db, owner_id, first, second, 2024, 0, 10)

    assert detail["year"] == 2024
    assert detail["total"] == 0
    assert detail["photos"] == []
    assert detail["next_skip"] is None
