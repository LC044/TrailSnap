"""Nightly watch 2026-10-30 (r3) · app/api/agent.py 的路由盲区。

被测模块：app/api/agent.py（此前覆盖率 85.0%，20 行未触达）。
未触达的部分集中在"照片即记忆"与"主动关怀消息"这几条新接口上：

- GET /search-results/{result_id}/photos 的成功返回与 ValueError -> 404。
- GET /memory 读取长期记忆锚点。
- DELETE /memory/{photo_id} 的成功与"未找到对应的记忆"。
- GET /proactive 组装未读主动消息（anchor_date / recommendations / unread 计数）。
- POST /proactive/{message_id}/read 的成功与"未找到对应的主动消息"。

这些接口都只是薄薄的路由层，被测的业务逻辑在
app/service/agent/memory.py、app/service/agent/photo_search.py 与 app/crud/agent.py，
因此本文件替换这些协作者，只验证路由层的组装与错误映射。
"""

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api import agent as agent_api

pytestmark = [pytest.mark.smoke]


def _user():
    return SimpleNamespace(id=uuid4())


def test_search_result_photos_returns_the_page(face_sqlite_session, monkeypatch):
    from app.service.agent import photo_search

    monkeypatch.setattr(photo_search, "search_result_page",
                        lambda db, owner_id, result_id, offset, limit: {
                            "items": [{"id": "p1"}], "total": 1, "offset": offset, "limit": limit})
    user = _user()
    result = agent_api.get_search_result_photos(uuid4(), 10, 20, user, face_sqlite_session)
    assert result.code == 0
    assert result.data["items"] == [{"id": "p1"}]
    assert result.data["offset"] == 10


def test_search_result_photos_reports_an_unknown_result_as_404(face_sqlite_session, monkeypatch):
    from app.service.agent import photo_search

    def explode(db, owner_id, result_id, offset, limit):
        raise ValueError("搜索结果不存在")

    monkeypatch.setattr(photo_search, "search_result_page", explode)
    with pytest.raises(HTTPException) as failure:
        agent_api.get_search_result_photos(uuid4(), 0, 60, _user(), face_sqlite_session)
    assert failure.value.status_code == 404
    assert failure.value.detail == "搜索结果不存在"


def test_memory_lists_the_valid_anchors(face_sqlite_session, monkeypatch):
    from app.service.agent import memory

    monkeypatch.setattr(memory, "get_valid_memory_anchors",
                        lambda db, owner_id: [{"photo_id": "p1", "caption": "海边"}])
    user = _user()
    result = agent_api.get_memory(user, face_sqlite_session)
    assert result.code == 0
    assert result.data["anchors"] == [{"photo_id": "p1", "caption": "海边"}]


def test_delete_memory_reports_success(face_sqlite_session, monkeypatch):
    from app.service.agent import memory

    removed = {}
    monkeypatch.setattr(memory, "remove_memory_anchor",
                        lambda db, owner_id, photo_id: removed.setdefault("photo_id", photo_id) is not None)
    result = agent_api.delete_memory("p1", _user(), face_sqlite_session)
    assert result.code == 0
    assert result.data == {"photo_id": "p1"}
    assert removed["photo_id"] == "p1"


def test_delete_memory_reports_a_missing_anchor(face_sqlite_session, monkeypatch):
    from app.service.agent import memory

    monkeypatch.setattr(memory, "remove_memory_anchor", lambda db, owner_id, photo_id: False)
    result = agent_api.delete_memory("p1", _user(), face_sqlite_session)
    assert result.code == 404
    assert result.msg == "未找到对应的记忆"


def test_proactive_messages_are_assembled_with_their_metadata(face_sqlite_session, monkeypatch):
    from app.crud import agent as agent_crud

    message = SimpleNamespace(id=7, content="那年今日", content_ext={"anchor_date": "2020-05-01",
                                                                     "recommendations": ["杭州"]},
                               created_at="2026-01-02T03:04:05")
    monkeypatch.setattr(agent_crud, "get_unread_proactive_messages", lambda db, user_id: [message])
    result = agent_api.get_proactive_messages(_user(), face_sqlite_session)
    assert result.code == 0
    assert result.data["unread"] == 1
    payload = result.data["messages"][0]
    assert payload["id"] == 7
    assert payload["anchor_date"] == "2020-05-01"
    assert payload["recommendations"] == ["杭州"]


def test_proactive_messages_default_to_no_recommendations(face_sqlite_session, monkeypatch):
    from app.crud import agent as agent_crud

    message = SimpleNamespace(id=8, content="没有扩展信息", content_ext=None, created_at="2026-01-02")
    monkeypatch.setattr(agent_crud, "get_unread_proactive_messages", lambda db, user_id: [message])
    result = agent_api.get_proactive_messages(_user(), face_sqlite_session)
    payload = result.data["messages"][0]
    assert payload["anchor_date"] is None
    assert payload["recommendations"] == []


def test_proactive_messages_are_empty_without_any_unread_entry(face_sqlite_session, monkeypatch):
    from app.crud import agent as agent_crud

    monkeypatch.setattr(agent_crud, "get_unread_proactive_messages", lambda db, user_id: [])
    result = agent_api.get_proactive_messages(_user(), face_sqlite_session)
    assert result.data == {"messages": [], "unread": 0}


def test_marking_a_proactive_message_as_read(face_sqlite_session, monkeypatch):
    from app.crud import agent as agent_crud

    seen = {}
    monkeypatch.setattr(agent_crud, "mark_proactive_read",
                        lambda db, user_id, message_id: seen.setdefault("id", message_id) == message_id)
    result = agent_api.read_proactive_message(9, _user(), face_sqlite_session)
    assert result.code == 0
    assert result.data == {"message_id": 9}
    assert seen["id"] == 9


def test_marking_an_unknown_proactive_message_as_read(face_sqlite_session, monkeypatch):
    from app.crud import agent as agent_crud

    monkeypatch.setattr(agent_crud, "mark_proactive_read", lambda db, user_id, message_id: False)
    result = agent_api.read_proactive_message(404, _user(), face_sqlite_session)
    assert result.code == 404
    assert result.msg == "未找到对应的主动消息"
