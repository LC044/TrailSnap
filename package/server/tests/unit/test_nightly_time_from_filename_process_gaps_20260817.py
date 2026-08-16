"""Unit tests for app/service/tasks/time_from_filename.py process() method.

The nightly gap scan flagged service/tasks/time_from_filename.py at 29 %
coverage (88 missed lines).  ``test_time_from_filename_task.py`` covers
``_has_missing_metadata`` + the empty ``target_root_path`` error path.
This file picks up the remaining branches of ``process``:

  * custom_time format validation (YYYY-MM-DD HH:MM:SS)
  * target_root_path filter (only photos under that path)
  * only_missing_metadata filter
  * time_mode branches: auto / custom / none
  * PhotoMetadata creation when absent
"""

import asyncio
import os
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _build_task(payload, owner_id="user-1"):
    return SimpleNamespace(
        id="task-ttff",
        owner_id=owner_id,
        payload=payload,
        total_items=0,
        processed_items=0,
    )


def _make_photo(pid, file_path, photo_time=None, metadata=None):
    return SimpleNamespace(
        id=pid,
        file_path=file_path,
        photo_time=photo_time,
        metadata_info=metadata,
        is_deleted=False,
        owner_id="user-1",
    )


def _query_with_photos(photos):
    """Mimic ``db.query(...).outerjoin(...).options(...).filter().all()`` chain."""
    query = MagicMock()
    query.outerjoin.return_value = query
    query.options.return_value = query
    query.filter.return_value = query
    query.all.return_value = photos
    return query


def _db_with_photos(photos):
    """DB whose ``query(...).all()`` returns the given photos, with a
    default no-op chain for the albums-query used by the post-step
    ``trigger_conditional_albums_update`` (out of scope for these tests)."""
    db = MagicMock()
    db.query.return_value = _query_with_photos(photos)
    return db


# ---------------------------------------------------------------------------
# error paths
# ---------------------------------------------------------------------------


class TestProcessErrors:
    def test_missing_target_root_path_raises(self):
        from app.service.tasks.time_from_filename import TimeFromFilenameStrategy

        task = _build_task({})

        with pytest.raises(ValueError, match="target_root_path"):
            asyncio.run(TimeFromFilenameStrategy().process(None, task, None))

    def test_invalid_custom_time_format_raises(self):
        """``custom_time`` must follow ``%Y-%m-%d %H:%M:%S``; bad input
        is rejected loudly so the worker can mark the task failed rather
        than silently writing ``None``."""
        from app.service.tasks.time_from_filename import TimeFromFilenameStrategy

        task = _build_task(
            {
                "target_root_path": str(os.path.abspath(".")),
                "time_mode": "custom",
                "custom_time": "yesterday",
            }
        )

        with pytest.raises(ValueError, match="Invalid custom_time format"):
            asyncio.run(TimeFromFilenameStrategy().process(None, task, None))


# ---------------------------------------------------------------------------
# happy paths
# ---------------------------------------------------------------------------


class TestProcessHappyPaths:
    def test_filters_by_target_root_path(self, tmp_path):
        """Photos whose file_path is not under ``target_root_path`` must be
        excluded even though the DB returned them."""
        from app.service.tasks.time_from_filename import TimeFromFilenameStrategy

        inside = _make_photo("p1", str(tmp_path / "a.jpg"))
        outside = _make_photo("p2", str(tmp_path.parent / "b.jpg"))
        # Patch os.path.exists so both "exist" without touching the FS.
        with patch("app.service.tasks.time_from_filename.os.path.exists", return_value=True), \
             patch("app.crud.album.trigger_conditional_albums_update"):
            task = _build_task(
                {"target_root_path": str(tmp_path), "time_mode": "none"}
            )
            db = _db_with_photos([inside, outside])

            result = asyncio.run(
                TimeFromFilenameStrategy().process(None, task, db)
            )

        assert task.total_items == 1
        assert result["total_processed"] == 1

    def test_only_missing_metadata_filter_narrows_targets(self, tmp_path):
        from app.service.tasks.time_from_filename import TimeFromFilenameStrategy

        incomplete = _make_photo("p1", str(tmp_path / "a.jpg"), metadata=None)
        complete = _make_photo(
            "p2", str(tmp_path / "b.jpg"),
            metadata=SimpleNamespace(make="Canon", model=" EOS "),
        )

        with patch("app.service.tasks.time_from_filename.os.path.exists", return_value=True), \
             patch("app.crud.album.trigger_conditional_albums_update"):
            task = _build_task(
                {
                    "target_root_path": str(tmp_path),
                    "time_mode": "none",
                    "only_missing_metadata": True,
                }
            )
            db = _db_with_photos([incomplete, complete])

            asyncio.run(TimeFromFilenameStrategy().process(None, task, db))

        assert task.total_items == 1

    def test_auto_mode_uses_existing_photo_time(self, tmp_path):
        """time_mode=auto reuses ``photo.photo_time`` and writes it back
        to the file timestamp via ``os.utime``."""
        from app.service.tasks.time_from_filename import TimeFromFilenameStrategy

        target_dt = datetime(2024, 1, 2, 3, 4, 5)
        photo = _make_photo("p1", str(tmp_path / "a.jpg"), photo_time=target_dt)

        with patch("app.service.tasks.time_from_filename.os.path.exists", return_value=True), \
             patch("app.service.tasks.time_from_filename.os.utime") as utime_call, \
             patch("app.crud.album.trigger_conditional_albums_update"):
            task = _build_task(
                {"target_root_path": str(tmp_path), "time_mode": "auto"}
            )
            db = _db_with_photos([photo])

            result = asyncio.run(
                TimeFromFilenameStrategy().process(None, task, db)
            )

        assert result["success_count"] == 1
        # auto mode writes the stored timestamp back to disk.
        utime_call.assert_called_once()
        called_path, (atime, mtime) = utime_call.call_args.args
        assert called_path == str(tmp_path / "a.jpg")
        assert atime == mtime == target_dt.timestamp()

    def test_custom_mode_sets_photo_time_and_calls_utime(self, tmp_path):
        from app.service.tasks.time_from_filename import TimeFromFilenameStrategy

        photo = _make_photo("p1", str(tmp_path / "a.jpg"), photo_time=None)

        with patch("app.service.tasks.time_from_filename.os.path.exists", return_value=True), \
             patch("app.service.tasks.time_from_filename.os.utime") as utime_call, \
             patch("app.crud.album.trigger_conditional_albums_update"):
            task = _build_task(
                {
                    "target_root_path": str(tmp_path),
                    "time_mode": "custom",
                    "custom_time": "2024-05-06 07:08:09",
                    "make": "Canon",
                    "model": " EOS R5 ",
                }
            )
            db = _db_with_photos([photo])

            asyncio.run(TimeFromFilenameStrategy().process(None, task, db))

        assert photo.photo_time == datetime(2024, 5, 6, 7, 8, 9)
        utime_call.assert_called_once()
        called_path, (atime, mtime) = utime_call.call_args.args
        assert called_path == str(tmp_path / "a.jpg")
        assert atime == mtime
        assert datetime.fromtimestamp(mtime) == datetime(2024, 5, 6, 7, 8, 9)

    def test_none_mode_writes_make_model_without_touching_time(self, tmp_path):
        """time_mode=none skips os.utime entirely even when photo_time is set."""
        from app.service.tasks.time_from_filename import TimeFromFilenameStrategy

        photo = _make_photo(
            "p1",
            str(tmp_path / "a.jpg"),
            photo_time=datetime(2020, 1, 1, 0, 0, 0),
            metadata=SimpleNamespace(make=None, model=None),
        )

        with patch("app.service.tasks.time_from_filename.os.path.exists", return_value=True), \
             patch("app.service.tasks.time_from_filename.os.utime") as utime_call, \
             patch("app.crud.album.trigger_conditional_albums_update"):
            task = _build_task(
                {
                    "target_root_path": str(tmp_path),
                    "time_mode": "none",
                    "make": "Sony",
                    "model": "A7M4",
                }
            )
            db = _db_with_photos([photo])

            asyncio.run(TimeFromFilenameStrategy().process(None, task, db))

        utime_call.assert_not_called()
        assert photo.metadata_info.make == "Sony"
        assert photo.metadata_info.model == "A7M4"

    def test_creates_photo_metadata_when_missing(self, tmp_path):
        """If the photo has no ``metadata_info`` row, ``process`` must
        instantiate a new ``PhotoMetadata`` and attach it."""
        from app.service.tasks.time_from_filename import TimeFromFilenameStrategy

        photo = _make_photo("p1", str(tmp_path / "a.jpg"), metadata=None)

        with patch("app.service.tasks.time_from_filename.os.path.exists", return_value=True), \
             patch("app.crud.album.trigger_conditional_albums_update"):
            task = _build_task(
                {
                    "target_root_path": str(tmp_path),
                    "time_mode": "none",
                    "make": "Apple",
                    "model": "iPhone 15",
                }
            )
            db = _db_with_photos([photo])

            asyncio.run(TimeFromFilenameStrategy().process(None, task, db))

        assert photo.metadata_info is not None
        assert photo.metadata_info.make == "Apple"
        assert photo.metadata_info.model == "iPhone 15"
        # db.add should have been called to register the new metadata row.
        assert db.add.called