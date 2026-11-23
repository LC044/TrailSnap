"""Nightly watch 2026-11-23 · app/api/chapter.py 的日记日程路由盲区。

本文件覆盖章节「日记日程」这一组路由：
- diary_days  列出某章节的日记天数
- day_photos  列出某一天范围内的照片
- save_day    手工保存某一天的标题文案
- _discovery_task 发现任务的对外摘要

业务逻辑分别在 app/service/chapter_days.py 与 app/crud/moment.py；
本文件只验证路由层的参数传递、事务锁与返回包装，协作者一律替换成桩函数。
"""

from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.api import chapter as chapter_api

pytestmark = [pytest.mark.smoke]


def _user():
    return SimpleNamespace(id=uuid4())


def test_diary_days_forwards_every_filter_to_the_service(face_sqlite_session, monkeypatch):
    from app.service import chapter_days

    seen = {}

    def fake_list_days(db, owner_id, chapter_id, skip, limit, year, month):
        seen.update({"owner_id": owner_id, "chapter_id": chapter_id,
                     "skip": skip, "limit": limit, "year": year, "month": month})
        return {"items": [{"day": "2024-05-01"}], "total": 1}

    monkeypatch.setattr(chapter_days, "list_days", fake_list_days)
    chapter_id = uuid4()
    user = _user()

    result = chapter_api.diary_days(chapter_id, 0, 6, 2024, 5, user, face_sqlite_session)

    assert result.code == 0
    assert result.data["total"] == 1
    assert seen["chapter_id"] == chapter_id
    assert seen["owner_id"] == user.id
    assert (seen["skip"], seen["limit"]) == (0, 6)
    assert (seen["year"], seen["month"]) == (2024, 5)


def test_diary_days_accepts_a_missing_year_and_month(face_sqlite_session, monkeypatch):
    """年 / 月都是可选过滤条件，缺省时必须原样传 None 给服务层。"""
    from app.service import chapter_days

    seen = {}

    def fake_list_days(db, owner_id, chapter_id, skip, limit, year, month):
        seen["year"] = year
        seen["month"] = month
        return {"items": [], "total": 0}

    monkeypatch.setattr(chapter_days, "list_days", fake_list_days)

    result = chapter_api.diary_days(uuid4(), 0, 6, None, None, _user(), face_sqlite_session)

    assert result.code == 0
    assert seen["year"] is None
    assert seen["month"] is None


def test_day_photos_uses_the_day_scope_and_forwards_paging(face_sqlite_session, monkeypatch):
    from app.service import chapter as service
    from app.service import chapter_days

    scoped = object()
    seen = {}

    def fake_day_scope(db, owner_id, chapter_id, day):
        seen["day"] = day
        return {"chapter": chapter_id}, scoped

    def fake_photos(db, row, skip, limit):
        seen["row"] = row
        seen["skip"] = skip
        seen["limit"] = limit
        return {"items": [{"id": "photo-1"}], "total": 1}

    monkeypatch.setattr(chapter_days, "day_scope", fake_day_scope)
    monkeypatch.setattr(service, "photos", fake_photos)
    day = date(2024, 5, 1)

    result = chapter_api.day_photos(uuid4(), day, 0, 30, _user(), face_sqlite_session)

    assert result.code == 0
    assert result.data["total"] == 1
    assert seen["day"] == day
    assert seen["row"] is scoped
    assert (seen["skip"], seen["limit"]) == (0, 30)


def test_day_photos_propagates_a_missing_chapter(face_sqlite_session, monkeypatch):
    """章节不存在时服务层抛错，路由不得吞掉它。"""
    from fastapi import HTTPException

    from app.service import chapter_days

    def fake_day_scope(db, owner_id, chapter_id, day):
        raise HTTPException(404, "章节不存在")

    monkeypatch.setattr(chapter_days, "day_scope", fake_day_scope)

    with pytest.raises(HTTPException) as failure:
        chapter_api.day_photos(uuid4(), date(2024, 5, 1), 0, 30, _user(), face_sqlite_session)
    assert failure.value.status_code == 404


def test_save_day_strips_the_caption_and_writes_a_manual_caption(face_sqlite_session, monkeypatch):
    from app.crud import moment
    from app.schemas.chapter import ChapterDayCaption
    from app.service import chapter_days

    seen = {}

    def fake_upsert_caption(db, owner_id, scope, scope_id, day, caption, source):
        seen.update({"owner_id": owner_id, "scope": scope, "scope_id": scope_id,
                     "day": day, "caption": caption, "source": source})
        return SimpleNamespace(caption=caption, source=source)

    monkeypatch.setattr(chapter_days, "day_scope", lambda db, owner_id, chapter_id, day: (None, None))
    monkeypatch.setattr(moment, "upsert_caption", fake_upsert_caption)
    monkeypatch.setattr(face_sqlite_session, "query", _fake_user_query(face_sqlite_session))
    day = date(2024, 5, 1)
    payload = ChapterDayCaption(caption="  一日一帧  ", source="manual")

    result = chapter_api.save_day(uuid4(), day, payload, _user(), face_sqlite_session)

    assert result.code == 0
    assert result.data["caption"] == "一日一帧"
    assert result.data["source"] == "manual"
    assert seen["scope"] == "all"
    assert seen["scope_id"] is None
    assert seen["day"] == day
    assert seen["caption"] == "一日一帧"
    assert seen["source"] == "manual"


def test_discovery_task_summarises_a_running_task():
    from app.db.models.task import TaskStatus

    task = SimpleNamespace(id=uuid4(), status=TaskStatus.PROCESSING, result={"created": 3})

    payload = chapter_api._discovery_task(task)

    assert payload["id"] == str(task.id)
    assert payload["status"] == TaskStatus.PROCESSING
    assert payload["created"] == 3
    assert payload["error"] is None


def test_discovery_task_reports_a_failed_task():
    from app.db.models.task import TaskStatus

    task = SimpleNamespace(id=uuid4(), status=TaskStatus.FAILED, result=None)

    payload = chapter_api._discovery_task(task)

    assert payload["status"] == TaskStatus.FAILED
    assert payload["created"] == 0
    assert payload["error"] == "发现失败，请重试"


def _fake_user_query(session):
    """save_day 会对当前用户行加锁，这里用桩查询替换真实用户行查询。"""
    original = session.query

    def query(*args, **kwargs):
        result = original(*args, **kwargs)
        if args and getattr(args[0], "__name__", "") == "User":
            return _StubQuery()
        return result

    return query


class _StubQuery:
    def filter(self, *args, **kwargs):
        return self

    def with_for_update(self):
        return self

    def one(self):
        return SimpleNamespace(id=uuid4())
