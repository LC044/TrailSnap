"""2026-11-16 nightly coverage for ``app/service/notification_manager.py``.

The 2026-11-16 backend coverage scan reported
``service/notification_manager.py`` at 95.8% with 2 missed lines: the
inner ``except Exception: pass`` that guards dropping the oldest event of
a full subscriber queue (lines 82-83).

A subscriber that disappears between the "queue is full" check and the
``get_nowait()`` call must never break the publisher.
"""

from __future__ import annotations

import asyncio

import pytest

from app.service.notification_manager import NotificationManager


pytestmark = [pytest.mark.smoke]


class _BrokenQueue:
    """A subscriber queue that fails as soon as the publisher touches it."""

    def full(self):
        return True

    def get_nowait(self):
        raise RuntimeError("subscriber went away")

    def put_nowait(self, item):
        raise AssertionError("unreachable")


def test_publish_survives_a_broken_subscriber_queue():
    manager = NotificationManager()
    manager.subscribe("user-1").put_nowait({"event": "old", "data": {}})
    manager._subscribers.append(("user-1", _BrokenQueue()))

    manager.publish_to_user("user-1", "task.done", {"ok": True})

    # The healthy subscriber still received the event after the broken one.
    healthy = manager._subscribers[0][1]
    received = [healthy.get_nowait() for _ in range(healthy.qsize())]
    assert received[-1] == {"event": "task.done", "data": {"ok": True}}


def test_publish_ignores_subscribers_of_other_users():
    manager = NotificationManager()
    other = manager.subscribe("user-2")
    manager.publish_to_user("user-1", "task.done", {"ok": True})

    assert other.empty()


def test_publish_broadcasts_when_no_user_is_given():
    manager = NotificationManager()
    queue = manager.subscribe("user-1")
    manager.publish_to_user(None, "system.info", {"ok": True})

    assert queue.get_nowait() == {"event": "system.info", "data": {"ok": True}}


def test_unsubscribe_removes_the_queue():
    manager = NotificationManager()
    queue = manager.subscribe("user-1")
    manager.unsubscribe(queue)
    manager.publish_to_user("user-1", "task.done", {"ok": True})

    assert queue.empty()


@pytest.mark.asyncio
async def test_publish_from_a_running_loop_is_delivered():
    manager = NotificationManager()
    manager.attach_loop(asyncio.get_running_loop())
    queue = manager.subscribe("user-1")
    manager.publish_to_user("user-1", "task.done", {"ok": True})
    await asyncio.sleep(0)

    assert queue.get_nowait() == {"event": "task.done", "data": {"ok": True}}

