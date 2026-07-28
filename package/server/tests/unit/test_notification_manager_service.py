"""Unit coverage for user-scoped notification pub/sub."""

from unittest.mock import MagicMock

import pytest

from app.service.notification_manager import NotificationManager


pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


def test_targeted_publish_reaches_matching_and_legacy_broadcast_subscribers():
    manager = NotificationManager()
    alice = manager.subscribe("alice")
    bob = manager.subscribe("bob")
    legacy = manager.subscribe(None)

    manager.publish_to_user("alice", "notification.created", {"id": 7})

    expected = {"event": "notification.created", "data": {"id": 7}}
    assert alice.get_nowait() == expected
    assert bob.empty()
    assert legacy.get_nowait() == expected


def test_none_user_broadcasts_to_every_subscriber():
    manager = NotificationManager()
    queues = [manager.subscribe("alice"), manager.subscribe("bob")]

    manager.publish_to_user(None, "system.notice", {"message": "maintenance"})

    for queue in queues:
        assert queue.get_nowait() == {
            "event": "system.notice",
            "data": {"message": "maintenance"},
        }


def test_attached_loop_schedules_publish_and_unsubscribe_removes_queue():
    manager = NotificationManager()
    queue = manager.subscribe("alice")
    loop = MagicMock()
    manager.attach_loop(loop)

    manager.publish_to_user("alice", "notification.read", {"id": 3})

    loop.call_soon_threadsafe.assert_called_once_with(
        manager._do_publish,
        "alice",
        "notification.read",
        {"id": 3},
    )
    assert queue.empty()

    manager.unsubscribe(queue)
    assert manager._subscribers == []
