"""Unit tests for ``app/service/tasks/image_embedding.py::process_batch``.

Target: ``ImageEmbeddingStrategy.process_batch`` (the multi-task entry
point that groups photo-embedding jobs by owner, batches them into a
single AI service request, and persists the resulting vectors).

The companion ``test_tasks_image_embedding.py`` covers the
``process``/``process_single_photo`` surfaces; this file fills in the
``process_batch`` surface that the cov scan flagged.

Each test runs ``process_batch`` deterministically by patching:

* ``storage.get_available_photo_path`` -- return a fake path we open
  in-process.
* ``aiohttp.ClientSession`` -- return a stub whose ``post(...).__aenter__``
  yields a stub response with ``status`` / ``json`` / ``text``.
* ``config_manager.get_user_config`` -- return a SimpleNamespace whose
  ``.ai.ai_api_url`` points at our ``http://fake-ai`` host.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, mock_open, patch

import pytest


pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


def _build_task(payload, *, owner_id="user-1", task_id=None):
    return SimpleNamespace(
        id=task_id or f"task-{payload.get('photo_id', 'gen')}",
        type="IMAGE_EMBEDDING",
        owner_id=owner_id,
        payload=payload,
        total_items=0,
        processed_items=0,
        result=None,
        status=None,
    )


def _make_photo(pid, *, owner_id="user-1", file_path="/fake/photo.jpg"):
    return SimpleNamespace(
        id=pid,
        file_type="image",
        processed_tasks={},
        owner_id=owner_id,
        file_path=file_path,
    )


def _ai_response(status=200, *, embeddings=None, body_text="error"):
    resp = MagicMock()
    resp.status = status
    if status == 200:
        resp.json = AsyncMock(return_value=embeddings or [])
    else:
        resp.text = AsyncMock(return_value=body_text)
        resp.json = AsyncMock(return_value={})
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    return resp


def _session_with(response):
    session = MagicMock()
    session.post = MagicMock(return_value=response)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


def _patch_ai_config(monkeypatch, *, url="http://fake-ai"):
    cfg = SimpleNamespace(ai=SimpleNamespace(ai_api_url=url))
    monkeypatch.setattr(
        "app.service.tasks.image_embedding.config_manager.get_user_config",
        lambda owner_id, db: cfg,
    )


def _patch_storage(monkeypatch, *, target="/fake/photo.jpg"):
    monkeypatch.setattr(
        "app.service.tasks.image_embedding.storage.get_available_photo_path",
        lambda owner_id, photo_id, file_path: target,
    )


# Happy path: AI service returns a valid embedding per photo


def test_process_batch_persists_embedding_and_marks_photo(monkeypatch):
    from app.service.tasks import image_embedding as ie_mod

    photo = _make_photo("p-1")
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [photo]
    db.query.return_value.filter.return_value.first.return_value = None

    resp = _ai_response(200, embeddings=[[0.1, 0.2, 0.3]])
    session = _session_with(resp)
    _patch_ai_config(monkeypatch)
    _patch_storage(monkeypatch)

    task = _build_task({"photo_id": "p-1"}, task_id="t-1")

    with patch(
        "app.service.tasks.image_embedding.aiohttp.ClientSession",
        return_value=session,
    ), patch("builtins.open", mock_open(read_data=b"\x89PNG\r\n\x1a\n")):
        results = asyncio.run(
            ie_mod.ImageEmbeddingStrategy().process_batch(
                worker=None, tasks=[task], db=db,
            )
        )

    assert len(results) == 1
    r = results[0]
    assert r["task_id"] == "t-1"
    assert r["status"] == "completed"
    assert r["result"]["status"] == "success"
    assert r["result"]["embedding_size"] == 3
    assert photo.processed_tasks["image_embedding"] is True
    db.commit.assert_called()


# Photo lookup misses: record a "skipped" entry without calling AI


def test_process_batch_skips_missing_photo(monkeypatch):
    from app.service.tasks import image_embedding as ie_mod

    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = []

    task = _build_task({"photo_id": "missing"}, task_id="t-skip")

    _patch_ai_config(monkeypatch)
    _patch_storage(monkeypatch)

    results = asyncio.run(
        ie_mod.ImageEmbeddingStrategy().process_batch(
            worker=None, tasks=[task], db=db,
        )
    )

    assert len(results) == 1
    assert results[0]["status"] == "completed"
    assert results[0]["result"] == {"status": "skipped", "reason": "photo not found"}


# File not found at storage layer -> failed result without AI call


def test_process_batch_marks_failed_when_storage_returns_none(monkeypatch):
    from app.service.tasks import image_embedding as ie_mod

    photo = _make_photo("p-x")
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [photo]

    monkeypatch.setattr(
        "app.service.tasks.image_embedding.storage.get_available_photo_path",
        lambda owner_id, photo_id, file_path: None,
    )
    _patch_ai_config(monkeypatch)

    task = _build_task({"photo_id": "p-x"}, task_id="t-nofile")

    results = asyncio.run(
        ie_mod.ImageEmbeddingStrategy().process_batch(
            worker=None, tasks=[task], db=db,
        )
    )

    assert results[0]["status"] == "failed"
    assert results[0]["error"] == "file not found"


# File read raises OSError -> failure recorded, AI not called


def test_process_batch_records_read_error(monkeypatch):
    from app.service.tasks import image_embedding as ie_mod

    photo = _make_photo("p-y")
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [photo]

    _patch_ai_config(monkeypatch)
    _patch_storage(monkeypatch)

    def boom(*args, **kwargs):
        raise OSError("disk gone")

    task = _build_task({"photo_id": "p-y"}, task_id="t-read")

    with patch("builtins.open", side_effect=boom):
        results = asyncio.run(
            ie_mod.ImageEmbeddingStrategy().process_batch(
                worker=None, tasks=[task], db=db,
            )
        )

    assert len(results) == 1
    assert results[0]["status"] == "failed"
    assert "read file error" in results[0]["error"]
    assert "disk gone" in results[0]["error"]


# AI service returns non-200 -> all tasks in the batch fail with AI msg


def test_process_batch_ai_non_200_marks_all_failed(monkeypatch):
    from app.service.tasks import image_embedding as ie_mod

    photo1 = _make_photo("p-a")
    photo2 = _make_photo("p-b", file_path="/fake/photo2.jpg")
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [photo1, photo2]

    _patch_ai_config(monkeypatch)
    _patch_storage(monkeypatch)

    resp = _ai_response(500, body_text="boom")
    session = _session_with(resp)

    task1 = _build_task({"photo_id": "p-a"}, task_id="t-a")
    task2 = _build_task({"photo_id": "p-b"}, task_id="t-b")

    with patch(
        "app.service.tasks.image_embedding.aiohttp.ClientSession",
        return_value=session,
    ), patch("builtins.open", mock_open(read_data=b"x")):
        results = asyncio.run(
            ie_mod.ImageEmbeddingStrategy().process_batch(
                worker=None, tasks=[task1, task2], db=db,
            )
        )

    assert len(results) == 2
    for r in results:
        assert r["status"] == "failed"
        assert "AI Service error: 500" in r["error"]


# AI returns 200 with empty list -> failed "No embedding returned"


def test_process_batch_ai_empty_list_reports_no_embedding(monkeypatch):
    from app.service.tasks import image_embedding as ie_mod

    photo = _make_photo("p-empty")
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [photo]
    db.query.return_value.filter.return_value.first.return_value = None

    _patch_ai_config(monkeypatch)
    _patch_storage(monkeypatch)

    resp = _ai_response(200, embeddings=[])
    session = _session_with(resp)

    task = _build_task({"photo_id": "p-empty"}, task_id="t-empty")

    with patch(
        "app.service.tasks.image_embedding.aiohttp.ClientSession",
        return_value=session,
    ), patch("builtins.open", mock_open(read_data=b"x")):
        results = asyncio.run(
            ie_mod.ImageEmbeddingStrategy().process_batch(
                worker=None, tasks=[task], db=db,
            )
        )

    assert results[0]["status"] == "failed"
    assert results[0]["error"] == "No embedding returned"


# Empty task list -> empty result list (no AI session)


def test_process_batch_empty_task_list_returns_empty(monkeypatch):
    from app.service.tasks import image_embedding as ie_mod

    db = MagicMock()

    with patch(
        "app.service.tasks.image_embedding.aiohttp.ClientSession"
    ) as session_cls:
        results = asyncio.run(
            ie_mod.ImageEmbeddingStrategy().process_batch(
                worker=None, tasks=[], db=db,
            )
        )

    assert results == []
    session_cls.assert_not_called()


# Generator-mode tasks (no photo_id) run via self.process and contribute results


def test_process_batch_routes_generator_task_through_process(monkeypatch):
    from app.service.tasks import image_embedding as ie_mod

    strategy = ie_mod.ImageEmbeddingStrategy()
    sentinel = {"processed": 0, "generated_tasks": 0, "message": "noop"}

    db = MagicMock()

    with patch.object(strategy, "process", new=AsyncMock(return_value=sentinel)):
        results = asyncio.run(
            strategy.process_batch(
                worker=None, tasks=[_build_task({}, task_id="t-gen")], db=db,
            )
        )

    assert len(results) == 1
    assert results[0]["task_id"] == "t-gen"
    assert results[0]["status"] == "completed"
    assert results[0]["result"] == sentinel


# Generator task raises -> recorded as failed result, photo tasks still run


def test_process_batch_generator_exception_recorded_and_continues(monkeypatch):
    from app.service.tasks import image_embedding as ie_mod

    strategy = ie_mod.ImageEmbeddingStrategy()
    photo = _make_photo("p-z")
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [photo]
    db.query.return_value.filter.return_value.first.return_value = None

    _patch_ai_config(monkeypatch)
    _patch_storage(monkeypatch)

    resp = _ai_response(200, embeddings=[[0.7, 0.8, 0.9]])
    session = _session_with(resp)

    gen_task = _build_task({}, task_id="t-gen-fail")
    photo_task = _build_task({"photo_id": "p-z"}, task_id="t-z")

    with patch.object(
        strategy, "process", new=AsyncMock(side_effect=RuntimeError("gen boom")),
    ), patch(
        "app.service.tasks.image_embedding.aiohttp.ClientSession",
        return_value=session,
    ), patch("builtins.open", mock_open(read_data=b"x")):
        results = asyncio.run(
            strategy.process_batch(
                worker=None, tasks=[gen_task, photo_task], db=db,
            )
        )

    by_id = {r["task_id"]: r for r in results}
    assert by_id["t-gen-fail"]["status"] == "failed"
    assert "gen boom" in by_id["t-gen-fail"]["error"]
    assert by_id["t-z"]["status"] == "completed"
    assert by_id["t-z"]["result"]["status"] == "success"
