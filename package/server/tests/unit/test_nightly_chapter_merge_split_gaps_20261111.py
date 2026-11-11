"""Nightly watch 2026-11-11: ``app/service/chapter.py`` merge / split / transition gaps.

The 2026-11-11 coverage snapshot showed ``app/service/chapter.py`` at 93.4%
with 23 missed statements. The uncovered lines are the *guard rails* around
merging, splitting and transitioning life chapters:

* ``merge``      - duplicated chapter ids, non-mergeable status, a range that
                   does not cover every source chapter, two conflicting diary
                   entries for the same year whose combined body is too long,
                   and the optimistic-locking 409 when a source row changed;
* ``split``      - a split date outside the chapter range, and a chapter whose
                   status cannot be split;
* ``transition`` - an unknown action, and an action that does not apply to the
                   current status;
* ``year_links`` - chapters whose photo falls into the requested year.

Every test exercises already-implemented behaviour; no production code changes.
"""

from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models.chapter import LifeChapter
from app.db.models.photo import FileType, Photo
from app.db.models.user import User
from app.schemas.chapter import ChapterMerge, ChapterSplit
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
    db.add(User(id=value, username="nightly-chapter-owner", hashed_password="x"))
    db.commit()
    return value


def _chapter(db, owner_id, *, title="2024 春天", start=date(2024, 3, 1), end=date(2024, 5, 31),
             status="confirmed", version=1, diary_entries=None, is_hidden=False):
    row = LifeChapter(
        owner_id=owner_id, status=status, origin="manual", title=title,
        start_date=start, end_date=end, version=version,
        diary_entries=diary_entries or {}, is_hidden=is_hidden, evidence=[],
        source_ids=[], confirmed_at=None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _photo(db, owner_id, when: date):
    from datetime import datetime
    photo = Photo(
        id=uuid4(), owner_id=owner_id, filename="p.jpg", file_path="p.jpg",
        file_type=FileType.image, photo_time=datetime(when.year, when.month, when.day, 12, 0, 0),
        upload_time=datetime(when.year, when.month, when.day, 12, 0, 0),
    )
    db.add(photo)
    db.commit()
    db.refresh(photo)
    return photo


def _merge_payload(first, second, **overrides):
    payload = {
        "title": "合并章节",
        "chapter_ids": [first.id, second.id],
        "versions": {first.id: first.version, second.id: second.version},
        "start_date": min(first.start_date, second.start_date),
        "end_date": max(first.end_date, second.end_date),
    }
    payload.update(overrides)
    return ChapterMerge(**payload)


def test_merge_rejects_duplicated_chapter_ids(db, owner_id):
    """同一个章节被选中两次 → 400。"""
    row = _chapter(db, owner_id)
    payload = _merge_payload(row, row, chapter_ids=[row.id, row.id])
    with pytest.raises(HTTPException) as exc:
        chapter_service.merge(db, owner_id, payload)
    assert exc.value.status_code == 400
    assert "重复" in exc.value.detail


def test_merge_rejects_chapters_that_are_not_mergeable(db, owner_id):
    """已删除/已忽略的章节不能参与合并 → 400。"""
    first = _chapter(db, owner_id)
    second = _chapter(db, owner_id, status="ignored")
    with pytest.raises(HTTPException) as exc:
        chapter_service.merge(db, owner_id, _merge_payload(first, second))
    assert exc.value.status_code == 400
    assert "只能合并" in exc.value.detail


def test_merge_rejects_a_range_that_does_not_cover_every_source(db, owner_id):
    """合并范围必须覆盖全部来源章节 → 400。"""
    first = _chapter(db, owner_id, start=date(2024, 3, 1), end=date(2024, 5, 31))
    second = _chapter(db, owner_id, start=date(2024, 6, 1), end=date(2024, 8, 31))
    payload = _merge_payload(first, second, start_date=date(2024, 3, 1), end_date=date(2024, 5, 31))
    with pytest.raises(HTTPException) as exc:
        chapter_service.merge(db, owner_id, payload)
    assert exc.value.status_code == 400
    assert "覆盖全部来源章节" in exc.value.detail


def test_merge_rejects_conflicting_diary_entries_that_exceed_the_limit(db, owner_id):
    """同一年两段日记合并后超过 1000 字 → 400。"""
    first = _chapter(db, owner_id, diary_entries={"2024": {"title": "a", "body": "x" * 600, "source": "user",
                                                          "source_photo_ids": [], "source_memory_ids": []}})
    second = _chapter(db, owner_id, start=date(2024, 6, 1), end=date(2024, 8, 31),
                      diary_entries={"2024": {"title": "b", "body": "y" * 600, "source": "user",
                                               "source_photo_ids": [], "source_memory_ids": []}})
    with pytest.raises(HTTPException) as exc:
        chapter_service.merge(db, owner_id, _merge_payload(first, second))
    assert exc.value.status_code == 400
    assert "超过1000字" in exc.value.detail


def test_merge_joins_diary_entries_and_supersedes_the_sources(db, owner_id):
    """两个章节合并：日记按年份拼接，来源章节标记为 superseded。"""
    first = _chapter(db, owner_id, diary_entries={"2024": {"title": "春", "body": "春天", "source": "user",
                                                          "source_photo_ids": [], "source_memory_ids": []}})
    second = _chapter(db, owner_id, start=date(2024, 6, 1), end=date(2024, 8, 31),
                      diary_entries={"2024": {"title": "夏", "body": "夏天", "source": "ai",
                                               "source_photo_ids": [], "source_memory_ids": []}})
    merged = chapter_service.merge(db, owner_id, _merge_payload(first, second))

    assert merged.status == "confirmed"
    assert merged.diary_entries["2024"]["body"] == "春天\n\n夏天"
    # 只有两段都是 AI 才算 AI 来源
    assert merged.diary_entries["2024"]["source"] == "user"
    assert merged.diary_entries["2024"]["title"] == "春"

    for source in (first, second):
        db.refresh(source)
        assert source.status == "superseded"
        assert source.version == 2


def test_merge_reports_a_conflict_when_a_source_row_changed(db, owner_id):
    """乐观锁失败（来源章节已被改动）→ 409。"""
    first = _chapter(db, owner_id)
    second = _chapter(db, owner_id, start=date(2024, 6, 1), end=date(2024, 8, 31))
    payload = _merge_payload(first, second)
    # 合并前把来源章节的版本改掉，使 update 的版本条件不再命中
    db.query(LifeChapter).filter(LifeChapter.id == second.id).update({"version": 9}, synchronize_session=False)
    db.commit()

    with pytest.raises(HTTPException) as exc:
        chapter_service.merge(db, owner_id, payload)
    assert exc.value.status_code == 409
    assert "刷新后重试" in exc.value.detail


def test_split_rejects_a_date_outside_the_chapter_range(db, owner_id):
    """拆分日期必须落在章节范围内 → 400。"""
    row = _chapter(db, owner_id, start=date(2024, 3, 1), end=date(2024, 5, 31))
    payload = ChapterSplit(split_date=date(2024, 2, 20), first_title="上", second_title="下", version=row.version)
    with pytest.raises(HTTPException) as exc:
        chapter_service.split(db, owner_id, row.id, payload)
    assert exc.value.status_code == 400
    assert "拆分日期必须在章节范围内" in exc.value.detail


def test_split_rejects_a_chapter_that_cannot_be_split(db, owner_id):
    """已被忽略的章节不能拆分 → 400。"""
    row = _chapter(db, owner_id, status="ignored")
    payload = ChapterSplit(split_date=date(2024, 4, 10), first_title="上", second_title="下", version=row.version)
    with pytest.raises(HTTPException) as exc:
        chapter_service.split(db, owner_id, row.id, payload)
    assert exc.value.status_code == 400
    assert "不能拆分" in exc.value.detail


def test_split_creates_two_chapters_and_supersedes_the_source(db, owner_id):
    """正常拆分：生成上下两段，来源章节标记为 superseded。"""
    row = _chapter(db, owner_id, start=date(2024, 3, 1), end=date(2024, 5, 31))
    payload = ChapterSplit(split_date=date(2024, 4, 10), first_title="上", second_title="下", version=row.version)
    rows = chapter_service.split(db, owner_id, row.id, payload)

    assert [item.title for item in rows] == ["上", "下"]
    assert rows[0].end_date == date(2024, 4, 9)
    assert rows[1].start_date == date(2024, 4, 10)
    db.refresh(row)
    assert row.status == "superseded"


def test_transition_rejects_an_unknown_action(db, owner_id):
    """未知的状态流转动作 → 400。"""
    row = _chapter(db, owner_id)
    with pytest.raises(HTTPException) as exc:
        chapter_service.transition(db, owner_id, row.id, "explode", row.version)
    assert exc.value.status_code == 400
    assert "当前状态不能执行此操作" in exc.value.detail


def test_transition_rejects_an_action_that_does_not_match_the_status(db, owner_id):
    """只有 candidate 能 confirm；confirmed 不能再次 confirm。"""
    row = _chapter(db, owner_id, status="candidate")
    with pytest.raises(HTTPException) as exc:
        chapter_service.transition(db, owner_id, row.id, "hide", row.version)
    assert exc.value.status_code == 400

    updated = chapter_service.transition(db, owner_id, row.id, "confirm", row.version)
    assert updated.status == "confirmed"
    assert updated.confirmed_at is not None

    with pytest.raises(HTTPException) as exc:
        chapter_service.transition(db, owner_id, updated.id, "confirm", updated.version)
    assert exc.value.status_code == 400


def test_transition_hides_and_unhides_a_confirmed_chapter(db, owner_id):
    """hide / unhide 在 confirmed 章节上来回切换。"""
    row = _chapter(db, owner_id)
    hidden = chapter_service.transition(db, owner_id, row.id, "hide", row.version)
    assert hidden.is_hidden is True
    shown = chapter_service.transition(db, owner_id, row.id, "unhide", hidden.version)
    assert shown.is_hidden is False


def test_year_links_lists_confirmed_chapters_with_photos_in_that_year(db, owner_id):
    """年份导航：只列出该年有照片的正式章节。"""
    _photo(db, owner_id, date(2024, 4, 2))
    with_photo = _chapter(db, owner_id, title="有照片", start=date(2024, 3, 1), end=date(2024, 5, 31))
    _chapter(db, owner_id, title="无照片", start=date(2023, 1, 1), end=date(2023, 12, 31))

    links = chapter_service.year_links(db, owner_id, [2024, 2023])
    assert [item["title"] for item in links["2024"]] == [with_photo.title]
    assert links["2023"] == []
    assert chapter_service.year_links(db, owner_id, []) == {}
