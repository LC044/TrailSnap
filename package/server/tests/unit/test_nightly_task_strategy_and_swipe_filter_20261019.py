"""Nightly coverage for the daily-frame task strategy, the swipe-filter HTTP
edge cases and the worker cancel-isolation helper."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.api import swipe_filter as swipe_filter_api
from app.service import task_runtime
from app.service.tasks import daily_frame as daily_frame_tasks
from app.service.daily_frame_render import RenderCancelled


pytestmark = [pytest.mark.smoke]


# ---------------------------------------------------------------------------
# DailyFrameRenderStrategy -- covers 54.5% line coverage (task_category,
# resource_key, timeout, max_attempts, process, process_batch outcomes).
# ---------------------------------------------------------------------------


def _strategy() -> daily_frame_tasks.DailyFrameRenderStrategy:
    return daily_frame_tasks.DailyFrameRenderStrategy()


def test_daily_frame_render_strategy_metadata_is_stable():
    s = _strategy()
    assert s.task_category == "CPU"
    assert s.resource_key == "daily_frame_render"
    assert s.timeout == 4 * 60 * 60
    assert s.max_attempts == 1


def test_daily_frame_render_strategy_process_renders_work(monkeypatch):
    render_calls = []

    def fake_render(work_id, generation, task_id):
        render_calls.append((work_id, generation, task_id))
        return {"output": "ok"}

    monkeypatch.setattr(daily_frame_tasks, "render_work", fake_render)

    work_id = uuid4()
    task_id = uuid4()
    task = SimpleNamespace(id=task_id, payload={"work_id": str(work_id), "generation": 3})

    result = asyncio.run(_strategy().process(worker=None, task=task, db=None))

    assert result == {"output": "ok"}
    assert render_calls == [(work_id, 3, task_id)]


def test_daily_frame_render_strategy_process_batch_marks_outcomes(monkeypatch):
    strategy = _strategy()

    completed_task = SimpleNamespace(id=uuid4(), type="render_daily_frame", payload={"work_id": str(uuid4()), "generation": 1})
    cancelled_task = SimpleNamespace(id=uuid4(), type="render_daily_frame", payload={"work_id": str(uuid4()), "generation": 1})
    failed_task = SimpleNamespace(id=uuid4(), type="render_daily_frame", payload={"work_id": str(uuid4()), "generation": 1})

    async def fake_process(worker, task, db):
        if task is cancelled_task:
            raise RenderCancelled()
        if task is failed_task:
            raise RuntimeError("ffmpeg exit 1")
        return {"output": f"ok-{task.id}"}

    monkeypatch.setattr(strategy, "process", fake_process)

    results = asyncio.run(strategy.process_batch(worker=None, tasks=[completed_task, cancelled_task, failed_task], db=None))

    assert [r["status"] for r in results] == ["completed", "cancelled", "failed"]
    assert results[0]["result"] == {"output": f"ok-{completed_task.id}"}
    assert results[1]["result"] == {}
    assert results[2].get("error") == "影片生成失败，请查看作品详情"


# ---------------------------------------------------------------------------
# api/swipe_filter -- 404 (LookupError) / 409 (ValueError) boundaries plus
# undo / reset happy paths.
# ---------------------------------------------------------------------------


def _user():
    return SimpleNamespace(id=uuid4())


def test_swipe_filter_decisions_lookup_error_becomes_404():
    db = MagicMock()
    user = _user()
    payload = MagicMock(items=[SimpleNamespace(photo_id=uuid4(), action="keep")])

    with patch.object(swipe_filter_api.crud, "save_decisions", side_effect=LookupError("missing")):
        with pytest.raises(Exception) as exc_info:
            swipe_filter_api.save_swipe_filter_decisions(payload=payload, db=db, current_user=user)

    assert exc_info.value.status_code == 404
    assert "missing" in str(exc_info.value.detail)


def test_swipe_filter_decisions_value_error_becomes_409():
    db = MagicMock()
    user = _user()
    payload = MagicMock(items=[SimpleNamespace(photo_id=uuid4(), action="keep")])

    with patch.object(swipe_filter_api.crud, "save_decisions", side_effect=ValueError("dup")):
        with pytest.raises(Exception) as exc_info:
            swipe_filter_api.save_swipe_filter_decisions(payload=payload, db=db, current_user=user)

    assert exc_info.value.status_code == 409
    assert "dup" in str(exc_info.value.detail)


def test_swipe_filter_decisions_returns_updated_count():
    db = MagicMock()
    user = _user()
    payload = MagicMock(items=[SimpleNamespace(photo_id=uuid4(), action="keep")])

    with patch.object(swipe_filter_api.crud, "save_decisions", return_value=3):
        response = swipe_filter_api.save_swipe_filter_decisions(payload=payload, db=db, current_user=user)

    assert response.data["updated"] == 3


def test_swipe_filter_undo_forwards_user_and_photo():
    db = MagicMock()
    user = _user()
    photo_id = uuid4()

    with patch.object(swipe_filter_api.crud, "undo_decision", return_value=True) as undo:
        response = swipe_filter_api.undo_swipe_filter_decision(photo_id=photo_id, db=db, current_user=user)

    undo.assert_called_once_with(db, user.id, photo_id)
    assert response.data["undone"] is True


def test_swipe_filter_reset_forwards_user():
    db = MagicMock()
    user = _user()

    with patch.object(swipe_filter_api.crud, "reset_decisions", return_value=5) as reset:
        response = swipe_filter_api.reset_swipe_filter_decisions(db=db, current_user=user)

    reset.assert_called_once_with(db, user.id)
    assert response.data["reset"] == 5


# ---------------------------------------------------------------------------
# service/task_runtime -- await_owned must wait until the underlying future
# actually finishes before propagating CancelledError.
# ---------------------------------------------------------------------------


def test_await_owned_propagates_normal_result():
    async def runner():
        return await task_runtime.await_owned(asyncio.sleep(0, result="ok"))

    assert asyncio.run(runner()) == "ok"


def test_await_owned_raises_cancelled_after_cancel():
    async def runner():
        task = asyncio.ensure_future(task_runtime.await_owned(asyncio.sleep(60)))
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(runner())


def test_run_in_executor_owned_runs_function():
    def add(a, b):
        return a + b

    async def runner():
        return await task_runtime.run_in_executor_owned(None, add, 2, 3)

    assert asyncio.run(runner()) == 5
