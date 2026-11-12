import asyncio
from unittest.mock import AsyncMock

import pytest

from app.service import task_event_stream as stream

pytestmark = pytest.mark.smoke


@pytest.fixture
def clock(monkeypatch):
    class Clock:
        now = 0.0

        def time(self):
            return self.now

    clock = Clock()
    monkeypatch.setattr(stream.asyncio, 'get_running_loop', lambda: clock)

    async def wait_for(coro, timeout):
        try:
            result = await coro
        except asyncio.TimeoutError:
            clock.now += timeout
            raise
        clock.now += 0.5
        return result

    monkeypatch.setattr(stream.asyncio, 'wait_for', wait_for)
    return clock


class Queue:
    def __init__(self, messages):
        self.messages = list(messages)

    async def get(self):
        if not self.messages:
            raise asyncio.TimeoutError
        return self.messages.pop(0)


def task(status, task_id='a'):
    return {'event': 'task.updated', 'data': {'id': task_id, 'status': status}}


@pytest.mark.asyncio
async def test_final_batch_flushes_without_further_events(clock):
    request = AsyncMock()
    request.is_disconnected.return_value = False
    iterator = stream.task_event_stream(Queue([task('processing'), task('completed')]), request, batch=True)
    batch = await anext(iterator)
    assert clock.now == 4.5
    assert batch == {'event': 'task.batch', 'data': {'events': [task('completed')]}}
    await iterator.aclose()


@pytest.mark.asyncio
async def test_continuous_queue_does_not_postpone_deadline(clock):
    request = AsyncMock()
    request.is_disconnected.return_value = False
    iterator = stream.task_event_stream(Queue([task('processing', str(i)) for i in range(40)]), request, batch=True)
    first = await anext(iterator)
    assert clock.now == 4.5
    second = await anext(iterator)
    assert clock.now == 9.0
    assert len(first['data']['events']) == 9
    assert len(second['data']['events']) == 9
    await iterator.aclose()


@pytest.mark.asyncio
async def test_notifications_are_immediate_and_tasks_still_flush(clock):
    notification = {'event': 'notification.created', 'data': {'id': 'n'}}
    request = AsyncMock()
    request.is_disconnected.return_value = False
    iterator = stream.task_event_stream(Queue([task('completed'), notification]), request, batch=True)
    assert await anext(iterator) == notification
    assert clock.now == 1.0
    assert (await anext(iterator))['event'] == 'task.batch'
    request.is_disconnected.return_value = True
    with pytest.raises(StopAsyncIteration):
        await anext(iterator)


@pytest.mark.asyncio
async def test_legacy_clients_keep_single_events(clock):
    request = AsyncMock()
    request.is_disconnected.return_value = False
    iterator = stream.task_event_stream(Queue([task('completed')]), request)
    assert await anext(iterator) == task('completed')
    assert clock.now == 0.5
    await iterator.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize('name', ['tasks', 'notification'])
async def test_routes_negotiate_batch_format_and_unsubscribe(monkeypatch, name):
    import importlib
    import json
    from unittest.mock import MagicMock

    api = importlib.import_module('app.api.' + name)
    request = AsyncMock()
    request.is_disconnected.return_value = False
    queue = asyncio.Queue()
    queue.put_nowait(task('completed'))
    manager = MagicMock()
    manager.subscribe.return_value = queue
    monkeypatch.setattr(stream, 'TASK_EVENT_INTERVAL', 0)
    if name == 'tasks':
        monkeypatch.setattr(api, '_resolve_user_from_token', MagicMock())
        monkeypatch.setattr(api.TaskManager, 'get_instance', lambda: manager)
        route = api.task_events
    else:
        monkeypatch.setattr(api, 'resolve_user_from_token', MagicMock())
        monkeypatch.setattr(api.NotificationManager, 'get_instance', lambda: manager)
        route = api.notification_events
    response = await route(request, token='test', db=MagicMock(), batch=True)
    iterator = response.body_iterator
    assert (await anext(iterator))['event'] == 'hello'
    batch = await anext(iterator)
    assert batch['event'] == 'task.batch'
    assert json.loads(batch['data'])['events'] == [task('completed')]
    await iterator.aclose()
    manager.unsubscribe.assert_called_once_with(queue)
