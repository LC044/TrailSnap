"""Unit tests for app/service/notification_manager.py.

``NotificationManager`` is a singleton pub/sub: each subscribe creates a
queue, publish_to_user only delivers to the matching user (or broadcasts
when user_id is None), and put_nowait must drop the oldest item when the
queue is full. The manager also supports being called from a non-loop
thread (call_soon_threadsafe) — we exercise that path by attaching a
fake loop.
"""

import asyncio
from unittest.mock import MagicMock

import pytest

pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


@pytest.fixture
def manager():
    # Reset the singleton so each test gets a fresh state.
    from app.service.notification_manager import NotificationManager
    NotificationManager._instance = None
    return NotificationManager.get_instance()


def test_get_instance_returns_singleton():
    from app.service.notification_manager import NotificationManager
    NotificationManager._instance = None
    a = NotificationManager.get_instance()
    b = NotificationManager.get_instance()
    assert a is b


def test_subscribe_returns_queue_and_keeps_subscriber(manager):
    q = manager.subscribe(user_id=42)
    assert isinstance(q, asyncio.Queue)
    assert (42, q) in manager._subscribers


def test_publish_to_user_filters_by_user_id(manager):
    q_alice = manager.subscribe(user_id="alice")
    q_bob = manager.subscribe(user_id="bob")
    manager._loop = None  # exercise the direct path

    manager.publish_to_user("alice", "notification.created", {"x": 1})
    assert not q_alice.empty()
    assert q_bob.empty()
    msg = q_alice.get_nowait()
    assert msg == {"event": "notification.created", "data": {"x": 1}}


def test_publish_to_user_with_none_broadcasts_to_everyone(manager):
    q_a = manager.subscribe(user_id="a")
    q_b = manager.subscribe(user_id="b")
    manager._loop = None
    manager.publish_to_user(None, "system.broadcast", {"ok": True})
    assert not q_a.empty()
    assert not q_b.empty()


def test_unsubscribe_removes_target_queue(manager):
    q = manager.subscribe(user_id=1)
    other = manager.subscribe(user_id=2)
    manager.unsubscribe(q)
    assert (1, q) not in manager._subscribers
    assert (2, other) in manager._subscribers


def test_publish_drops_oldest_when_queue_full(manager):
    """If the queue is full, publish_to_user must evict one item first."""
    q = manager.subscribe(user_id=1)
    # Fill the queue to its cap (256).
    for i in range(q.maxsize):
        q.put_nowait({"event": "fill", "data": {"i": i}})
    manager._loop = None
    manager.publish_to_user(1, "flood", {"i": 999})
    # Queue must still be at maxsize (not overflow).
    assert q.full()
    # The most recent message must be the one we just published.
    last = q.get_nowait()
    # get_nowait pops from head; we may have lost an old one, so the
    # remaining 255 are all from this run, ending with our payload.
    while not q.empty():
        last = q.get_nowait()
    assert last == {"event": "flood", "data": {"i": 999}}


def test_publish_calls_call_soon_threadsafe_when_loop_attached(manager):
    """When attach_loop is set, publish must use call_soon_threadsafe."""
    q = manager.subscribe(user_id=7)
    fake_loop = MagicMock()
    fake_loop.call_soon_threadsafe = MagicMock()
    manager.attach_loop(fake_loop)
    manager.publish_to_user(7, "x", {"y": 2})
    fake_loop.call_soon_threadsafe.assert_called_once()
    # And the queue is still empty (real delivery happens via _do_publish).
    assert q.empty()
