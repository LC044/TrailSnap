"""Coalesce task changes without delaying persistent notifications."""
import asyncio

TASK_EVENT_INTERVAL = 4.0
TASK_ROW_EVENTS = {'task.updated', 'task.created', 'task.retry'}


async def task_event_stream(queue, request, *, batch=False, default_event='task.updated'):
    loop = asyncio.get_running_loop()
    pending = {}
    deadline = None
    while not await request.is_disconnected():
        # Check before reading: a continuously nonempty queue must not starve flushes.
        if deadline is not None and loop.time() >= deadline:
            yield {'event': 'task.batch', 'data': {'events': list(pending.values())}}
            pending.clear()
            deadline = None
            continue
        timeout = max(0, deadline - loop.time()) if deadline is not None else 15.0
        try:
            msg = await asyncio.wait_for(queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            if deadline is None:
                yield {'event': 'ping', 'data': {}}
            continue
        event = msg.get('event', default_event)
        data = msg.get('data') or {}
        if batch and event in TASK_ROW_EVENTS:
            # Tasks without IDs still invalidate summaries; retain one per type/owner.
            key = (str(data.get('owner_id')), data.get('id') or data.get('type'))
            pending[key] = {'event': event, 'data': data}
            if deadline is None:
                deadline = loop.time() + TASK_EVENT_INTERVAL
        else:
            yield {'event': event, 'data': data}
