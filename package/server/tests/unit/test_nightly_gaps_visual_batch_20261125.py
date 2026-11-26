"""Nightly watch 2026-11-25 (part 5): cover the batch dispatch of visual description.

``app/service/tasks/visual_description.py`` batches several photo analyses into
one model call.  ``tests/unit/test_tasks_visual_description.py`` already covers
the successful batch and the missing-number retry; the *dispatch* decisions
were never exercised: when the batch is not eligible, when a photo is not
supported, and how a broken model reply is reported.

Everything here is offline: the model client, the photo lookup and the result
writer are replaced, so no network and no database are involved.
"""
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.db.models.photo import ImageType
from app.service.tasks import visual_description as visual_module
from app.service.tasks.visual_description import VisualDescriptionStrategy

VALID_RESULT = {
    "description": "海边的日落",
    "tags": ["海边", "日落"],
    "memory_score": 88,
    "beauty_score": 91,
    "reason": "光线与构图都很出色",
    "narrative": "那天在海边等到了日落。",
}


class _FakeResponse:
    def __init__(self, content):
        self.content = content


class _FakeClient:
    def __init__(self, reply):
        self.reply = reply
        self.calls = []

    async def ainvoke(self, messages, **kwargs):
        self.calls.append(messages)
        return _FakeResponse(self.reply)


def _task(task_id, owner_id="owner-1", payload=None):
    return SimpleNamespace(
        id=task_id,
        owner_id=owner_id,
        type="visual_description",
        payload=payload if payload is not None else {"photo_id": f"photo-{task_id}"},
    )


def _photo(photo_id, image_type=ImageType.CAMERA):
    return SimpleNamespace(id=photo_id, image_type=image_type)


def _settings(connection_id="conn-1"):
    return SimpleNamespace(
        analysis_connection_id=connection_id,
        analysis_model_name="gpt-test",
        visual_evaluation_prompt="请分析照片。",
        analysis_reasoning_effort="none",
    )


def _strategy(monkeypatch, reply='{"1": %s}' % json.dumps(VALID_RESULT, ensure_ascii=False),
              connection_id="conn-1", photos=None, image_content="ok"):
    """Build a strategy whose model, photo lookup and writer are stubbed."""
    strategy = VisualDescriptionStrategy()
    client = _FakeClient(reply)

    monkeypatch.setattr(visual_module, "config_manager", MagicMock(
        get_user_config=lambda owner_id, db: SimpleNamespace(ai=_settings(connection_id))))

    @asynccontextmanager
    async def fake_client(self, settings, owner_id):
        yield client

    monkeypatch.setattr(VisualDescriptionStrategy, "_client", fake_client)

    def fake_task_photo(self, task, db):
        if photos is not None and task.id in photos:
            value = photos[task.id]
            return value if isinstance(value, tuple) else (value, None)
        return _photo(f"photo-{task.id}"), None

    monkeypatch.setattr(VisualDescriptionStrategy, "_task_photo", fake_task_photo)
    monkeypatch.setattr(
        VisualDescriptionStrategy, "_image_content",
        lambda self, photo, db, batch=False: None if image_content is None else [{"text": f"text-{photo.id}"}])
    monkeypatch.setattr(
        VisualDescriptionStrategy, "_save_result",
        lambda self, db, photo_id, result, payload=None, photo=None: {"status": "completed", "photo_id": photo_id})
    return strategy, client


async def _run(strategy, tasks):
    return await strategy.process_batch(None, tasks, MagicMock())


@pytest.mark.asyncio
async def test_a_single_task_falls_back_to_the_single_photo_path(monkeypatch):
    strategy, client = _strategy(monkeypatch)
    strategy.process = AsyncMock(return_value={"status": "completed"})

    results = await _run(strategy, [_task("a")])

    strategy.process.assert_awaited_once()
    assert client.calls == []
    assert results[0]["task_id"] == "a"


@pytest.mark.asyncio
async def test_tasks_of_different_owners_fall_back_to_the_single_photo_path(monkeypatch):
    strategy, client = _strategy(monkeypatch)
    strategy.process = AsyncMock(return_value={"status": "completed"})

    results = await _run(strategy, [_task("a", owner_id="owner-1"), _task("b", owner_id="owner-2")])

    assert strategy.process.await_count == 2
    assert client.calls == []
    assert len(results) == 2


@pytest.mark.asyncio
async def test_a_task_without_a_photo_falls_back_to_the_single_photo_path(monkeypatch):
    strategy, client = _strategy(monkeypatch)
    strategy.process = AsyncMock(return_value={"status": "completed"})

    await _run(strategy, [_task("a"), _task("b", payload={"note": "no photo"})])

    assert strategy.process.await_count == 2
    assert client.calls == []


@pytest.mark.asyncio
async def test_the_builtin_connection_falls_back_to_the_single_photo_path(monkeypatch):
    strategy, client = _strategy(monkeypatch, connection_id="builtin")
    strategy.process = AsyncMock(return_value={"status": "completed"})

    await _run(strategy, [_task("a"), _task("b")])

    assert strategy.process.await_count == 2
    assert client.calls == []


@pytest.mark.asyncio
async def test_screenshots_are_skipped_without_calling_the_model(monkeypatch):
    strategy, client = _strategy(monkeypatch, photos={
        "a": (_photo("photo-a", ImageType.SCREENSHOT), None),
        "b": (_photo("photo-b"), None),
    })

    results = await _run(strategy, [_task("a"), _task("b")])

    skipped = [row for row in results if row["result"].get("status") == "skipped"]
    assert skipped and skipped[0]["result"]["reason"] == "screenshot not supported"
    assert len(client.calls) == 1


@pytest.mark.asyncio
async def test_a_missing_photo_file_fails_only_that_task(monkeypatch):
    strategy, client = _strategy(monkeypatch, image_content=None)

    results = await _run(strategy, [_task("a"), _task("b")])

    assert all(row["status"] == "failed" for row in results)
    assert results[0]["result"]["error"] == "file not found"
    assert client.calls == []


@pytest.mark.asyncio
async def test_a_broken_model_reply_marks_every_photo_for_a_single_retry(monkeypatch):
    strategy, client = _strategy(monkeypatch, reply="这不是 JSON")

    results = await _run(strategy, [_task("a"), _task("b")])

    assert all(row["status"] == "failed" for row in results)
    assert all(row["retry_as_single"] is True for row in results)
    assert len(client.calls) == 1


@pytest.mark.asyncio
async def test_a_reply_without_a_json_object_is_rejected(monkeypatch):
    strategy, _ = _strategy(monkeypatch, reply="[]")

    results = await _run(strategy, [_task("a"), _task("b")])

    assert all(row["status"] == "failed" for row in results)
    assert results[0]["result"]["error"] == "模型未返回批量 JSON 结果"
    assert results[0]["retry_as_single"] is True


@pytest.mark.asyncio
async def test_a_successful_batch_labels_every_photo_with_its_number(monkeypatch):
    reply = json.dumps({"1": VALID_RESULT, "2": VALID_RESULT}, ensure_ascii=False)
    strategy, client = _strategy(monkeypatch, reply=reply)

    results = await _run(strategy, [_task("a"), _task("b")])

    assert [row["status"] for row in results] == ["completed", "completed"]
    parts = client.calls[0][-1]["content"]
    user_message = "".join(part["text"] for part in parts)
    assert "照片编号：1" in user_message
    assert "照片编号：2" in user_message



@pytest.mark.asyncio
async def test_a_lookup_error_is_recorded_for_that_photo_only(monkeypatch):
    strategy, client = _strategy(monkeypatch, photos={
        "a": (_photo("photo-a"), None),
    })

    def fake_task_photo(self, task, db):
        if task.id == "b":
            raise RuntimeError("数据库忙")
        return _photo("photo-a"), None

    monkeypatch.setattr(VisualDescriptionStrategy, "_task_photo", fake_task_photo)

    results = await _run(strategy, [_task("a"), _task("b")])

    assert results[0]["status"] == "completed"
    assert results[1]["status"] == "failed"
    assert "数据库忙" in results[1]["result"]["error"]



