"""Nightly watch coverage guards for the 2026-11-06 backend gap scan.

The selected modules are the low-coverage entries from coverage-gaps-backend.txt:
``app.api.media``, ``app.service.task_worker``, ``app.service.face_cluster``,
``app.crud.face``, and ``app.core.logger``.  These guards exercise small
error/edge branches only and intentionally keep persistence mocked.
"""

import asyncio
import logging
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api import media
from app.core.logger import DailySizeRotatingFileHandler, log_operation
from app.crud import face as crud_face
from app.service import task_worker
from app.service.face_cluster import FaceClusterService, FaceRescanError

pytestmark = pytest.mark.smoke


@pytest.mark.asyncio
async def test_task_queue_reports_and_drains_lowest_priority():
    manager = task_worker.TaskQueueManager()
    low = [{"id": "low"}]
    await manager.put_batch("IO", low, priority=2)

    assert manager.get_lowest_priority("IO") == 2
    assert manager.drain_queued("IO") == low
    assert manager.get_lowest_priority("IO") == -9999


def test_task_queue_item_count_stays_nonnegative_for_unknown_category():
    manager = task_worker.TaskQueueManager()
    assert manager.item_count("UNKNOWN") == 0
    assert manager.qsize("UNKNOWN") == 0


def test_logger_operation_dispatches_error_and_non_error_levels():
    logger = MagicMock()
    with patch.object(logging, "getLogger", return_value=logger):
        log_operation("warn", "careful", operation="watch", params={"x": 1}, result=2)
        log_operation("error", "failed", operation="watch", error=RuntimeError("boom"))

    logger.warning.assert_called_once()
    logger.error.assert_called_once()
    assert logger.error.call_args.kwargs["exc_info"] is not None


def test_logger_handler_creation_warns_when_log_directory_unavailable(capsys, monkeypatch):
    def fail_mkdir(*args, **kwargs):
        raise PermissionError("read-only")

    monkeypatch.setattr(logging.handlers.RotatingFileHandler, "__init__", lambda self, *args, **kwargs: None)
    monkeypatch.setattr(Path, "mkdir", fail_mkdir)
    handler = DailySizeRotatingFileHandler(
        "watch", "Z:/unwritable/logs", maxBytes=100, backupCount=1
    )
    try:
        assert "read-only" in capsys.readouterr().out
    finally:
        # Parent initialization is intentionally stubbed, so no stream exists.
        pass


def test_media_backup_check_rejects_invalid_source_time():
    with pytest.raises(HTTPException) as exc_info:
        media.check_mobile_backup_assets(
            {"keys": ["a"], "source_times": {"a": "not-a-date"}},
            db=MagicMock(),
            current_user=SimpleUser(),
        )

    assert exc_info.value.status_code == 400
    assert "invalid datetime" in exc_info.value.detail


def test_media_live_photo_video_path_rejects_mismatched_extensions():
    with pytest.raises(ValueError, match="image type"):
        media._live_photo_video_path("photo.webp", "photo.mp4")


def test_face_cluster_preview_failure_rolls_back_and_wraps_error():
    db = MagicMock()
    service = FaceClusterService(db)
    identity_id = uuid.uuid4()

    with patch.object(service, "_analyze_identity_rescan", side_effect=RuntimeError("db failed")):
        with pytest.raises(FaceRescanError, match=str(identity_id)):
            service.preview_identity_rescan(identity_id, owner_id=None)

    db.rollback.assert_called_once_with()


def test_crud_face_delete_faces_by_photo_can_flush_without_commit():
    db = MagicMock()
    query = MagicMock()
    face = MagicMock(id=17)
    query.filter.return_value.all.return_value = [face]
    db.query.return_value = query

    with patch.object(crud_face, "handle_face_deletion_dependency") as handle_dependency:
        count = crud_face.delete_faces_by_photo(db, uuid.uuid4(), commit=False)
    handle_dependency.assert_called_once_with(db, face)

    assert count == 1
    db.delete.assert_called_once_with(face)
    db.flush.assert_called_once()
    db.commit.assert_not_called()


def test_crud_face_set_identity_cover_returns_false_without_face():
    db = MagicMock()
    identity_query = MagicMock()
    identity_query.filter.return_value.first.return_value = MagicMock()
    face_query = MagicMock()
    face_query.join.return_value.filter.return_value.first.return_value = None
    db.query = MagicMock(return_value=face_query)
    identity_id, photo_id = uuid.uuid4(), uuid.uuid4()

    with patch.object(crud_face, "get_identity", return_value=MagicMock()):
        result = crud_face.set_identity_cover(db, identity_id, photo_id)

    assert result is False
    db.commit.assert_not_called()


class SimpleUser:
    id = uuid.uuid4()




