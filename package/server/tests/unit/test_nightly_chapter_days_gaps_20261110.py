"""Nightly gap coverage for app/service/chapter_days.py.

Uncovered branches reported by the nightly coverage scan:

* the daily page falls back to every photo of the day when the day only
  contains screenshots (no "ordinary" photo exists)
* the diary generation accepts a structured (block list) model response
* the diary generation rejects an empty / oversized model answer with 502
* the diary generation detects that the photos of the day changed while the
  model was running and answers 409
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.db.models.photo import FileType, ImageType, Photo
from app.db.models.user import User
from app.schemas.chapter import ChapterDefinition
from app.service import chapter, chapter_diary, chapter_days

pytestmark = [pytest.mark.smoke, pytest.mark.module_album]


def _setup(db):
    owner = User(id=uuid4(), username="nightly-chapter-days-owner", hashed_password="x")
    db.add(owner)
    db.flush()
    photo = Photo(
        id=uuid4(),
        owner_id=owner.id,
        filename="screenshot.png",
        file_path="/daily/screenshot.png",
        file_type=FileType.image,
        photo_time=datetime(2024, 3, 1, 10, 0),
        upload_time=datetime(2024, 3, 1, 10, 0),
        image_type=ImageType.SCREENSHOT,
        is_deleted=False,
    )
    db.add(photo)
    db.commit()
    row = chapter.create(
        db,
        owner.id,
        ChapterDefinition(title="只有截图的一天", start_date=date(2024, 3, 1), end_date=date(2024, 3, 1)),
    )
    return owner, row


def test_daily_page_falls_back_to_screenshots_when_no_ordinary_photo(face_sqlite_session, monkeypatch):
    db = face_sqlite_session
    owner, row = _setup(db)
    monkeypatch.setattr(chapter_days, "get_day_highlights", lambda *args, **kwargs: ([], None))

    result = chapter_days.page(db, owner.id, date(2024, 3, 1), 1)

    assert [item["filename"] for item in result["photos"]] == ["screenshot.png"]
    assert result["photo_count"] == 1


def test_daily_generation_accepts_structured_block_response(face_sqlite_session, monkeypatch):
    db = face_sqlite_session
    owner, row = _setup(db)

    class Model:
        async def ainvoke(self, messages):
            return SimpleNamespace(
                content=[
                    {"type": "text", "text": "这一天只有一张截图，"},
                    {"type": "text", "text": "安静地停在这里。"},
                ]
            )

    monkeypatch.setattr(chapter_diary, "configured_model", lambda *args: Model())
    result = asyncio.run(chapter_days.generate(db, owner.id, row.id, date(2024, 3, 1)))

    assert result["source"] == "ai"
    assert "安静地停在这里" in result["caption"]


def test_daily_generation_rejects_empty_model_answer(face_sqlite_session, monkeypatch):
    db = face_sqlite_session
    owner, row = _setup(db)

    class Model:
        async def ainvoke(self, messages):
            return SimpleNamespace(content="   ")

    monkeypatch.setattr(chapter_diary, "configured_model", lambda *args: Model())
    with pytest.raises(HTTPException) as exc:
        asyncio.run(chapter_days.generate(db, owner.id, row.id, date(2024, 3, 1)))

    assert exc.value.status_code == 502


def test_daily_generation_detects_photos_changed_while_running(face_sqlite_session, monkeypatch):
    db = face_sqlite_session
    owner, row = _setup(db)

    class Model:
        async def ainvoke(self, messages):
            return SimpleNamespace(content="这一天的一天。")

    monkeypatch.setattr(chapter_diary, "configured_model", lambda *args: Model())
    monkeypatch.setattr(
        chapter_days,
        "page",
        lambda *args, **kwargs: {
            "day": "2024-03-01",
            "photo_count": 1,
            "photos": [{"id": str(uuid4())}],
            "caption": "",
            "source": None,
            "needs_generation": True,
        },
    )
    with pytest.raises(HTTPException) as exc:
        asyncio.run(chapter_days.generate(db, owner.id, row.id, date(2024, 3, 1)))

    assert exc.value.status_code == 409
