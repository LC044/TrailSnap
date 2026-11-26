"""Nightly watch 2026-11-25: ``app/service/chapter.py`` 盲区。

2026-11-24 的后端覆盖率报告里 ``service/chapter.py`` 为 95.7%，以下分支从未执行：

- 第 171 行：章节照片在「年份中点之后」没有素材时，回退到区间内最新的一张；
- 第 184 行：区间里只有截图时，代表照片退回到不过滤截图的全量照片；
- 第 187 行：区间里有 6 张以上相机原片时，代表照片只从相机原片里挑；
- 第 333 行：更新章节时把日记条目按年份序列化进 ``diary_entries``；
- 第 351 行：删除章节把状态改成 ``deleted`` 并写入 ``deleted_at``。

这些分支决定「人生章节」的封面与代表照片选取，以及日记/删除是否落库：
封面选错会让章节看起来是空的，代表照片只挑原片会让纯截图的章节没有代表图。

这里用真实的内存 SQLite 会话逐条锁定行为。
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
from app.schemas.chapter import ChapterDiaryEntry, ChapterUpdate
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
def owner(db):
    user = User(id=uuid4(), username="nightly-chapter-gaps-owner", hashed_password="x")
    db.add(user)
    db.commit()
    return user


@pytest.fixture()
def chapter(db, owner):
    row = LifeChapter(
        owner_id=owner.id, status="confirmed", origin="manual", title="2024 春天",
        start_date=date(2024, 1, 1), end_date=date(2024, 12, 31), version=1,
        diary_entries={}, is_hidden=False, evidence=[], source_ids=[],
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _photo(db, owner, when, image_type=ImageType.CAMERA, name="p.jpg"):
    photo = Photo(
        id=uuid4(), owner_id=owner.id, filename=name, file_type=FileType.image,
        file_path=f"/photos/{name}", photo_time=when, image_type=image_type, is_deleted=False,
    )
    db.add(photo)
    db.commit()
    return photo


def test_photos_fall_back_to_the_latest_photo_before_the_midpoint(db, owner, chapter):
    _photo(db, owner, datetime(2024, 2, 1), name="early.jpg")
    latest = _photo(db, owner, datetime(2024, 3, 1), name="early-mid.jpg")

    result = chapter_service.photos(db, chapter, 0, 20, year=2024)

    assert result["total"] == 2
    assert result["featured"]["id"] == str(latest.id), "中点之后没有照片时应回退到最新一张"


def test_representative_photos_fall_back_to_screenshots(db, owner, chapter):
    for index in range(2):
        _photo(db, owner, datetime(2024, 4 + index, 1), ImageType.SCREENSHOT, f"shot-{index}.jpg")

    samples = chapter_service.representative_photos(db, chapter, 2024)

    assert len(samples) == 2, "只有截图时代表照片不能为空"


def test_representative_photos_prefer_camera_photos(db, owner, chapter):
    for index in range(7):
        _photo(db, owner, datetime(2024, 5, index + 1), ImageType.CAMERA, f"cam-{index}.jpg")
    for index in range(2):
        _photo(db, owner, datetime(2024, 6, index + 1), ImageType.SCREENSHOT, f"shot-{index}.jpg")

    samples = chapter_service.representative_photos(db, chapter, 2024)

    assert samples, "相机原片足够时必须有代表照片"
    assert all(sample.image_type == ImageType.CAMERA for sample in samples)


def test_update_persists_diary_entries(db, owner, chapter):
    version = chapter.version
    payload = ChapterUpdate(
        title="2024 春天", start_date=date(2024, 1, 1), end_date=date(2024, 12, 31),
        version=version,
        diary_entries={"2024": ChapterDiaryEntry(title="开春", body="第一张照片")},
    )

    updated = chapter_service.update(db, owner.id, chapter.id, payload)

    assert updated.version == version + 1
    assert updated.diary_entries["2024"]["title"] == "开春"
    assert updated.diary_entries["2024"]["source"] == "user"


def test_delete_marks_the_chapter_as_deleted(db, owner, chapter):
    chapter_service.delete(db, owner.id, chapter.id, chapter.version)

    db.refresh(chapter)
    assert chapter.status == "deleted"
    assert chapter.deleted_at is not None

