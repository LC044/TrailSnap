"""Unit coverage for task-manager pub/sub and worker cold starts."""

from unittest.mock import patch

import pytest

from app.service.task_manager import TaskManager


pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


def test_publish_event_delivers_envelope_and_unsubscribe_stops_delivery():
    manager = TaskManager()
    queue = manager.subscribe()

    with patch("app.service.notification_manager.NotificationManager.get_instance") as get_notifications:
        manager.publish_event("task.updated", {"id": "task-1"})

    assert queue.get_nowait() == {
        "event": "task.updated",
        "data": {"id": "task-1"},
    }
    get_notifications.return_value.publish_to_user.assert_called_once()

    manager.unsubscribe(queue)
    manager.publish_event("task.updated", {"id": "task-2"})
    assert queue.empty()


def test_publish_event_drops_oldest_item_when_subscriber_queue_is_full():
    manager = TaskManager()
    queue = manager.subscribe()
    for index in range(queue.maxsize):
        queue.put_nowait({"event": "old", "data": {"index": index}})

    with patch("app.service.notification_manager.NotificationManager.get_instance"):
        manager.publish_event("task.updated", {"id": "latest"})

    assert queue.qsize() == queue.maxsize
    assert queue.get_nowait()["data"]["index"] == 1
    last = None
    while not queue.empty():
        last = queue.get_nowait()
    assert last == {"event": "task.updated", "data": {"id": "latest"}}


def test_start_worker_publishes_snapshot_only_after_actual_start():
    manager = TaskManager()

    with patch.object(manager, "_start_worker_locked", side_effect=[False, True]) as start, patch.object(
        manager, "_publish_active_tasks_snapshot"
    ) as snapshot:
        manager.start_worker_if_needed()
        snapshot.assert_not_called()

        manager.start_worker_if_needed()

    assert start.call_count == 2
    snapshot.assert_called_once_with()
