import asyncio
from datetime import date, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.crud import moment
from app.db.models.image_description import ImageDescription
from app.db.models.photo import FileType, Photo
from app.db.models.tag import PhotoTag, PhotoTagRelation
from app.db.models.user import User
from app.schemas.chapter import ChapterDefinition
from app.service import chapter, chapter_days, chapter_diary

pytestmark = [pytest.mark.smoke, pytest.mark.module_album]


def setup_diary(db):
    owner = User(id=uuid4(), username="daily-owner", hashed_password="x")
    stranger = User(id=uuid4(), username="daily-stranger", hashed_password="x")
    db.add_all([owner, stranger])
    db.flush()
    for index, (user, when) in enumerate([
        (owner, datetime(2024, 1, 1, 23, 59)), (owner, datetime(2024, 1, 2)),
        (owner, datetime(2024, 2, 1)), (stranger, datetime(2024, 1, 2)),
    ]):
        photo = Photo(id=uuid4(), owner_id=user.id, filename=f"daily-{index}.jpg",
                      file_path=f"/daily/{index}.jpg", file_type=FileType.image,
                      photo_time=when, upload_time=when, is_deleted=False)
        db.add(photo)
        db.flush()
        db.add(ImageDescription(photo_id=photo.id, description="湖边散步", tags=["风景"]))
        if index == 1:
            tag = PhotoTag(id=uuid4(), owner_id=owner.id, tag_name="周末", is_deleted=False)
            db.add(tag)
            db.flush()
            db.add(PhotoTagRelation(photo_id=photo.id, tag_id=tag.id, is_deleted=False))
    db.commit()
    row = chapter.create(db, owner.id, ChapterDefinition(
        title="这一段时光", start_date=date(2024, 1, 1), end_date=date(2024, 2, 1)))
    return owner, stranger, row


def test_daily_pagination_scope_and_moment_text(face_sqlite_session):
    db = face_sqlite_session
    owner, stranger, row = setup_diary(db)
    moment.upsert_caption(db, owner.id, "all", None, date(2024, 1, 2), "自己写下的文字", "manual")
    result = chapter_days.list_days(db, owner.id, row.id, 0, 1, 2024, 1)
    assert result["total"] == 2
    page = result["items"][0]
    assert page["day"] == "2024-01-02"
    assert page["photo_count"] == 1
    assert page["caption"] == "自己写下的文字"
    assert page["source"] == "manual"
    assert set(page["tags"]) == {"周末", "风景"}
    assert chapter_days.list_days(db, owner.id, row.id, 1, 1, 2024, 1)["items"][0]["day"] == "2024-01-01"
    with pytest.raises(HTTPException) as exc:
        chapter_days.list_days(db, stranger.id, row.id, 0, 6)
    assert exc.value.status_code == 404
    with pytest.raises(HTTPException):
        chapter_days.day_scope(db, owner.id, row.id, date(2023, 12, 31))
    chapter.transition(db, owner.id, row.id, "hide", row.version)
    with pytest.raises(HTTPException):
        chapter_days.list_days(db, owner.id, row.id, 0, 6)


def test_daily_generation_saved_once_and_manual_wins(face_sqlite_session, monkeypatch):
    db = face_sqlite_session
    owner, _, row = setup_diary(db)
    calls = []

    class Model:
        async def ainvoke(self, messages):
            calls.append(messages)
            return SimpleNamespace(content="湖边的散步，留在了这一天的照片里。")

    monkeypatch.setattr(chapter_diary, "configured_model", lambda *args: Model())
    first = asyncio.run(chapter_days.generate(db, owner.id, row.id, date(2024, 1, 1)))
    assert first["source"] == "ai"
    assert moment.get_caption(db, owner.id, "all", None, date(2024, 1, 1)).caption == first["caption"]
    assert asyncio.run(chapter_days.generate(db, owner.id, row.id, date(2024, 1, 1))) == first
    assert len(calls) == 1
    cached = moment.get_caption(db, owner.id, "all", None, date(2024, 1, 1))
    cached.photo_count = 5
    db.commit()
    assert chapter_days.list_days(db, owner.id, row.id, 0, 6)["items"][-1]["needs_generation"] is True
    asyncio.run(chapter_days.generate(db, owner.id, row.id, date(2024, 1, 1)))
    assert len(calls) == 2
    assert moment.get_caption(db, owner.id, "all", None, date(2024, 1, 1)).photo_count == 1

    class EditingModel:
        async def ainvoke(self, messages):
            moment.upsert_caption(db, owner.id, "all", None, date(2024, 1, 2), "我手写的日记", "manual")
            return SimpleNamespace(content="AI 的文字")

    monkeypatch.setattr(chapter_diary, "configured_model", lambda *args: EditingModel())
    assert asyncio.run(chapter_days.generate(db, owner.id, row.id, date(2024, 1, 2))) == {
        "caption": "我手写的日记", "source": "manual"}


def test_daily_generation_rechecks_visibility(face_sqlite_session, monkeypatch):
    db = face_sqlite_session
    owner, _, row = setup_diary(db)

    class Model:
        async def ainvoke(self, messages):
            chapter.transition(db, owner.id, row.id, "hide", row.version)
            return SimpleNamespace(content="这一天的文字")

    monkeypatch.setattr(chapter_diary, "configured_model", lambda *args: Model())
    with pytest.raises(HTTPException) as exc:
        asyncio.run(chapter_days.generate(db, owner.id, row.id, date(2024, 1, 1)))
    assert exc.value.status_code == 404
    assert moment.get_caption(db, owner.id, "all", None, date(2024, 1, 1)) is None
