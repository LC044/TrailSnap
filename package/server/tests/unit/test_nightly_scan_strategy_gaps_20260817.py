"""Unit tests for app/service/tasks/scan.py strategy class.

The nightly gap scan flagged service/tasks/scan.py as 30 percent covered
with 172 missed lines.  Pure helpers (_compile_folder_patterns,
_is_folder_excluded, scan_directory_recursive) are covered by
test_scan_folder_helpers.py; this file picks up the three ScanFolderStrategy
methods that touch SQLAlchemy without spinning up real os.scandir walks.

Goals:
  * _get_existing_files         -- SQL row iteration + live-photo bookkeeping
  * _create_tasks_for_new_files -- grouping + live-photo pair detection
  * _handle_deleted_files       -- chunked batch_delete_photos_db + IndexLog
  * process                      -- single-user vs all-user dispatch
"""

import asyncio
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.db.models.photo import FileType
from app.db.models.task import TaskStatus, TaskType
from app.service.tasks.scan import ScanFolderStrategy


pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _strategy():
    return ScanFolderStrategy()


def _photo(file_path, file_type="image", owner_id="user-1"):
    return SimpleNamespace(
        id=f"photo-{os.path.basename(file_path)}",
        file_path=file_path,
        file_type=file_type,
        owner_id=owner_id,
        is_deleted=False,
    )


def _row(file_path, file_type):
    """``query(Photo.file_path, Photo.file_type).all()`` returns 2-tuples."""
    return (file_path, file_type)


# ---------------------------------------------------------------------------
# _get_existing_files
# ---------------------------------------------------------------------------


class TestGetExistingFiles:
    def test_returns_only_files_under_scan_roots(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = [
            _row("E:/photos/2024/a.jpg", FileType.image),
            _row("E:/other/x.jpg", FileType.image),
        ]

        existing, live_add = _strategy()._get_existing_files(
            db, "user-1", ["E:/photos"]
        )

        assert "E:/photos/2024/a.jpg" in existing
        assert "E:/other/x.jpg" not in existing
        assert live_add == set()

    def test_live_jpg_mp4_pair_flags_mp4_row(self):
        """For a jpg+mp4 pair stored with the image+video file types the
        scanner iterates rows in DB order; when the mp4 row is processed
        second, the matching jpg is already in ``existing_files`` so the
        mp4 row is added to ``live_photo_to_add`` (it needs the live
        payload in PROCESS_BASIC)."""
        db = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = [
            _row("E:/p/IMG_0001.jpg", FileType.image),
            _row("E:/p/IMG_0001.mp4", FileType.video),
        ]

        existing, live_add = _strategy()._get_existing_files(
            db, "user-1", ["E:/p"]
        )

        assert existing == {"E:/p/IMG_0001.jpg", "E:/p/IMG_0001.mp4"}
        assert live_add == {"E:/p/IMG_0001.mp4"}

    def test_live_heic_mov_pair_flags_mov_row(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = [
            _row("E:/p/IMG_0002.HEIC", FileType.image),
            _row("E:/p/IMG_0002.MOV", FileType.video),
        ]

        existing, live_add = _strategy()._get_existing_files(
            db, "user-1", ["E:/p"]
        )

        assert existing == {"E:/p/IMG_0002.HEIC", "E:/p/IMG_0002.MOV"}
        assert live_add == {"E:/p/IMG_0002.MOV"}

    def test_live_photo_file_type_injects_video_into_existing(self):
        """A DB row already marked ``FileType.live_photo`` for a .jpg file
        means the scanner must pre-populate ``existing_files`` with the
        matching .mp4 path so later disk diff doesn't see a phantom new
        file."""
        db = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = [
            _row("E:/p/IMG_0001.jpg", FileType.live_photo),
        ]

        existing, _ = _strategy()._get_existing_files(db, "user-1", ["E:/p"])

        assert "E:/p/IMG_0001.mp4" in existing
        assert "E:/p/IMG_0001.jpg" in existing

    def test_live_photo_heic_injects_mov_into_existing(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = [
            _row("E:/p/IMG_0002.HEIC", FileType.live_photo),
        ]

        existing, _ = _strategy()._get_existing_files(db, "user-1", ["E:/p"])

        assert "E:/p/IMG_0002.MOV" in existing
        assert "E:/p/IMG_0002.HEIC" in existing


# ---------------------------------------------------------------------------
# _create_tasks_for_new_files
# ---------------------------------------------------------------------------


class TestCreateTasksForNewFiles:
    @pytest.mark.asyncio
    async def test_emits_basic_task_for_each_image(self):
        db = MagicMock()
        loop = asyncio.get_running_loop()
        files = {
            "E:/p/IMG_0001.jpg",
            "E:/p/IMG_0002.jpg",
            "E:/p/IMG_0003.png",
        }

        with patch(
            "app.service.tasks.scan.live_photo_service.get_content_identifier",
            return_value=None,
        ):
            await _strategy()._create_tasks_for_new_files("user-1", files, loop, db)

        # Three files -> three PROCESS_BASIC tasks in a single 1000-chunk.
        assert db.bulk_save_objects.call_count == 1
        all_tasks = db.bulk_save_objects.call_args.args[0]
        assert len(all_tasks) == 3
        assert {t.type for t in all_tasks} == {TaskType.PROCESS_BASIC}
        assert {t.status for t in all_tasks} == {TaskStatus.PENDING}
        assert all(t.payload["user_id"] == "user-1" for t in all_tasks)

    @pytest.mark.asyncio
    async def test_live_pair_emits_single_task_with_video_payload(self):
        db = MagicMock()
        loop = asyncio.get_running_loop()
        files = {"E:/p/IMG_0001.jpg", "E:/p/IMG_0001.mp4"}

        with patch(
            "app.service.tasks.scan.live_photo_service.get_content_identifier",
            side_effect=lambda p: "cid-1",
        ):
            await _strategy()._create_tasks_for_new_files("user-1", files, loop, db)

        all_tasks = db.bulk_save_objects.call_args.args[0]
        assert len(all_tasks) == 1
        task = all_tasks[0]
        assert task.payload["is_live_photo"] is True
        assert task.payload["file_path"].endswith(".jpg")
        assert task.payload["live_photo_video_path"].endswith(".mp4")

    @pytest.mark.asyncio
    async def test_empty_input_skips_db_write(self):
        db = MagicMock()
        await _strategy()._create_tasks_for_new_files(
            "user-1", set(), asyncio.get_running_loop(), db
        )
        db.bulk_save_objects.assert_not_called()
        db.commit.assert_not_called()


# ---------------------------------------------------------------------------
# _handle_deleted_files
# ---------------------------------------------------------------------------


class TestHandleDeletedFiles:
    def test_no_files_means_no_db_calls(self):
        db = MagicMock()
        worker = SimpleNamespace(scan_status={"deleted": 0})

        _strategy()._handle_deleted_files("user-1", set(), db, worker)

        db.query.assert_not_called()
        db.add.assert_not_called()
        db.commit.assert_not_called()
        assert worker.scan_status["deleted"] == 0

    def test_chunks_deleted_files_into_batches(self):
        # 1200 files -> 3 chunks of 500 / 500 / 200.
        # Each chunk's photo query returns 10 Photo rows -> worker counts
        # accumulate to 30 over the 3 iterations.
        deleted = {f"E:/p/{i}.jpg" for i in range(1200)}

        db = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = [
            _photo(p) for p in list(deleted)[:10]
        ]

        worker = SimpleNamespace(scan_status={"deleted": 0})

        # ``batch_delete_photos_db`` is imported lazily inside the method,
        # so the patch must target the source module, not the consumer.
        with patch(
            "app.crud.photo.batch_delete_photos_db"
        ) as batch_delete:
            _strategy()._handle_deleted_files("user-1", deleted, db, worker)

        assert batch_delete.call_count == 3
        assert worker.scan_status["deleted"] == 30


# ---------------------------------------------------------------------------
# process (entrypoint)
# ---------------------------------------------------------------------------


class TestProcess:
    @pytest.mark.asyncio
    async def test_processes_only_target_user_when_user_id_provided(self):
        db = MagicMock()
        target_user = SimpleNamespace(id="target-user")
        db.query.return_value.filter.return_value.first.return_value = target_user

        worker = SimpleNamespace(scan_status={"message": "", "total_files": 0, "deleted": 0})
        task = SimpleNamespace(
            payload={"user_id": "target-user", "scan_roots": ["E:/p"]}
        )
        strategy = _strategy()
        strategy._scan_for_user = AsyncMock(return_value={"new_files": 2, "deleted_files": 1})

        result = await strategy.process(worker, task, db)

        strategy._scan_for_user.assert_awaited_once()
        assert result == {"new_files": 2, "deleted_files": 1}

    @pytest.mark.asyncio
    async def test_unknown_user_id_produces_zero_result(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None

        worker = SimpleNamespace(scan_status={"message": "", "total_files": 0, "deleted": 0})
        task = SimpleNamespace(payload={"user_id": "ghost", "scan_roots": ["E:/p"]})
        strategy = _strategy()
        strategy._scan_for_user = AsyncMock()

        result = await strategy.process(worker, task, db)

        strategy._scan_for_user.assert_not_awaited()
        assert result == {"new_files": 0, "deleted_files": 0}