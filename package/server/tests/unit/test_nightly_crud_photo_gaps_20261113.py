"""Nightly watch 2026-11-13 (round 2): photo CRUD gaps.

Targets the branches the 2026-11-13 coverage snapshot still reports as
uncovered in ``app/crud/photo.py``:

* ``batch_create_photos`` - entries without a ``file_path`` are skipped and a
  failing batch rolls the session back before re-raising.
* ``_write_gps_back`` - missing photo, broken storage reference and a failed
  md5 refresh (the write itself already succeeded).
* ``get_photos`` - the time-window filters and the unlimited (``limit=0``)
  branch.

Every test exercises already-implemented behaviour; no production change.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.crud import photo as photo_crud

pytestmark = [pytest.mark.smoke]


def _photo_item(file_path="C:/photos/a.jpg"):
    schema = MagicMock()
    schema.filename = "a.jpg"
    schema.photo_time = datetime(2024, 1, 1, 10, 0, 0)
    schema.file_type = "image"
    schema.size = 10
    schema.width = 100
    schema.height = 100
    schema.duration = None
    schema.md5 = None
    return {"photo": schema, "metadata": None, "photo_id": "pid-1",
            "file_path": file_path}


# --- batch_create_photos ----------------------------------------------------


def test_batch_create_photos_skips_entries_without_a_file_path():
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = []

    with patch.object(photo_crud, "apply_photo_reference", create=True), \
            patch("app.service.storage_paths.apply_photo_reference"), \
            patch("app.service.journey_queue.enqueue"), \
            patch.object(photo_crud.Photo, "id", create=True):
        result = photo_crud.batch_create_photos(
            db, [_photo_item(file_path=""), _photo_item(file_path="C:/photos/a.jpg")],
            user_id=None,
        )

    assert result == ["pid-1"]


def test_batch_create_photos_rolls_back_and_re_raises():
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = []

    with patch("app.service.storage_paths.apply_photo_reference", side_effect=RuntimeError("boom")):
        with pytest.raises(RuntimeError):
            photo_crud.batch_create_photos(db, [_photo_item()], user_id=None)

    db.rollback.assert_called_once()


# --- _write_gps_back --------------------------------------------------------


def test_write_gps_back_skips_a_missing_photo():
    with patch.object(photo_crud, "get_photo", return_value=None):
        assert photo_crud._write_gps_back(MagicMock(), "pid", None, 1.0, 2.0) == "skipped"


def test_write_gps_back_skips_a_broken_storage_reference():
    photo = MagicMock()
    type(photo).file_path = property(lambda self: (_ for _ in ()).throw(ValueError("broken")))

    with patch.object(photo_crud, "get_photo", return_value=photo):
        assert photo_crud._write_gps_back(MagicMock(), "pid", None, 1.0, 2.0) == "skipped"


def test_write_gps_back_reports_written_when_the_md5_refresh_fails(tmp_path):
    target = tmp_path / "photo.jpg"
    target.write_bytes(b"x")
    photo = MagicMock()
    photo.file_path = str(target)
    photo.owner_id = None

    with patch.object(photo_crud, "get_photo", return_value=photo), \
            patch.object(photo_crud, "write_gps_to_file", return_value=None), \
            patch.object(photo_crud, "update_photo_md5", return_value=False):
        assert photo_crud._write_gps_back(MagicMock(), "pid", None, 1.0, 2.0) == "written"


# --- get_photos -------------------------------------------------------------


def _album(kind="user"):
    album = MagicMock()
    album.type = kind
    album.query_embedding = None
    return album


def test_get_photos_applies_the_time_window_filters():
    db = MagicMock()
    query = MagicMock()
    db.query.return_value = query
    query.order_by.return_value = query
    query.filter.return_value = query
    query.options.return_value = query
    query.offset.return_value = query
    query.limit.return_value = query
    query.all.return_value = []

    start = datetime(2024, 1, 1)
    end = start + timedelta(days=1)

    with patch.object(photo_crud, "get_album", return_value=_album()), \
            patch.object(photo_crud, "_build_album_query", return_value=query):
        photo_crud.get_photos(db, "album", skip=0, limit=10, start_time=start, end_time=end)

    assert query.filter.call_count >= 2


def test_get_photos_returns_everything_when_limit_is_zero():
    db = MagicMock()
    query = MagicMock()
    db.query.return_value = query
    query.order_by.return_value = query
    query.filter.return_value = query
    query.options.return_value = query
    query.offset.return_value = query
    query.all.return_value = ["photo-a"]

    with patch.object(photo_crud, "get_album", return_value=_album()), \
            patch.object(photo_crud, "_build_album_query", return_value=query):
        rows = photo_crud.get_photos(db, "album", skip=0, limit=0)

    assert rows == ["photo-a"]
    query.limit.assert_not_called()


def test_get_photos_returns_an_empty_list_for_an_unknown_album():
    db = MagicMock()
    with patch.object(photo_crud, "get_album", return_value=None):
        assert photo_crud.get_photos(db, "album") == []
