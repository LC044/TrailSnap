"""Nightly watch 2026-11-21 · app/api/face.py 的聚类路由盲区。

被测模块：app/api/face.py。上一轮静态扫描显示以下顶层函数没有任何测试
引用：_guard_clustering / clustering_status / reset_clustering /
_timeline_scope。

这一段路由的语义是「人物聚类正在重整时的互斥门禁」：重整中或失败时，
除 status/reset/retry 三个自身接口外的所有人物接口都必须返回 409；
reset 本身要透传 request_id 并把任务交给后台 worker。
本文件替换聚类服务的协作者，验证门禁与透传。
"""

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api import face as face_api

pytestmark = [pytest.mark.smoke]

_RESETTABLE_PATHS = ("/clustering/status", "/clustering/reset", "/clustering/retry")


def _user():
    return SimpleNamespace(id=uuid4())


def _request(path):
    return SimpleNamespace(url=SimpleNamespace(path=path))


def test_guard_clustering_lets_the_clustering_endpoints_through(monkeypatch):
    monkeypatch.setattr(
        "app.service.face_appearance_clusters.get_state",
        lambda db, owner_id: {"phase": "resetting"},
    )
    for path in _RESETTABLE_PATHS:
        assert face_api._guard_clustering(_request(f"/api/face{path}"), MagicMock(), _user()) is None


def test_guard_clustering_blocks_the_other_endpoints_while_resetting(monkeypatch):
    monkeypatch.setattr(
        "app.service.face_appearance_clusters.get_state",
        lambda db, owner_id: {"phase": "resetting"},
    )
    with pytest.raises(HTTPException) as failure:
        face_api._guard_clustering(_request("/api/face/identities"), MagicMock(), _user())
    assert failure.value.status_code == 409
    assert failure.value.detail == "人物正在重新整理，请稍后重试"


def test_guard_clustering_blocks_when_the_clustering_failed(monkeypatch):
    monkeypatch.setattr(
        "app.service.face_appearance_clusters.get_state",
        lambda db, owner_id: {"phase": "failed"},
    )
    with pytest.raises(HTTPException) as failure:
        face_api._guard_clustering(_request("/api/face/identities"), MagicMock(), _user())
    assert failure.value.status_code == 409


def test_guard_clustering_allows_a_healthy_clustering(monkeypatch):
    monkeypatch.setattr(
        "app.service.face_appearance_clusters.get_state",
        lambda db, owner_id: {"phase": "idle"},
    )
    assert face_api._guard_clustering(_request("/api/face/identities"), MagicMock(), _user()) is None


def test_clustering_status_returns_the_service_state(monkeypatch):
    monkeypatch.setattr(
        "app.service.face_appearance_clusters.get_state",
        lambda db, owner_id: {"phase": "idle", "total": 3},
    )
    user = _user()
    result = face_api.clustering_status(MagicMock(), user)
    assert result.code == 0
    assert result.data == {"phase": "idle", "total": 3}


def test_reset_clustering_forwards_the_request_id_and_starts_the_worker(monkeypatch):
    captured = {}

    def fake_request_reset(db, owner_id, request_id):
        captured["owner_id"] = owner_id
        captured["request_id"] = request_id
        return {"phase": "resetting"}

    started = []

    class _FakeManager:
        def start_worker_for_pending_tasks(self):
            started.append(True)

    class _FakeTaskManager:
        @staticmethod
        def get_instance():
            return _FakeManager()

    monkeypatch.setattr("app.service.face_appearance_clusters.request_reset", fake_request_reset)
    monkeypatch.setattr("app.service.task_manager.TaskManager", _FakeTaskManager)

    user = _user()
    request_id = uuid4()
    result = face_api.reset_clustering(
        face_api.ResetClusteringRequest(request_id=request_id), MagicMock(), user
    )

    assert result.code == 0
    assert result.msg == "已开始重新整理人物"
    assert captured == {"owner_id": user.id, "request_id": request_id}
    assert started == [True]


def test_timeline_scope_delegates_to_the_person_timeline_service(monkeypatch):
    captured = {}

    def fake_scope(db, owner_id, identity_id, with_id):
        captured.update({"owner_id": owner_id, "identity_id": identity_id, "with_id": with_id})
        return "first", "second", ["p1"]

    monkeypatch.setattr(face_api.person_timeline, "scope", fake_scope)
    user = _user()
    identity_id = uuid4()
    with_id = uuid4()
    first, second, people = face_api._timeline_scope(MagicMock(), user, identity_id, with_id)

    assert (first, second, people) == ("first", "second", ["p1"])
    assert captured == {"owner_id": user.id, "identity_id": identity_id, "with_id": with_id}
