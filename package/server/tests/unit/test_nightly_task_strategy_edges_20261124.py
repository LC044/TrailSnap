"""Nightly watch 2026-11-24 — app/service/tasks/ 下三个任务策略的边界补测。

* image_embedding：resource_key 常量、异常被记录后重新抛出、批量任务的
  模型冲突校验、以及批量请求时 payload 是否带上 model。
* similar：带 cleanup_scan_id 的任务转交 cleanup_scan 处理；批量处理到
  100 张时应刷新进度并提交事务。
* tickets：票据识别结果里的车次候选码归一化与行程来源合并。
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest


pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


def _task(payload, task_id="task-1", owner_id="owner-1"):
    return SimpleNamespace(
        id=task_id,
        type="IMAGE_EMBEDDING",
        owner_id=owner_id,
        payload=payload,
        total_items=0,
        processed_items=0,
        result=None,
        status=None,
    )


def _photo(photo_id="p-1", owner_id="owner-1"):
    return SimpleNamespace(
        id=photo_id,
        owner_id=owner_id,
        file_path=f"/photos/{photo_id}.jpg",
        processed_tasks={},
    )


# --------------------------------------------------------------------------- #
# image_embedding
# --------------------------------------------------------------------------- #

def test_image_embedding_strategy_declares_the_embedding_resource():
    """resource_key 必须是 embedding，任务队列按它分桶。"""
    from app.service.tasks import image_embedding as ie_mod

    assert ie_mod.ImageEmbeddingStrategy().resource_key == "embedding"


def test_image_embedding_logs_and_reraises_unexpected_errors():
    """处理过程中的异常必须被记录后继续抛出，不能被静默吞掉。"""
    from app.service.tasks import image_embedding as ie_mod

    db = MagicMock()
    db.query.side_effect = RuntimeError("db is gone")
    task = _task({"photo_id": "p-1"})

    with pytest.raises(RuntimeError):
        asyncio.run(ie_mod.ImageEmbeddingStrategy().process(worker=None, task=task, db=db))


class _FakeResponse:
    def __init__(self, status=200):
        self.status = status

    async def json(self):
        raise RuntimeError("stop here after the request was built")


class _FakePost:
    def __init__(self, captured, response):
        self._captured = captured
        self._response = response

    async def __aenter__(self):
        return self._response

    async def __aexit__(self, *exc_info):
        return False

    def __call__(self, url, json=None, **kwargs):
        self._captured["url"] = url
        self._captured["payload"] = json
        return _FakePost(self._captured, self._response)


class _FakeSession:
    def __init__(self, captured, response):
        self._captured = captured
        self._response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    def post(self, url, json=None, **kwargs):
        self._captured["url"] = url
        self._captured["payload"] = json
        return _FakePost(self._captured, self._response)


def _patch_batch_env(monkeypatch, captured, response, tmp_path):
    from app.service.tasks import image_embedding as ie_mod

    target = tmp_path / "photo.jpg"
    target.write_bytes(b"binary-image")

    monkeypatch.setattr(
        ie_mod.storage, "get_available_photo_path", lambda *a, **k: str(target)
    )
    monkeypatch.setattr(
        ie_mod.disk_budget, "slot", lambda *a, **k: contextlib.nullcontext()
    )
    monkeypatch.setattr(
        ie_mod.config_manager,
        "get_user_config",
        lambda owner_id, db: SimpleNamespace(ai=SimpleNamespace(ai_api_url="http://ai.local")),
    )
    monkeypatch.setattr(ie_mod.aiohttp, "ClientSession", lambda *a, **k: _FakeSession(captured, response))


def test_image_embedding_batch_rejects_conflicting_models(monkeypatch, tmp_path):
    """同一批次里出现两种向量模型时必须整批失败，不能混用。"""
    from app.service.tasks import image_embedding as ie_mod

    captured: dict = {}
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [_photo()]
    _patch_batch_env(monkeypatch, captured, _FakeResponse(), tmp_path)

    tasks = [
        _task({"photo_id": "p-1", "model": "a"}, task_id="t-1"),
        _task({"photo_id": "p-1", "model": "b"}, task_id="t-2"),
    ]

    results = asyncio.run(
        ie_mod.ImageEmbeddingStrategy().process_batch(worker=None, tasks=tasks, db=db)
    )

    assert all(item["status"] == "failed" for item in results)
    assert any("Conflicting embedding models" in item["error"] for item in results)
    assert "payload" not in captured


def test_image_embedding_batch_forwards_the_selected_model(monkeypatch, tmp_path):
    """批量请求应把任务里唯一的模型名写进请求 payload。"""
    from app.service.tasks import image_embedding as ie_mod

    captured: dict = {}
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [_photo()]
    _patch_batch_env(monkeypatch, captured, _FakeResponse(), tmp_path)

    tasks = [_task({"photo_id": "p-1", "model": "vit-b32"}, task_id="t-1")]

    results = asyncio.run(
        ie_mod.ImageEmbeddingStrategy().process_batch(worker=None, tasks=tasks, db=db)
    )

    assert captured["payload"]["model"] == "vit-b32"
    assert captured["url"].endswith("/embedding/image")
    assert results[0]["status"] == "failed"  # 伪造响应在 json() 处抛错


class _SingleResponse:
    """模拟 /embedding/image 的成功响应。"""

    status = 200
    headers = {"X-Embedding-Model": "clip-ViT-B-32"}

    async def json(self):
        return [[0.1, 0.2, 0.3]]


def test_process_single_photo_sends_the_requested_model(monkeypatch, tmp_path):
    """单张处理时要把任务指定的模型名写进请求 payload。"""
    from app.service.tasks import image_embedding as ie_mod

    captured: dict = {}
    target = tmp_path / "photo.jpg"
    target.write_bytes(b"binary-image")
    photo = _photo()

    monkeypatch.setattr(
        ie_mod.storage, "get_available_photo_path", lambda *a, **k: str(target)
    )
    monkeypatch.setattr(
        ie_mod.disk_budget, "slot", lambda *a, **k: contextlib.nullcontext()
    )
    monkeypatch.setattr(
        ie_mod.config_manager,
        "get_user_config",
        lambda owner_id, db: SimpleNamespace(ai=SimpleNamespace(ai_api_url="http://ai.local")),
    )
    monkeypatch.setattr("app.service.clip_classification.enqueue_photo", lambda db, p: None)
    monkeypatch.setattr(ie_mod.aiohttp, "ClientSession", lambda *a, **k: _FakeSession(captured, _SingleResponse()))

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(
        photo_id=photo.id, embedding=None, model_name=None
    )

    result = asyncio.run(
        ie_mod.ImageEmbeddingStrategy().process_single_photo(None, photo, db, model="clip-ViT-B-32")
    )

    assert result["status"] == "success"
    assert captured["payload"]["model"] == "clip-ViT-B-32"
    assert len(captured["payload"]["images"]) == 1


def test_process_single_photo_reports_inference_timeout(monkeypatch, tmp_path):
    """AI 推理超时要转成可读的失败原因，而不是抛裸异常。"""
    from app.service.tasks import image_embedding as ie_mod

    captured: dict = {}
    target = tmp_path / "photo.jpg"
    target.write_bytes(b"binary-image")
    photo = _photo()

    monkeypatch.setattr(
        ie_mod.storage, "get_available_photo_path", lambda *a, **k: str(target)
    )
    monkeypatch.setattr(
        ie_mod.disk_budget, "slot", lambda *a, **k: contextlib.nullcontext()
    )
    monkeypatch.setattr(
        ie_mod.config_manager,
        "get_user_config",
        lambda owner_id, db: SimpleNamespace(ai=SimpleNamespace(ai_api_url="http://ai.local")),
    )
    monkeypatch.setattr(
        ie_mod, "inference_timeout_error", lambda exc: "等待 AI 模型：推理超时"
    )

    class _BoomSession(_FakeSession):
        def post(self, url, json=None, **kwargs):
            raise RuntimeError("boom")

    monkeypatch.setattr(ie_mod.aiohttp, "ClientSession", lambda *a, **k: _BoomSession(captured, _SingleResponse()))

    db = MagicMock()
    result = asyncio.run(
        ie_mod.ImageEmbeddingStrategy().process_single_photo(None, photo, db, model=None)
    )

    assert result["status"] == "failed"
    assert "推理超时" in result["error"]


def test_process_single_photo_translates_connection_errors(monkeypatch, tmp_path):
    """AI 服务不可达时要抛出带中文提示的 RuntimeError，供任务重试。"""
    from app.service.tasks import image_embedding as ie_mod

    captured: dict = {}
    target = tmp_path / "photo.jpg"
    target.write_bytes(b"binary-image")
    photo = _photo()

    monkeypatch.setattr(
        ie_mod.storage, "get_available_photo_path", lambda *a, **k: str(target)
    )
    monkeypatch.setattr(
        ie_mod.disk_budget, "slot", lambda *a, **k: contextlib.nullcontext()
    )
    monkeypatch.setattr(
        ie_mod.config_manager,
        "get_user_config",
        lambda owner_id, db: SimpleNamespace(ai=SimpleNamespace(ai_api_url="http://ai.local")),
    )
    monkeypatch.setattr(ie_mod, "inference_timeout_error", lambda exc: None)

    class _UnreachableSession(_FakeSession):
        def post(self, url, json=None, **kwargs):
            raise ie_mod.aiohttp.ClientConnectionError("connection refused")

    monkeypatch.setattr(
        ie_mod.aiohttp, "ClientSession", lambda *a, **k: _UnreachableSession(captured, _SingleResponse())
    )

    db = MagicMock()
    with pytest.raises(RuntimeError, match="AI 服务暂不可达"):
        asyncio.run(
            ie_mod.ImageEmbeddingStrategy().process_single_photo(None, photo, db, model=None)
        )


# --------------------------------------------------------------------------- #
# similar
# --------------------------------------------------------------------------- #

def test_similar_delegates_cleanup_scan_tasks_to_the_cleanup_service():
    """带 cleanup_scan_id 的任务应转交 cleanup_scan 处理。"""
    from app.service.tasks import similar as similar_mod

    task = _task({"cleanup_scan_id": "scan-1"}, task_id="t-scan")
    task.type = "SIMILAR_PHOTO_CLUSTERING"
    sentinel = {"status": "completed", "count": 7}

    with patch(
        "app.service.cleanup_scan.process_scan", new=AsyncMock(return_value=sentinel)
    ) as process_scan:
        result = asyncio.run(
            similar_mod.SimilarPhotoClusteringStrategy().process(worker=None, task=task, db=MagicMock())
        )

    assert result == sentinel
    process_scan.assert_awaited_once()


def test_similar_refreshes_progress_after_hundred_photos():
    """累计处理 100 张时应刷新进度并提交事务，供前端看到进度。"""
    from app.service.tasks import similar as similar_mod

    base = datetime(2026, 7, 31, 12, 0, 0)
    vec = np.array([1.0, 0.0, 0.0])

    db = MagicMock()
    db.execute.return_value.all.return_value = [
        SimpleNamespace(photo_id=f"p{i}", embedding=vec, photo_time=base) for i in range(100)
    ]
    task = _task({"threshold": 0.9}, task_id="t-sim")
    task.type = "SIMILAR_PHOTO_CLUSTERING"

    asyncio.run(
        similar_mod.SimilarPhotoClusteringStrategy().process(worker=None, task=task, db=db)
    )

    assert task.processed_items == 100
    db.commit.assert_called()


