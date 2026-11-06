"""Nightly coverage additions for the lowest-covered server modules on 2026-11-06."""

from datetime import date
from unittest.mock import MagicMock
from uuid import UUID

import numpy as np
import pytest
from fastapi import HTTPException

from app.api import media
from app.crud import photo as crud_photo
from app.service import chapter as chapter_service
from app.service import storage as storage_service
from app.service import task_worker
from app.service.face_cluster import FaceClusterService


pytestmark = [pytest.mark.smoke]


def test_face_cluster_assign_defers_recognition_to_batch_clustering():
    db = MagicMock()
    service = FaceClusterService(db)

    result = service.assign_face_to_identity(101, [0.1, 0.2], commit=False)

    assert result is None
    db.query.assert_not_called()
    db.rollback.assert_not_called()


@pytest.mark.asyncio
async def test_task_queue_manager_returns_available_ai_head():
    manager = task_worker.TaskQueueManager()
    high = [{"task_id": "high"}]
    low = [{"task_id": "low"}]

    await manager.put_batch("AI", low, priority=1)
    await manager.put_batch("AI", high, priority=9)

    batch = await manager.get_available_ai_batch(lambda candidate: candidate[0]["task_id"] == "high")

    assert batch == high
    assert manager.item_count("AI") == 1


def test_media_existing_content_photo_prefers_reusable_file(monkeypatch):
    db = MagicMock()
    query = MagicMock()
    query.filter.return_value.all.return_value = [
        MagicMock(file_path="missing.jpg"),
        MagicMock(file_path="available.jpg"),
    ]
    db.query.return_value = query
    monkeypatch.setattr(media.os.path, "isfile", lambda path: path == "available.jpg")

    photo = media._existing_content_photo(db, UUID(int=1), "hash")

    assert photo.file_path == "available.jpg"
    query.filter.assert_called_once()


def test_crud_batch_create_photos_deduplicates_existing_paths():
    db = MagicMock()
    query = MagicMock()
    query.filter.return_value.filter.return_value.all.return_value = [("already.jpg",)]
    db.query.return_value = query
    photo_id = UUID(int=2)

    result = crud_photo.batch_create_photos(
        db,
        [
            {
                "photo": MagicMock(filename="duplicate.jpg"),
                "metadata": MagicMock(),
                "photo_id": photo_id,
                "file_path": "already.jpg",
            },
            {
                "photo": MagicMock(filename="in-batch.jpg"),
                "metadata": None,
                "photo_id": UUID(int=3),
                "file_path": "already.jpg",
            },
        ],
        UUID(int=1),
        commit=False,
    )

    assert result == []
    db.bulk_save_objects.assert_not_called()
    db.rollback.assert_not_called()


def test_chapter_validate_cover_rejects_missing_photo():
    db = MagicMock()
    query = MagicMock()
    query.filter.return_value = query
    query.first.return_value = None
    db.query.return_value = query
    cover_id = UUID(int=4)

    with pytest.raises(HTTPException) as exc_info:
        chapter_service._validate_cover(
            db,
            UUID(int=1),
            cover_id,
            date(2026, 1, 1),
            date(2026, 12, 31),
        )

    assert exc_info.value.status_code == 400


def test_storage_video_thumbnail_helpers_reject_blanks_and_short_clips():
    assert storage_service._video_thumbnail_candidate_seconds(0) == [0.0]
    assert storage_service._video_thumbnail_candidate_seconds(0.08) == [0.0, 0.004, 0.008, 0.02, 0.03]

    blank = np.zeros((2, 2, 3), dtype=np.uint8)
    assert storage_service._score_video_thumbnail_frame(blank) == float("-inf")

    detailed = np.array([[[0, 0, 0], [255, 255, 255]]], dtype=np.uint8)
    assert storage_service._score_video_thumbnail_frame(detailed) > 0
