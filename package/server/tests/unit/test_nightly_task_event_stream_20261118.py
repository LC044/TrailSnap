"""2026-11-18 nightly coverage for ``app/service/task_event_stream.py``.

No test file referenced ``app/service/task_event_stream.py``.  The stream is
what keeps the browser's task list live, and it has two behaviours that are
easy to break:

* task-row events are coalesced into a ``task.batch`` event so a burst of
  updates does not flood the client;
* every other event is forwarded immediately, and an idle stream emits a
  ``ping`` so proxies keep the connection open.

The tests drive the generator with a fake request and a real queue.
"""

from __future__ import annotations

import asyncio

import pytest

from app.service.task_event_stream import TASK_EVENT_INTERVAL, task_event_stream


pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


class _Request:
    """A request whose ``is_disconnected`` flips after ``disconnect_after`` reads."""

    def __init__(self, disconnect_after: int = 100):
        self._remaining = disconnect_after

    async def is_disconnected(self) -> bool:
        if self._remaining <= 0:
            return True
        self._remaining -= 1
        return False


async def _drain(queue, request, count, *, batch=False):
    stream = task_event_stream(queue, request, batch=batch)
    events = []
    for _ in range(count):
        try:
            events.append(await asyncio.wait_for(stream.__anext__(), timeout=5))
        except StopAsyncIteration:
            break
        except asyncio.TimeoutError:
            break
    await stream.aclose()
    return events


@pytest.mark.asyncio
async def test_a_task_row_event_is_forwarded_immediately_without_batching():
    queue = asyncio.Queue()
    await queue.put({"event": "task.updated", "data": {"id": "a", "owner_id": "o"}})

    events = await _drain(queue, _Request(), 1)

    assert events == [{"event": "task.updated", "data": {"id": "a", "owner_id": "o"}}]


@pytest.mark.asyncio
async def test_task_row_events_are_coalesced_into_one_batch():
    queue = asyncio.Queue()
    await queue.put({"event": "task.updated", "data": {"id": "a", "owner_id": "o"}})
    await queue.put({"event": "task.created", "data": {"id": "b", "owner_id": "o"}})

    stream = task_event_stream(queue, _Request(), batch=True)
    # The first two messages are absorbed into the pending buffer.
    first = await asyncio.wait_for(stream.__anext__(), timeout=5)
    await stream.aclose()

    assert first["event"] == "task.batch"
    assert {item["event"] for item in first["data"]["events"]} == {"task.updated", "task.created"}


@pytest.mark.asyncio
async def test_a_non_row_event_is_forwarded_even_when_batching():
    queue = asyncio.Queue()
    await queue.put({"event": "notification.created", "data": {"id": "n"}})

    events = await _drain(queue, _Request(), 1, batch=True)

    assert events == [{"event": "notification.created", "data": {"id": "n"}}]


@pytest.mark.asyncio
async def test_a_message_without_an_event_uses_the_default_event():
    queue = asyncio.Queue()
    await queue.put({"data": {"id": "x"}})

    events = await _drain(queue, _Request(), 1)

    assert events == [{"event": "task.updated", "data": {"id": "x"}}]


@pytest.mark.asyncio
async def test_a_message_without_data_sends_an_empty_payload():
    queue = asyncio.Queue()
    await queue.put({"event": "notification.created"})

    events = await _drain(queue, _Request(), 1)

    assert events == [{"event": "notification.created", "data": {}}]


@pytest.mark.asyncio
async def test_the_batch_interval_is_the_documented_one():
    assert TASK_EVENT_INTERVAL == 4.0


@pytest.mark.asyncio
async def test_the_stream_stops_when_the_client_disconnects():
    queue = asyncio.Queue()
    request = _Request(disconnect_after=0)

    events = await _drain(queue, request, 3)

    assert events == []


@pytest.mark.asyncio
async def test_the_pending_batch_is_flushed_after_the_batch_interval(monkeypatch):
    """A burst of row events is emitted as one ``task.batch`` after the window."""
    monkeypatch.setattr("app.service.task_event_stream.TASK_EVENT_INTERVAL", 0.05)
    queue = asyncio.Queue()
    await queue.put({"event": "task.updated", "data": {"id": "a", "owner_id": "o"}})

    stream = task_event_stream(queue, _Request(), batch=True)
    events = []
    for _ in range(2):
        try:
            events.append(await asyncio.wait_for(stream.__anext__(), timeout=5))
        except (StopAsyncIteration, asyncio.TimeoutError):
            break
    await stream.aclose()

    assert events and events[0]["event"] == "task.batch"
    assert events[0]["data"]["events"] == [{"event": "task.updated", "data": {"id": "a", "owner_id": "o"}}]


@pytest.mark.asyncio
async def test_the_same_owner_keeps_only_one_pending_entry_per_task(monkeypatch):
    monkeypatch.setattr("app.service.task_event_stream.TASK_EVENT_INTERVAL", 0.05)
    queue = asyncio.Queue()
    await queue.put({"event": "task.updated", "data": {"id": "a", "owner_id": "o", "progress": 1}})
    await queue.put({"event": "task.updated", "data": {"id": "a", "owner_id": "o", "progress": 2}})

    stream = task_event_stream(queue, _Request(), batch=True)
    events = []
    for _ in range(2):
        try:
            events.append(await asyncio.wait_for(stream.__anext__(), timeout=5))
        except (StopAsyncIteration, asyncio.TimeoutError):
            break
    await stream.aclose()

    assert events and events[0]["event"] == "task.batch"
    assert len(events[0]["data"]["events"]) == 1
    assert events[0]["data"]["events"][0]["data"]["progress"] == 2

