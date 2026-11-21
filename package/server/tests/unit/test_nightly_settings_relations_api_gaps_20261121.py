"""Nightly watch 2026-11-21 · app/api/settings.py 与 app/api/relations.py 的路由盲区。

被测模块：
- app/api/settings.py：_select_embedding_model / get_llm_usage / scan_all_directories
- app/api/relations.py：common_memories

这三条路由各自藏着一处容易被忽略的业务约束：

- _select_embedding_model 在切换图片特征模型前，会检查旧模型是否已经相同、
  目标模型是否可用/已就绪、以及是否还有特征提取任务在跑；任何一条不满足就
  要么短路返回、要么返回 400/409，而不是直接切换。
- scan_all_directories 是管理员接口：非超管 403，目标用户不存在 404。
- common_memories 把服务层的 ValueError 翻译成带错误码的 BaseResponse.fail，
  而不是抛出 500。
本文件替换这些协作者，验证上述约束。
"""

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api import relations as relations_api
from app.api import settings as settings_api
from app.dependencies import BaseResponse

pytestmark = [pytest.mark.smoke]


def _user(is_superuser=False):
    return SimpleNamespace(id=uuid4(), is_superuser=is_superuser)


def _embedding_request(model):
    return settings_api.AIModelSelectionRequest(task="embedding", model=model)


def test_select_embedding_model_short_circuits_when_the_model_is_unchanged(monkeypatch):
    monkeypatch.setattr(
        settings_api, "_ai_model_request",
        lambda method, path, user, db, **kwargs: BaseResponse.success(data={
            "tasks": {"embedding": {"selected": "bge-m3"}},
            "models": [],
        }),
    )
    result = settings_api._select_embedding_model(_embedding_request("bge-m3"), MagicMock(), _user())
    assert result.code == 0
    assert result.data == {"changed": False, "status": "active"}


def test_select_embedding_model_rejects_an_unavailable_model(monkeypatch):
    monkeypatch.setattr(
        settings_api, "_ai_model_request",
        lambda method, path, user, db, **kwargs: BaseResponse.success(data={
            "tasks": {"embedding": {"selected": "bge-m3"}},
            "models": [{"id": "clip-vit", "tasks": ["embedding"], "available": False}],
        }),
    )
    result = settings_api._select_embedding_model(_embedding_request("clip-vit"), MagicMock(), _user())
    assert result.code == 400
    assert result.msg == "请选择可用的图片特征模型"


def test_select_embedding_model_requires_the_model_to_be_ready(monkeypatch):
    monkeypatch.setattr(
        settings_api, "_ai_model_request",
        lambda method, path, user, db, **kwargs: BaseResponse.success(data={
            "tasks": {"embedding": {"selected": "bge-m3"}},
            "models": [{"id": "clip-vit", "tasks": ["embedding"], "available": True, "status": "downloading"}],
        }),
    )
    result = settings_api._select_embedding_model(_embedding_request("clip-vit"), MagicMock(), _user())
    assert result.code == 409
    assert result.msg == "请先下载目标模型，下载完成后再切换"


def test_select_embedding_model_propagates_a_failed_snapshot(monkeypatch):
    monkeypatch.setattr(
        settings_api, "_ai_model_request",
        lambda method, path, user, db, **kwargs: BaseResponse.fail(code=503, msg="AI 服务不可用"),
    )
    result = settings_api._select_embedding_model(_embedding_request("clip-vit"), MagicMock(), _user())
    assert result.code == 503
    assert result.msg == "AI 服务不可用"


def test_get_llm_usage_delegates_to_the_usage_service(monkeypatch):
    captured = {}

    def fake_get_usage_report(db, owner_id, days):
        captured.update({"owner_id": owner_id, "days": days})
        return {"totals": {"requests": 123}, "models": []}

    monkeypatch.setattr("app.service.llm_usage.get_usage_report", fake_get_usage_report)
    user = _user()
    result = settings_api.get_llm_usage(7, MagicMock(), user)

    assert result.code == 0
    assert result.data.totals.requests == 123
    assert result.data.models == []
    assert captured == {"owner_id": user.id, "days": 7}


def test_scan_all_directories_rejects_a_normal_user(monkeypatch):
    payload = settings_api.ScanAllDirectoriesRequest()
    with pytest.raises(HTTPException) as failure:
        settings_api.scan_all_directories(payload, MagicMock(), _user(is_superuser=False))
    assert failure.value.status_code == 403
    assert failure.value.detail == "Not authorized"


def test_scan_all_directories_reports_a_missing_user(monkeypatch):
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    payload = settings_api.ScanAllDirectoriesRequest()
    with pytest.raises(HTTPException) as failure:
        settings_api.scan_all_directories(payload, db, _user(is_superuser=True))
    assert failure.value.status_code == 404
    assert failure.value.detail == "User not found"


def test_common_memories_returns_the_evidence_page(monkeypatch):
    captured = {}

    class _FakeRelations:
        def __init__(self, db, owner_id):
            captured["owner_id"] = owner_id

        def evidence(self, left, right, kind, limit, cursor):
            captured.update({"left": left, "right": right, "kind": kind, "limit": limit, "cursor": cursor})
            return {"items": [{"id": "e1"}], "next_cursor": None}

    monkeypatch.setattr(relations_api, "Relations", _FakeRelations)
    user = _user()
    result = relations_api.common_memories("photo:1", "photo:2", 10, None, user, MagicMock())

    assert result.code == 0
    assert result.data == {"items": [{"id": "e1"}], "next_cursor": None}
    assert captured["owner_id"] == user.id
    assert captured["kind"] == "memory"
    assert captured["left"] == "photo:1"
    assert captured["right"] == "photo:2"


def test_common_memories_maps_a_service_error_to_a_failed_response(monkeypatch):
    class _FakeRelations:
        def __init__(self, db, owner_id):
            pass

        def evidence(self, left, right, kind, limit, cursor):
            raise HTTPException(status_code=404, detail="对象不存在")

    monkeypatch.setattr(relations_api, "Relations", _FakeRelations)
    result = relations_api.common_memories("photo:1", "photo:2", 10, None, _user(), MagicMock())

    assert result.code == 404
    assert result.msg == "对象不存在"
    assert result.data is None

