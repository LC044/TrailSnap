"""Nightly gap-fill tests for app/api/notification.py SSE stream.

Targets the /notifications/events endpoint and its inner event_generator
(lines 76-100 of the source file), which were never covered by the existing
test_notification_api.py suite. All behaviour is verified by patching
resolve_user_from_token + NotificationManager.get_instance (no DB, no real
SSE client).

The generator emits:
- a hello event right after subscription;
- a real message from the per-user queue when one arrives;
- a ping keep-alive every 15s if no message arrived;
- and finally unsubscribes on disconnect / generator close.
"""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sse_starlette.sse import EventSourceResponse

from app.api import notification as notif_api
from app.service import notification_manager as notif_mgr


pytestmark = [pytest.mark.smoke, pytest.mark.regression]


def _user():
    return SimpleNamespace(id=uuid4(), is_superuser=False)


def _make_fake_request(*, disconnected: bool = False) -> MagicMock:
    """request.is_disconnected is awaited inside the generator."""

    async def _is_disconnected():
        return disconnected

    req = MagicMock()
    req.is_disconnected = _is_disconnected
    return req


async def _take_n(gen, n: int):
    """Collect at most ``n`` items from an async generator.

    Always calls ``aclose()`` on exit so the underlying task is cleaned up
    before the test ends - otherwise pytest-asyncio's loop may hang waiting
    for the pending generator coroutine.
    """

    taken = []
    try:
        async for item in gen:
            taken.append(item)
            if len(taken) >= n:
                break
    finally:
        aclose = getattr(gen, "aclose", None)
        if aclose is not None:
            await aclose()
    return taken


@pytest.mark.asyncio
async def test_notification_events_raises_401_when_token_missing():
    """Missing token query param should fail fast with HTTP 401."""

    req = _make_fake_request()
    db = MagicMock()
    with pytest.raises(HTTPException) as exc_info:
        # token=None (default) -> branch into 401
        await notif_api.notification_events(request=req, token=None, db=db)
    assert exc_info.value.status_code == 401
    assert "token" in str(exc_info.value.detail).lower()


@pytest.mark.asyncio
async def test_notification_events_yields_hello_then_message_then_unsubscribes():
    """Happy path: hello, a queue message, and finally unsubscribe."""

    user = _user()
    req = _make_fake_request()
    db = MagicMock()
    q: asyncio.Queue = asyncio.Queue()
    await q.put({"event": "task.updated", "data": {"id": "abc", "progress": 42}})

    fake_manager = MagicMock()
    fake_manager.subscribe.return_value = q

    with patch.object(notif_api, "resolve_user_from_token", return_value=user), \
         patch.object(notif_mgr.NotificationManager, "get_instance", return_value=fake_manager):
        response = await notif_api.notification_events(request=req, token="t", db=db)

    assert isinstance(response, EventSourceResponse)

    events = await _take_n(response.body_iterator, n=2)

    # 1) hello
    assert events[0]["event"] == "hello"
    hello_payload = json.loads(events[0]["data"])
    assert "ts" in hello_payload

    # 2) forwarded queue message
    assert events[1]["event"] == "task.updated"
    msg_payload = json.loads(events[1]["data"])
    assert msg_payload == {"id": "abc", "progress": 42}

    # generator must have unsubscribed the queue before returning
    fake_manager.unsubscribe.assert_called_once_with(q)


@pytest.mark.asyncio
async def test_notification_events_falls_back_to_default_event_when_missing():
    """Queue payload without event key defaults to notification.created."""

    user = _user()
    req = _make_fake_request()
    db = MagicMock()
    q: asyncio.Queue = asyncio.Queue()
    await q.put({"data": {"foo": "bar"}})  # no event field

    fake_manager = MagicMock()
    fake_manager.subscribe.return_value = q

    with patch.object(notif_api, "resolve_user_from_token", return_value=user), \
         patch.object(notif_mgr.NotificationManager, "get_instance", return_value=fake_manager):
        response = await notif_api.notification_events(request=req, token="t", db=db)

    events = await _take_n(response.body_iterator, n=2)
    assert events[0]["event"] == "hello"
    assert events[1]["event"] == "notification.created"
    assert json.loads(events[1]["data"]) == {"foo": "bar"}
    fake_manager.unsubscribe.assert_called_once_with(q)


@pytest.mark.asyncio
async def test_notification_events_emits_ping_on_queue_timeout():
    """If the queue stays empty past the wait_for timeout, emit a ping.

    We replace ``queue.get`` with an awaitable that raises ``asyncio.TimeoutError``
    immediately so the generator falls into the ping branch without waiting
    the real 15 seconds.
    """

    user = _user()
    req = _make_fake_request()
    db = MagicMock()
    q: asyncio.Queue = asyncio.Queue()  # never written to

    fake_manager = MagicMock()
    fake_manager.subscribe.return_value = q

    class _GetTimeout:
        """Awaitable that always raises TimeoutError when awaited."""

        def __await__(self):
            async def _coro():
                raise asyncio.TimeoutError()
            return _coro().__await__()

    def _raise_timeout():
        return _GetTimeout()

    q.get = _raise_timeout  # type: ignore[assignment]

    with patch.object(notif_api, "resolve_user_from_token", return_value=user), \
         patch.object(notif_mgr.NotificationManager, "get_instance", return_value=fake_manager):
        response = await notif_api.notification_events(request=req, token="t", db=db)

    events = await _take_n(response.body_iterator, n=2)
    assert events[0]["event"] == "hello"
    assert events[1]["event"] == "ping"
    ping_payload = json.loads(events[1]["data"])
    assert "ts" in ping_payload
    fake_manager.unsubscribe.assert_called_once_with(q)


@pytest.mark.asyncio
async def test_notification_events_breaks_when_client_disconnects():
    """A disconnected request should make the generator exit and unsubscribe."""

    user = _user()
    req = _make_fake_request(disconnected=True)
    db = MagicMock()
    q: asyncio.Queue = asyncio.Queue()

    fake_manager = MagicMock()
    fake_manager.subscribe.return_value = q

    with patch.object(notif_api, "resolve_user_from_token", return_value=user), \
         patch.object(notif_mgr.NotificationManager, "get_instance", return_value=fake_manager):
        response = await notif_api.notification_events(request=req, token="t", db=db)

    # Only the initial hello should be yielded before the disconnect branch
    # breaks out of the while-loop and the finally block unsubscribes.
    events = await _take_n(response.body_iterator, n=2)
    assert len(events) == 1
    assert events[0]["event"] == "hello"
    fake_manager.unsubscribe.assert_called_once_with(q)
