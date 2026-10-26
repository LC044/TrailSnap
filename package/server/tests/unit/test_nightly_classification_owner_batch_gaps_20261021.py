"""Unit tests for the 2026-10-21 nightly coverage gap scan.

Module exercised: ``app/service/tasks/classification.py``.

``ClassifyImageStrategy._process_ai_results`` and ``process_batch`` already
have dedicated coverage from the 2026-08-14 / 2026-08-18 rounds, but the
per-owner batch entry point ``_process_owner_batch`` (the function that
resolves photo paths, reads bytes, calls the AI classification endpoint and
maps HTTP failures back onto tasks) had **zero** direct tests -- every existing
case patches it out.

Coverage before this file: 71.1% (50 missed statements); lines 115-174 were
entirely unexecuted.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest


pytestmark = [pytest.mark.smoke]


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _strategy():
    from app.service.tasks.classification import ClassifyImageStrategy

    return ClassifyImageStrategy()


def _task(photo_id=None):
    return SimpleNamespace(
        id=uuid4(),
        type="CLASSIFY_IMAGE",
        owner_id=uuid4(),
        payload={"photo_id": str(photo_id or uuid4())},
    )


def _photo(tmp_path: Path):
    path = tmp_path / f"{uuid4().hex}.jpg"
    path.write_bytes(b"binary-image-bytes")
    return SimpleNamespace(
        id=uuid4(),
        owner_id=uuid4(),
        file_path=str(path),
        processed_tasks={},
    )


def _db(photos):
    db = MagicMock()
    db.info = {}
    db.query.return_value.filter.return_value.all.return_value = photos
    return db


def _ai_url(monkeypatch, url="http://ai.test:8001"):
    from app.service.tasks import classification as cls_mod

    monkeypatch.setattr(
        cls_mod.config_manager,
        "get_user_config",
        lambda owner_id, db: SimpleNamespace(ai=SimpleNamespace(ai_api_url=url)),
    )


def _fake_resp(status=200, payload=None):
    resp = MagicMock()
    resp.status = status
    resp.json = AsyncMock(return_value=payload if payload is not None else {})
    return resp


def _patch_client_session(monkeypatch, resp):
    """Wire aiohttp.ClientSession so `async with session.post(...)` yields resp."""
    from app.service.tasks import classification as cls_mod

    session = MagicMock()
    post_ctx = MagicMock()
    post_ctx.__aenter__ = AsyncMock(return_value=resp)
    post_ctx.__aexit__ = AsyncMock(return_value=False)
    session.post.return_value = post_ctx

    client_ctx = MagicMock()
    client_ctx.__aenter__ = AsyncMock(return_value=session)
    client_ctx.__aexit__ = AsyncMock(return_value=False)

    opened = MagicMock(return_value=client_ctx)
    monkeypatch.setattr(cls_mod.aiohttp, "ClientSession", opened)
    return opened, session


def _patch_disk_budget(monkeypatch, side_effect=None):
    from app.service.tasks import classification as cls_mod

    budget = MagicMock()
    if side_effect is not None:
        budget.slot.side_effect = side_effect
    else:
        budget.slot.return_value.__enter__.return_value = "slot"
        budget.slot.return_value.__exit__.return_value = False
    monkeypatch.setattr(cls_mod, "disk_budget", budget)
    return budget


def _existing_path(monkeypatch):
    """Resolve each photo to the real file the `_photo` helper created."""
    from app.service.tasks import classification as cls_mod

    monkeypatch.setattr(
        cls_mod.storage, "get_available_photo_path", lambda _owner, _pid, path: path
    )


# === happy path ===


def test_process_owner_batch_posts_images_and_delegates_to_ai_results(monkeypatch, tmp_path):
    strategy = _strategy()
    photo = _photo(tmp_path)
    task = _task(photo.id)

    _existing_path(monkeypatch)
    _patch_disk_budget(monkeypatch)
    _ai_url(monkeypatch)

    resp = _fake_resp(200, {"results": [{"status": "success", "predictions": []}]})
    opened, session = _patch_client_session(monkeypatch, resp)

    ai_results = [{"task_id": task.id, "task_type": "CLASSIFY_IMAGE", "status": "completed"}]
    delegated = AsyncMock(return_value=ai_results)
    monkeypatch.setattr(strategy, "_process_ai_results", delegated)

    db = _db([photo])
    results = _run(strategy._process_owner_batch(photo.owner_id, [task], db))

    assert results == ai_results
    opened.assert_called_once()
    api_url, = session.post.call_args.args
    assert api_url == "http://ai.test:8001/classification/"
    # images are base64 encoded, never raw bytes
    sent = session.post.call_args.kwargs["json"]["images"]
    assert len(sent) == 1 and sent[0] != "binary-image-bytes"
    delegated.assert_awaited_once()


# === edge: unusable photos are reported without contacting the AI service ===


def test_process_owner_batch_marks_missing_photo_as_skipped(monkeypatch, tmp_path):
    from app.service.tasks import classification as cls_mod

    strategy = _strategy()
    task = _task()
    _patch_disk_budget(monkeypatch)
    opened, _ = _patch_client_session(monkeypatch, _fake_resp())

    db = _db([])  # photo row already deleted
    results = _run(strategy._process_owner_batch(uuid4(), [task], db))

    assert results == [{
        "task_id": task.id,
        "task_type": "CLASSIFY_IMAGE",
        "status": "completed",
        "result": {"status": "skipped", "reason": "photo not found"},
    }]
    opened.assert_not_called()


def test_process_owner_batch_marks_missing_file_as_failed(monkeypatch, tmp_path):
    from app.service.tasks import classification as cls_mod

    strategy = _strategy()
    photo = _photo(tmp_path)
    task = _task(photo.id)
    monkeypatch.setattr(cls_mod.storage, "get_available_photo_path", lambda *a: None)
    _patch_disk_budget(monkeypatch)
    opened, _ = _patch_client_session(monkeypatch, _fake_resp())

    results = _run(strategy._process_owner_batch(photo.owner_id, [task], _db([photo])))

    assert results == [{
        "task_id": task.id,
        "task_type": "CLASSIFY_IMAGE",
        "status": "failed",
        "error": "file not found",
    }]
    opened.assert_not_called()


def test_process_owner_batch_returns_early_when_no_task_is_readable(monkeypatch, tmp_path):
    """All photos are unusable -> early return without opening an aiohttp session."""
    from app.service.tasks import classification as cls_mod

    strategy = _strategy()
    photos = [_photo(tmp_path), _photo(tmp_path)]
    tasks = [_task(p.id) for p in photos]
    monkeypatch.setattr(cls_mod.storage, "get_available_photo_path", lambda *a: None)
    _patch_disk_budget(monkeypatch)
    opened, _ = _patch_client_session(monkeypatch, _fake_resp())

    results = _run(strategy._process_owner_batch(photos[0].owner_id, tasks, _db(photos)))

    assert len(results) == 2
    assert all(r["error"] == "file not found" for r in results)
    opened.assert_not_called()


# === error: local IO and remote HTTP failures ===


def test_process_owner_batch_reports_read_error_per_task(monkeypatch, tmp_path):
    strategy = _strategy()
    photo = _photo(tmp_path)
    task = _task(photo.id)

    _existing_path(monkeypatch)
    # disk_budget.slot() itself blowing up is the cheapest way to make the
    # read block raise, which is what the per-task handler catches.
    _patch_disk_budget(monkeypatch, side_effect=OSError("disk budget exhausted"))
    opened, _ = _patch_client_session(monkeypatch, _fake_resp())

    results = _run(strategy._process_owner_batch(photo.owner_id, [task], _db([photo])))

    assert results[0]["status"] == "failed"
    assert "read file error" in results[0]["error"]
    assert "disk budget exhausted" in results[0]["error"]
    opened.assert_not_called()


def test_process_owner_batch_fails_every_task_on_ai_http_error(monkeypatch, tmp_path):
    from app.service.tasks import classification as cls_mod

    strategy = _strategy()
    photos = [_photo(tmp_path), _photo(tmp_path)]
    tasks = [_task(p.id) for p in photos]
    _existing_path(monkeypatch)
    _patch_disk_budget(monkeypatch)
    _ai_url(monkeypatch)
    _patch_client_session(monkeypatch, _fake_resp(503))
    err_mock = AsyncMock(return_value="ai service unavailable")
    monkeypatch.setattr(cls_mod, "ai_response_error", err_mock)

    results = _run(strategy._process_owner_batch(photos[0].owner_id, tasks, _db(photos)))

    assert len(results) == 2
    assert all(r["status"] == "failed" for r in results)
    assert all(r["error"] == "ai service unavailable" for r in results)
    err_mock.assert_awaited()


def test_process_owner_batch_rolls_back_and_fails_tasks_on_unexpected_error(monkeypatch, tmp_path):
    strategy = _strategy()
    photo = _photo(tmp_path)
    task = _task(photo.id)
    db = _db([photo])
    db.query.side_effect = RuntimeError("db connection lost")
    db.info = {"classification_tags": {("x", "beach"): "tag-id"}}

    results = _run(strategy._process_owner_batch(photo.owner_id, [task], db))

    db.rollback.assert_called_once()
    assert "classification_tags" not in db.info
    assert results == [{
        "task_id": task.id,
        "task_type": "CLASSIFY_IMAGE",
        "status": "failed",
        "error": "db connection lost",
    }]


def test_process_owner_batch_keeps_already_recorded_results_when_batch_fails(
    monkeypatch, tmp_path
):
    """A mid-batch failure must not overwrite the per-photo verdicts already collected."""
    from app.service.tasks import classification as cls_mod

    strategy = _strategy()
    missing = _photo(tmp_path)          # not returned by the query -> skipped
    present = _photo(tmp_path)         # returned, but config lookup blows up later
    tasks = [_task(missing.id), _task(present.id)]

    _existing_path(monkeypatch)
    _patch_disk_budget(monkeypatch)
    monkeypatch.setattr(
        cls_mod.config_manager,
        "get_user_config",
        MagicMock(side_effect=RuntimeError("ai config missing")),
    )

    db = _db([present])
    results = _run(strategy._process_owner_batch(present.owner_id, tasks, db))

    by_id = {r["task_id"]: r for r in results}
    assert by_id[tasks[0].id]["result"] == {"status": "skipped", "reason": "photo not found"}
    assert by_id[tasks[1].id]["status"] == "failed"
    assert by_id[tasks[1].id]["error"] == "ai config missing"
    assert len(results) == 2
