"""Nightly watch 2026-11-24: ``app/service/chapter.py`` 的删除与版本冲突盲区。

2026-11-24 的后端覆盖率报告里 ``service/chapter.py`` 为 95.7%，其中
第 350-351 行（软删除章节：写入 ``status='deleted'`` 与 ``deleted_at``）、
第 333 行（日记条目按年份序列化）和第 399-400 / 427-428 行（合并 / 拆分时
来源章节版本已变化的 409 冲突）从未被执行过。

章节是用户手动维护的长期记忆，误删或并发覆盖都不可接受：删除必须是软删除，
版本冲突必须返回 409 而不是覆盖别人的修改。
"""

from __future__ import annotations

from datetime import date, timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.db.models.chapter import LifeChapter
from app.schemas.chapter import ChapterDefinition, ChapterDiaryEntry, ChapterSplit, ChapterUpdate
from app.service import chapter as chapter_service


pytestmark = [pytest.mark.smoke]


def _chapter(db, owner_id, title="2024 春天", start=date(2024, 3, 1), status="confirmed", version=1):
    row = LifeChapter(
        id=uuid4(),
        owner_id=owner_id,
        status=status,
        origin="manual",
        title=title,
        summary="一段记录",
        summary_source="user",
        diary_entries={},
        start_date=start,
        end_date=date(2024, 5, 31),
        evidence=[],
        source_ids=[],
        version=version,
    )
    db.add(row)
    db.commit()
    return row


def test_delete_soft_deletes_the_chapter(face_sqlite_session):
    owner_id = uuid4()
    row = _chapter(face_sqlite_session, owner_id)

    chapter_service.delete(face_sqlite_session, owner_id, row.id, row.version)

    face_sqlite_session.refresh(row)
    assert row.status == "deleted"
    assert row.deleted_at is not None
    assert row.version == 2


def test_delete_rejects_a_stale_version(face_sqlite_session):
    owner_id = uuid4()
    row = _chapter(face_sqlite_session, owner_id)

    with pytest.raises(HTTPException) as error:
        chapter_service.delete(face_sqlite_session, owner_id, row.id, row.version + 5)

    assert error.value.status_code == 409
    face_sqlite_session.refresh(row)
    assert row.status == "confirmed", "版本冲突时不能删除"


def test_delete_cannot_reach_an_already_deleted_chapter(face_sqlite_session):
    owner_id = uuid4()
    row = _chapter(face_sqlite_session, owner_id, status="deleted")

    with pytest.raises(HTTPException) as error:
        chapter_service.delete(face_sqlite_session, owner_id, row.id, row.version)

    assert error.value.status_code == 404


def test_delete_cannot_reach_another_owners_chapter(face_sqlite_session):
    row = _chapter(face_sqlite_session, uuid4())

    with pytest.raises(HTTPException) as error:
        chapter_service.delete(face_sqlite_session, uuid4(), row.id, row.version)

    assert error.value.status_code == 404


def test_update_serializes_the_diary_entries(face_sqlite_session):
    owner_id = uuid4()
    row = _chapter(face_sqlite_session, owner_id)
    data = ChapterUpdate(
        title="2024 春天",
        summary="一段记录",
        start_date=date(2024, 3, 1),
        end_date=date(2024, 5, 31),
        version=row.version,
        diary_entries={
            "2024": ChapterDiaryEntry(title="三月", body="去了公园", source="user"),
        },
    )

    chapter_service.update(face_sqlite_session, owner_id, row.id, data)

    face_sqlite_session.refresh(row)
    assert "2024" in row.diary_entries
    assert row.diary_entries["2024"]["title"] == "三月"
    assert row.diary_entries["2024"]["source"] == "user"


def test_split_rejects_a_chapter_whose_version_changed(face_sqlite_session):
    owner_id = uuid4()
    row = _chapter(face_sqlite_session, owner_id)
    data = ChapterSplit(
        first_title="三月",
        second_title="四月",
        split_date=date(2024, 4, 1),
        version=row.version,
    )
    # 先把版本号推高，模拟另一个客户端已经改过这一章
    face_sqlite_session.query(LifeChapter).filter(LifeChapter.id == row.id).update({"version": 7})
    face_sqlite_session.commit()

    with pytest.raises(HTTPException) as error:
        chapter_service.split(face_sqlite_session, owner_id, row.id, data)

    assert error.value.status_code == 409


def test_split_rejects_a_date_outside_the_chapter(face_sqlite_session):
    owner_id = uuid4()
    row = _chapter(face_sqlite_session, owner_id)
    data = ChapterSplit(
        first_title="三月",
        second_title="四月",
        split_date=row.start_date,
        version=row.version,
    )

    with pytest.raises(HTTPException) as error:
        chapter_service.split(face_sqlite_session, owner_id, row.id, data)

    assert error.value.status_code == 400


def test_create_persists_a_new_chapter(face_sqlite_session):
    owner_id = uuid4()
    data = ChapterDefinition(title="2024 夏天", start_date=date(2024, 6, 1), end_date=date(2024, 8, 31))

    row = chapter_service.create(face_sqlite_session, owner_id, data)

    assert row.status == "confirmed"
    assert row.title == "2024 夏天"
    assert row.start_date == date(2024, 6, 1)


def test_update_rejects_a_stale_version(face_sqlite_session):
    owner_id = uuid4()
    row = _chapter(face_sqlite_session, owner_id)
    data = ChapterUpdate(title="改过", start_date=date(2024, 3, 1), version=row.version + 3)

    with pytest.raises(HTTPException) as error:
        chapter_service.update(face_sqlite_session, owner_id, row.id, data)

    assert error.value.status_code == 409
