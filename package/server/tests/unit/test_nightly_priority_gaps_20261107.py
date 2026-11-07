"""Nightly priority-gap tests for 2026-11-07.

覆盖扫描选择：api/media.py、service/task_worker.py。
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api import media as media_api
from app.service.task_worker import TaskQueueManager


pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


def test_upload_folders_lists_internal_and_external_directories(tmp_path):
    root = tmp_path / "internal"
    (root / "2026" / "11").mkdir(parents=True)
    external = tmp_path / "external"
    (external / "trip").mkdir(parents=True)
    db = MagicMock()
    user = SimpleNamespace(id=uuid4())

    with patch.object(media_api, "_upload_root", return_value=str(root)), patch.object(
        media_api.storage, "get_external_upload_roots", return_value=[str(external)]
    ):
        response = media_api.list_upload_folders(db=db, current_user=user)

    assert response.code == 0
    assert response.data["folders"] == ["2026", "2026/11"]
    assert set(response.data["external_folders"]) == {str(external), str(external / "trip")}


def test_create_upload_folder_validates_and_creates_nested_path(tmp_path):
    root = tmp_path / "uploads"
    db = MagicMock()
    user = SimpleNamespace(id=uuid4())

    with patch.object(media_api, "_upload_root", return_value=str(root)):
        response = media_api.create_upload_folder(
            {"path": "2026/11"}, db=db, current_user=user
        )

    assert response.code == 0
    assert response.data == {"path": "2026/11"}
    assert (root / "2026" / "11").is_dir()


def test_create_upload_folder_rejects_escape_path(tmp_path):
    root = tmp_path / "uploads"
    db = MagicMock()
    user = SimpleNamespace(id=uuid4())

    with patch.object(media_api, "_upload_root", return_value=str(root)):
        with pytest.raises(HTTPException) as exc_info:
            media_api.create_upload_folder(
                {"path": "../outside"}, db=db, current_user=user
            )

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_task_queue_manager_tracks_priority_and_drains_batches():
    manager = TaskQueueManager()
    high_priority = [{"id": "high"}]
    low_priority = [{"id": "low"}]

    await manager.put_batch("CPU", high_priority, priority=10)
    await manager.put_batch("CPU", low_priority, priority=1)

    assert manager.qsize("CPU") == 2
    assert manager.item_count("CPU") == 2
    assert manager.get_lowest_priority("CPU") == 1
    assert manager.qsize("unknown") == 0
    assert manager.get_lowest_priority("unknown") == -9999

    drained = manager.drain_queued("CPU")
    assert drained == high_priority + low_priority
    assert manager.qsize("CPU") == 0
    assert manager.item_count("CPU") == 0

