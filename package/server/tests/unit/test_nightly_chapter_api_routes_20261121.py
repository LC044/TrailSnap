"""Nightly watch 2026-11-21 · app/api/chapter.py 的路由盲区。

被测模块：app/api/chapter.py。上一轮静态扫描显示该 router 有 18 个顶层
函数没有任何测试引用（list_chapters / chapter_year_links / preview_chapter /
chapter_cover_options / discover_chapters / merge_chapters / create_chapter /
update_chapter / split_chapter / chapter_action / chapter_photos /
chapter_events / delete_chapter ...）。

这些路由都只是薄薄的参数装配层，真正的业务在 app/service/chapter.py 与
app/service/chapter_days.py，因此本文件替换这些协作者，只验证路由层的
参数传递、分页/年份边界校验与错误映射。
"""

from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api import chapter as chapter_api
from app.schemas.chapter import ChapterDefinition, ChapterPreview, ChapterSplit, ChapterUpdate, ChapterVersion

pytestmark = [pytest.mark.smoke]


def _user():
    return SimpleNamespace(id=uuid4())


def test_list_chapters_forwards_the_query_filters(face_sqlite_session, monkeypatch):
    from app.service import chapter as service

    captured = {}

    def fake_list_owned(db, owner_id, **kwargs):
        captured["owner_id"] = owner_id
        captured.update(kwargs)
        return {"items": [], "total": 0}

    monkeypatch.setattr(service, "list_owned", fake_list_owned)
    user = _user()
    result = chapter_api.list_chapters("confirmed", True, True, True, 5, 10, user, face_sqlite_session)

    assert result.code == 0
    assert captured["owner_id"] == user.id
    assert captured["status"] == "confirmed"
    assert captured["hidden"] is True
    assert captured["reveal"] is True
    assert captured["counts_only"] is True
    assert captured["skip"] == 5
    assert captured["limit"] == 10


def test_chapter_year_links_rejects_an_out_of_range_year(face_sqlite_session):
    with pytest.raises(HTTPException) as failure:
        chapter_api.chapter_year_links([1800], _user(), face_sqlite_session)
    assert failure.value.status_code == 400
    assert failure.value.detail == "年份范围无效"


def test_chapter_year_links_rejects_too_many_years(face_sqlite_session):
    with pytest.raises(HTTPException) as failure:
        chapter_api.chapter_year_links(list(range(2000, 2035)), _user(), face_sqlite_session)
    assert failure.value.status_code == 400


def test_chapter_action_rejects_an_unknown_action(face_sqlite_session):
    with pytest.raises(HTTPException) as failure:
        chapter_api.chapter_action(
            uuid4(), "publish", ChapterVersion(version=1), _user(), face_sqlite_session
        )
    assert failure.value.status_code == 404
    assert failure.value.detail == "操作不存在"


def test_update_chapter_serializes_the_updated_row(face_sqlite_session, monkeypatch):
    from app.service import chapter as service

    row = SimpleNamespace(id=uuid4(), version=3)
    captured = {}

    def fake_update(db, owner_id, chapter_id, payload):
        captured["chapter_id"] = chapter_id
        captured["version"] = payload.version
        return row

    monkeypatch.setattr(service, "update", fake_update)
    monkeypatch.setattr(service, "serialize", lambda db, value: {"id": str(value.id)})

    payload = ChapterUpdate(
        title="新的章节", start_date=date(2024, 1, 1), end_date=date(2024, 12, 31), version=3
    )
    result = chapter_api.update_chapter(row.id, payload, _user(), face_sqlite_session)

    assert result.code == 0
    assert result.data == {"id": str(row.id)}
    assert captured["chapter_id"] == row.id
    assert captured["version"] == 3


def test_discover_chapters_reuses_the_running_discovery_task(face_sqlite_session, monkeypatch):
    from app.db.models.task import Task, TaskStatus, TaskType

    user = _user()
    task = Task(owner_id=user.id, type=TaskType.DISCOVER_CHAPTERS.value, status=TaskStatus.PENDING.value)
    face_sqlite_session.add(task)
    face_sqlite_session.commit()

    started = []

    class _FakeManager:
        def start_worker_if_needed(self):
            started.append(True)

    class _FakeTaskManager:
        @staticmethod
        def get_instance():
            return _FakeManager()

    monkeypatch.setattr("app.service.task_manager.TaskManager", _FakeTaskManager)
    result = chapter_api.discover_chapters(user, face_sqlite_session)

    assert result.code == 0
    assert result.data["id"] == str(task.id)
    assert result.data["status"] == TaskStatus.PENDING.value
    assert started == [True]


def test_delete_chapter_delegates_to_the_service(face_sqlite_session, monkeypatch):
    from app.service import chapter as service

    captured = {}

    def fake_delete(db, owner_id, chapter_id, version):
        captured["chapter_id"] = chapter_id
        captured["version"] = version

    monkeypatch.setattr(service, "delete", fake_delete)
    chapter_id = uuid4()
    result = chapter_api.delete_chapter(chapter_id, 2, _user(), face_sqlite_session)

    assert result.code == 0
    assert result.data == {"deleted": True}
    assert captured == {"chapter_id": chapter_id, "version": 2}


def test_split_chapter_serializes_every_returned_row(face_sqlite_session, monkeypatch):
    from app.service import chapter as service

    rows = [SimpleNamespace(id=uuid4()), SimpleNamespace(id=uuid4())]
    monkeypatch.setattr(service, "split", lambda db, owner_id, chapter_id, payload: rows)
    monkeypatch.setattr(service, "serialize", lambda db, value: {"id": str(value.id)})

    payload = ChapterSplit(split_date=date(2024, 6, 1), first_title="上半年", second_title="下半年", version=1)
    result = chapter_api.split_chapter(rows[0].id, payload, _user(), face_sqlite_session)

    assert result.code == 0
    assert result.data == [{"id": str(rows[0].id)}, {"id": str(rows[1].id)}]

