"""Nightly watch 2026-11-22 · app/api/chapter.py 的 get_chapter / generate_diary 路由盲区。

这两条路由是「章节详情」与「日记生成」的入口，业务逻辑分别在
app/service/chapter.py 与 app/service/chapter_diary.py；本文件只验证路由层的
参数传递与返回包装，协作者一律替换成桩函数。

覆盖：
- get_chapter 正常返回章节详情（happy）
- get_chapter 把 manage 参数透传给 service.get（edge）
- generate_diary 把 payload 透传给 chapter_diary.generate（happy）
- generate_diary 透传 HTTPException（error）
"""

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api import chapter as chapter_api

pytestmark = [pytest.mark.smoke]


def _user():
    return SimpleNamespace(id=uuid4())


def test_get_chapter_returns_the_service_payload(face_sqlite_session, monkeypatch):
    from app.service import chapter as service

    monkeypatch.setattr(service, "get", lambda db, owner_id, chapter_id, manage=False: {
        "id": str(chapter_id), "years": [2024]})
    chapter_id = uuid4()

    result = chapter_api.get_chapter(chapter_id, False, _user(), face_sqlite_session)

    assert result.code == 0
    assert result.data["id"] == str(chapter_id)
    assert result.data["years"] == [2024]


def test_get_chapter_forwards_the_manage_flag(face_sqlite_session, monkeypatch):
    from app.service import chapter as service

    seen = {}

    def fake_get(db, owner_id, chapter_id, manage=False):
        seen["manage"] = manage
        return {"id": str(chapter_id)}

    monkeypatch.setattr(service, "get", fake_get)

    chapter_api.get_chapter(uuid4(), True, _user(), face_sqlite_session)

    assert seen["manage"] is True


def test_generate_diary_forwards_the_request_to_the_service(face_sqlite_session, monkeypatch):
    from app.service import chapter_diary
    from app.schemas.chapter import ChapterDiaryGenerate

    seen = {}

    async def fake_generate(db, owner_id, chapter_id, request):
        seen["chapter_id"] = chapter_id
        seen["scope"] = request.scope
        return {"title": "小标题", "body": "正文"}

    monkeypatch.setattr(chapter_diary, "generate", fake_generate)
    chapter_id = uuid4()
    payload = ChapterDiaryGenerate(scope="introduction", version=1)

    result = asyncio.run(chapter_api.generate_diary(chapter_id, payload, _user(), face_sqlite_session))

    assert result.code == 0
    assert result.data["body"] == "正文"
    assert seen["chapter_id"] == chapter_id
    assert seen["scope"] == "introduction"


def test_generate_diary_propagates_a_service_error(face_sqlite_session, monkeypatch):
    from app.service import chapter_diary
    from app.schemas.chapter import ChapterDiaryGenerate

    async def fake_generate(db, owner_id, chapter_id, request):
        raise HTTPException(400, "当前章节不能生成日记")

    monkeypatch.setattr(chapter_diary, "generate", fake_generate)

    with pytest.raises(HTTPException) as failure:
        asyncio.run(chapter_api.generate_diary(
            uuid4(), ChapterDiaryGenerate(scope="introduction", version=1), _user(), face_sqlite_session))
    assert failure.value.status_code == 400
