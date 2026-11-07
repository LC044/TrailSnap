"""Second nightly priority-gap pass for 2026-11-07.

The first pass covered view references and the top media/task-worker branches.
This file adds focused guards for remaining low-coverage modules selected by
the fresh unit coverage scan: task_worker, api/media, crud/face and crud/photo.
"""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.api import media as media_api
from app.crud import face as crud_face
from app.crud import photo as crud_photo
from app.db.models.task import TaskType
from app.service import task_worker


pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


def test_task_worker_stop_cancels_tasks_and_shuts_down_pools():
    worker = task_worker.TaskWorker()
    batch_pool = MagicMock(name="batch_pool")
    process_pool = MagicMock(name="process_pool")
    thread_pool = MagicMock(name="thread_pool")
    worker_task = MagicMock(name="worker_task")
    result_task = MagicMock(name="result_task")
    cpu_consumer_task = MagicMock(name="cpu_consumer_task")
    io_consumer_task = MagicMock(name="io_consumer_task")
    ai_consumer_task = MagicMock(name="ai_consumer_task")
    pressure_task = MagicMock(name="pressure_task")
    worker.batch_pool = batch_pool
    worker.process_pool = process_pool
    worker.thread_pool = thread_pool
    worker.worker_task = worker_task
    worker.result_task = result_task
    worker.cpu_consumer_task = cpu_consumer_task
    worker.io_consumer_task = io_consumer_task
    worker.ai_consumer_task = ai_consumer_task
    worker.pressure_task = pressure_task
    worker._save_system_state = MagicMock()

    worker.stop()

    assert worker.running is False
    assert worker.batch_pool is None
    assert worker.process_pool is None
    assert worker.thread_pool is None
    batch_pool.shutdown.assert_called_once_with(wait=False)
    process_pool.shutdown.assert_called_once_with(wait=False)
    thread_pool.shutdown.assert_called_once_with(wait=False)
    for task in (worker_task, result_task, cpu_consumer_task,
                 io_consumer_task, ai_consumer_task, pressure_task):
        task.cancel.assert_called_once_with()
    worker._save_system_state.assert_called_once_with("scan_status", worker.scan_status)


def test_execute_batch_sync_returns_when_database_has_no_pending_rows():
    worker = task_worker.TaskWorker()
    db = MagicMock(name="session")
    task_id = uuid4()

    with patch.object(task_worker, "SessionLocal", return_value=db), patch.object(
        task_worker.crud_task, "get_tasks_by_ids", return_value=[]
    ) as get_tasks:
        result = worker._execute_batch_sync([{"id": task_id, "type": TaskType.PROCESS_BASIC}])

    assert result == ([], None)
    get_tasks.assert_called_once_with(db, [task_id])
    db.close.assert_called_once()


def test_media_add_tasks_marks_live_photo_payload():
    db = MagicMock()
    user_id = uuid4()
    photo_id = uuid4()
    manager = MagicMock()
    task_payload = {
        "photo_id": str(photo_id),
        "file_path": r"C:\photos\IMG_0001.jpg",
        "user_id": str(user_id),
        "is_live_photo": True,
        "live_photo_video_path": r"C:\photos\IMG_0001.mp4",
    }

    with patch.object(media_api.TaskManager, "get_instance", return_value=manager):
        media_api.add_tasks(
            db,
            user_id,
            photo_id,
            task_payload["file_path"],
            task_payload["live_photo_video_path"],
        )

    manager.add_tasks.assert_called_once_with(
        db,
        [{"type": TaskType.PROCESS_BASIC, "payload": task_payload}],
        owner_id=user_id,
    )


def test_live_photo_companion_requires_matching_stem():
    db = MagicMock()
    image_photo = SimpleNamespace(filename="IMG_0001.jpg", file_path=r"C:\photos\IMG_0001.jpg")
    video = SimpleNamespace(filename="different.mp4", file=MagicMock())

    with pytest.raises(ValueError, match="names must match"):
        media_api._attach_live_photo_video(
            db, image_photo, video, companion_backup_key=None, user_id=uuid4()
        )


def test_face_deletion_dependency_reassigns_default_face():
    db = MagicMock()
    identity = SimpleNamespace(id=88, default_face_id=12)
    replacement = SimpleNamespace(id=15)
    face = SimpleNamespace(id=12, photo_id=30, face_cluster_id=None, face_identity_id=88)

    identity_query = MagicMock()
    identity_query.get.return_value = identity
    face_query = MagicMock()
    face_query.filter.return_value.order_by.return_value.first.return_value = replacement
    db.query.side_effect = [identity_query, face_query]

    crud_face.handle_face_deletion_dependency(db, face)

    assert identity.default_face_id == 15
    db.add.assert_called_once_with(identity)
    db.flush.assert_called_once()


def test_photos_by_time_applies_time_bounds_and_unlimited_query():
    db = MagicMock()
    expected = [SimpleNamespace(id=uuid4())]
    query = MagicMock()
    query.filter.return_value = query
    query.order_by.return_value = query
    query.offset.return_value = query
    query.all.return_value = expected
    db.query.return_value = query
    owner_id = uuid4()
    start = datetime(2026, 1, 1)
    end = datetime(2026, 1, 31, 23, 59, 59)

    result = crud_photo.get_photos_by_time(
        db, owner_id, skip=10, limit=0, start_time=start, end_time=end
    )

    assert result == expected
    assert query.filter.call_count == 3
    query.offset.assert_called_once_with(10)


