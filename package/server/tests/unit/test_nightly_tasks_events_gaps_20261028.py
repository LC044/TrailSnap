"""2026-10-28 nightly coverage for ``app/api/tasks.py`` SSE event stream.

The 2026-10-28 backend coverage scan reported ``api/tasks.py`` with 19
uncovered lines, all inside the task SSE endpoint and its token helper.

``EventSource`` cannot send an ``Authorization`` header, so the endpoint
accepts the token as a query parameter and validates it *before* opening the
stream.  If that validation is skipped the browser receives an endless empty
stream instead of a 401, which looks like a hung UI.  The tests therefore
assert the three outcomes that matter: a missing token is rejected, an invalid
token is rejected, and a valid token opens a stream that greets the client and
then unsubscribes from the task manager.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException


pytestmark = [pytest.mark.smoke]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _tasks():
    from app.api import tasks

    return tasks


class _Request:
    """A request stub whose ``is_disconnected`` flips on demand."""

    def __init__(self):
        self.disconnected = False

    async def is_disconnected(self):
        return self.disconnected


# ---------------------------------------------------------------------------
# _resolve_user_from_token
# ---------------------------------------------------------------------------


def test_resolve_user_from_token_delegates_with_the_sse_scope():
    tasks = _tasks()
    db = MagicMock()
    user = MagicMock()

    with patch.object(tasks, "resolve_user_from_token", return_value=user) as resolve:
        result = tasks._resolve_user_from_token("tok", db)

    resolve.assert_called_once_with("tok", db, method="GET", path="/tasks/events")
    assert result is user


# ---------------------------------------------------------------------------
# task_events
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_task_events_requires_a_token():
    tasks = _tasks()

    with pytest.raises(HTTPException) as excinfo:
        await tasks.task_events(_Request(), token=None, db=MagicMock())

    assert excinfo.value.status_code == 401


@pytest.mark.asyncio
async def test_task_events_rejects_an_invalid_token_before_streaming():
    tasks = _tasks()
    manager = MagicMock()

    with patch.object(tasks, "_resolve_user_from_token", side_effect=HTTPException(401, "bad token")), \
            patch.object(tasks.TaskManager, "get_instance", return_value=manager):
        with pytest.raises(HTTPException) as excinfo:
            await tasks.task_events(_Request(), token="bad", db=MagicMock())

    assert excinfo.value.status_code == 401
    manager.subscribe.assert_not_called()


@pytest.mark.asyncio
async def test_task_events_greets_the_client_and_unsubscribes_on_disconnect():
    tasks = _tasks()
    request = _Request()
    queue = asyncio.Queue()
    manager = MagicMock()
    manager.subscribe.return_value = queue

    with patch.object(tasks, "_resolve_user_from_token", return_value=MagicMock()), \
            patch.object(tasks.TaskManager, "get_instance", return_value=manager):
        response = await tasks.task_events(request, token="tok", db=MagicMock())

    manager.subscribe.assert_called_once()

    iterator = response.body_iterator
    greeting = await anext(iterator)
    assert greeting["event"] == "hello"
    assert "ts" in greeting["data"]

    # The client disconnects: the generator must stop and release the queue.
    request.disconnected = True
    with pytest.raises(StopAsyncIteration):
        await anext(iterator)

    manager.unsubscribe.assert_called_once_with(queue)


@pytest.mark.asyncio
async def test_task_events_forwards_a_queued_task_update():
    tasks = _tasks()
    request = _Request()
    queue = asyncio.Queue()
    manager = MagicMock()
    manager.subscribe.return_value = queue

    with patch.object(tasks, "_resolve_user_from_token", return_value=MagicMock()), \
            patch.object(tasks.TaskManager, "get_instance", return_value=manager):
        response = await tasks.task_events(request, token="tok", db=MagicMock())

    await queue.put({"event": "task.updated", "data": {"id": "task-1"}})

    iterator = response.body_iterator
    await anext(iterator)  # hello
    update = await anext(iterator)

    assert update["event"] == "task.updated"
    assert "task-1" in update["data"]



