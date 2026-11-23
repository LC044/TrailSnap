"""Nightly watch 2026-11-22: ``app/service/chapter.py``::_cover 盲区。

``_cover`` 决定一个「人生章节」在列表/详情页上显示哪张照片作为封面。
它有三级兜底：

1. 用户显式指定的封面仍然有效（在章节时间区间内、未删除）时直接采用；
2. 否则自动挑选：先排除截图，优先相机原片，再取章节时间中点之后最早的一张；
3. 中点之后没有时取最晚的一张；连非截图都没有时，才退回到区间内的任意一张。

这段逻辑一旦漂移，章节封面会突然变成截图或跨章节的照片，因此本文件逐级锁定行为：

- 没有照片时返回 None（edge）
- 显式封面有效时直接采用（happy）
- 显式封面指向已删除照片时回退到自动挑选（edge）
- 自动挑选跳过截图并优先相机原片（happy）
- 只有截图时退回到区间内的任意一张（edge）
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models.chapter import LifeChapter
from app.db.models.photo import FileType, ImageType, Photo
from app.db.models.user import User
from app.service import chapter as chapter_service


pytestmark = [pytest.mark.smoke, pytest.mark.module_album]


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def owner_id(db):
    value = uuid4()
    db.add(User(id=value, username="nightly-chapter-cover-owner", hashed_password="x"))
    db.commit()
    return value


@pytest.fixture()
def chapter(db, owner_id):
    row = LifeChapter(
        owner_id=owner_id, status="confirmed", origin="manual", title="2024 春天",
        start_date=date(2024, 3, 1), end_date=date(2024, 5, 31), version=1,
        diary_entries={}, is_hidden=False, evidence=[], source_ids=[],
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _photo(db, owner_id, *, at, image_type=None, deleted=False, name="cover.jpg"):
    row = Photo(
        id=uuid4(), owner_id=owner_id, filename=name, file_path=f"/isolated/{name}",
        file_type=FileType.image, size=1024, photo_time=at, image_type=image_type,
        is_deleted=deleted,
    )
    db.add(row)
    db.commit()
    return row


def test_cover_is_none_when_the_chapter_has_no_photo(db, owner_id, chapter):
    assert chapter_service._cover(db, chapter) is None


def test_cover_prefers_the_explicit_cover_when_it_is_still_valid(db, owner_id, chapter):
    explicit = _photo(db, owner_id, at=datetime(2024, 3, 2, 10, 0), image_type=ImageType.OTHER)
    other = _photo(db, owner_id, at=datetime(2024, 4, 2, 10, 0), image_type=ImageType.CAMERA)
    chapter.cover_photo_id = explicit.id
    db.commit()

    assert chapter_service._cover(db, chapter) == str(explicit.id)
    assert str(other.id) != chapter_service._cover(db, chapter)


def test_cover_falls_back_when_the_explicit_cover_was_deleted(db, owner_id, chapter):
    deleted = _photo(db, owner_id, at=datetime(2024, 3, 2, 10, 0), image_type=ImageType.CAMERA,
                     deleted=True, name="deleted.jpg")
    keeper = _photo(db, owner_id, at=datetime(2024, 3, 3, 10, 0), image_type=ImageType.CAMERA,
                    name="keeper.jpg")
    chapter.cover_photo_id = deleted.id
    db.commit()

    assert chapter_service._cover(db, chapter) == str(keeper.id)


def test_cover_skips_screenshots_and_prefers_camera_photos(db, owner_id, chapter):
    shot = _photo(db, owner_id, at=datetime(2024, 4, 20, 9, 0), image_type=ImageType.SCREENSHOT,
                  name="shot.png")
    camera = _photo(db, owner_id, at=datetime(2024, 4, 21, 9, 0), image_type=ImageType.CAMERA,
                    name="camera.jpg")

    assert chapter_service._cover(db, chapter) == str(camera.id)
    assert str(shot.id) != chapter_service._cover(db, chapter)


def test_cover_falls_back_to_any_photo_when_only_screenshots_exist(db, owner_id, chapter):
    shot = _photo(db, owner_id, at=datetime(2024, 4, 20, 9, 0), image_type=ImageType.SCREENSHOT,
                  name="only-shot.png")

    assert chapter_service._cover(db, chapter) == str(shot.id)


def test_cover_ignores_photos_outside_the_chapter_range(db, owner_id, chapter):
    outside = _photo(db, owner_id, at=datetime(2024, 8, 1, 9, 0), image_type=ImageType.CAMERA,
                      name="outside.jpg")
    inside = _photo(db, owner_id, at=datetime(2024, 3, 5, 9, 0), image_type=ImageType.CAMERA,
                    name="inside.jpg")

    assert chapter_service._cover(db, chapter) == str(inside.id)
    assert str(outside.id) != chapter_service._cover(db, chapter)
