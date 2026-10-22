"""Unit tests for ``app/service/tasks/time_from_filename.py`` guards.

The 2026-10-23 coverage scan showed the module at 75.0% (33 missed of 132).
The misses sat in the parts the strategy owns:

* the payload guards -- missing ``target_root_path`` / ``album_id``, an album
  that no longer exists (or belongs to somebody else) and a malformed
  ``custom_time``;
* the target selection -- ``only_missing_metadata`` filtering and the
  ``os.path.commonpath`` containment check that keeps the task inside the
  chosen root;
* the per-photo write path -- ``time_mode`` handling, the
  ``PhotoMetadata`` upsert, the file mtime update and the EXIF rewrite.

The strategy reaches into the file system, PIL and piexif, so every
dependency is stubbed here: the tests assert *what the strategy decided*
(the guards it raises, the metadata it writes, the time it applies) rather
than re-implementing the side effects.
"""

from __future__ import annotations

import os
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


from app.service.tasks import time_from_filename as tff  # noqa: E402


class _FakeQuery:
    """Chainable stand-in for a SQLAlchemy query object."""

    def __init__(self, *, rows=None, first=None):
        self._rows = rows if rows is not None else []
        self._first = first

    def outerjoin(self, *args, **kwargs):
        return self

    def options(self, *args, **kwargs):
        return self

    def join(self, *args, **kwargs):
        return self

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self._first

    def all(self):
        return list(self._rows)


class _FakeDB:
    """Minimal DB double: routes by queried model."""

    def __init__(self, *, photos=None, album=None):
        self._photos = photos if photos is not None else []
        self._album = album
        self.added = []
        self.commits = 0

    def query(self, model):
        name = getattr(model, "__name__", str(model))
        if name == "Album":
            return _FakeQuery(first=self._album)
        return _FakeQuery(rows=self._photos)

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.commits += 1


def _make_photo(photo_id="p-1", file_path="C:/photos/a.jpg", photo_time=None, make=None, model=None):
    """Build a photo double with optional existing metadata."""
    metadata = None
    if make is not None or model is not None:
        metadata = SimpleNamespace(make=make, model=model, exif_info=None)
    return SimpleNamespace(
        id=photo_id,
        file_path=file_path,
        photo_time=photo_time,
        metadata_info=metadata,
    )


def _task(payload=None, owner_id="user-1"):
    return SimpleNamespace(
        id="task-1",
        owner_id=owner_id,
        payload=payload or {},
        total_items=0,
        processed_items=0,
    )


def _strategy():
    return tff.TimeFromFilenameStrategy()


# --- _has_missing_metadata ------------------------------------------------


def test_missing_metadata_when_photo_has_no_metadata_row():
    photo = _make_photo()
    assert _strategy()._has_missing_metadata(photo) is True


@pytest.mark.parametrize(
    "make, model",
    [
        (None, "iPhone"),
        ("Canon", None),
        ("", "iPhone"),
        ("Canon", "   "),
    ],
)
def test_missing_metadata_when_make_or_model_is_blank(make, model):
    photo = _make_photo(make=make, model=model)
    assert _strategy()._has_missing_metadata(photo) is True


def test_missing_metadata_is_false_when_make_and_model_present():
    photo = _make_photo(make="Canon", model="EOS")
    assert _strategy()._has_missing_metadata(photo) is False


# --- payload guards -------------------------------------------------------


@pytest.mark.asyncio
async def test_process_requires_root_path_or_album():
    db = _FakeDB()
    with pytest.raises(ValueError, match="Missing target_root_path or album_id"):
        await _strategy().process(None, _task({}), db)


@pytest.mark.asyncio
async def test_process_rejects_album_owned_by_somebody_else():
    db = _FakeDB(album=None)
    payload = {"album_id": "6f1b0c1e-0b1e-4a3d-9c7a-9f0b2c3d4e5f"}
    with pytest.raises(ValueError, match="Album no longer exists or is not owned"):
        await _strategy().process(None, _task(payload), db)


@pytest.mark.asyncio
async def test_process_rejects_malformed_custom_time():
    db = _FakeDB()
    payload = {
        "target_root_path": "C:/photos",
        "custom_time": "2024/06/01 12:00:00",
        "time_mode": "custom",
    }
    with pytest.raises(ValueError, match="Invalid custom_time format"):
        await _strategy().process(None, _task(payload), db)


@pytest.mark.asyncio
async def test_process_rejects_missing_album_id_key_when_only_root_missing():
    # album_id present but empty -> falls back to the root-path requirement
    db = _FakeDB()
    with pytest.raises(ValueError, match="Missing target_root_path or album_id"):
        await _strategy().process(None, _task({"album_id": ""}), db)


# --- target selection -----------------------------------------------------


@pytest.mark.asyncio
async def test_process_skips_files_outside_the_target_root(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    inside = root / "inside.jpg"
    inside.write_bytes(b"x")
    outside = tmp_path / "outside.jpg"
    outside.write_bytes(b"x")

    photo_in = _make_photo("p-in", str(inside))
    photo_out = _make_photo("p-out", str(outside))
    db = _FakeDB(photos=[photo_in, photo_out])

    # 用真实的 os.path.commonpath：只有 root 内的文件会被选中
    with patch.object(tff.os.path, "exists", return_value=True):
        result = await _strategy().process(
            None, _task({"target_root_path": str(root)}), db
        )

    assert result["total_processed"] == 1
    assert result["success_count"] == 1


@pytest.mark.asyncio
async def test_process_only_missing_metadata_filters_complete_photos(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    file_a = root / "a.jpg"
    file_a.write_bytes(b"x")
    file_b = root / "b.jpg"
    file_b.write_bytes(b"x")

    complete = _make_photo("p-complete", str(file_a), make="Canon", model="EOS")
    incomplete = _make_photo("p-incomplete", str(file_b))
    db = _FakeDB(photos=[complete, incomplete])

    payload = {
        "target_root_path": str(root),
        "only_missing_metadata": True,
        "make": "Sony",
        "model": "A7",
    }
    with patch.object(tff.os.path, "exists", return_value=True), \
            patch.object(tff.os.path, "commonpath", return_value=str(root)):
        result = await _strategy().process(None, _task(payload), db)

    assert result["total_processed"] == 1
    # 只有缺 make/model 的那张被写入 make/model
    assert incomplete.metadata_info.make == "Sony"
    assert incomplete.metadata_info.model == "A7"
    assert complete.metadata_info.make == "Canon"


@pytest.mark.asyncio
async def test_process_creates_metadata_row_when_photo_has_none(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    file_path = root / "a.jpg"
    file_path.write_bytes(b"x")

    photo = _make_photo("p-1", str(file_path))
    db = _FakeDB(photos=[photo])

    payload = {"target_root_path": str(root), "make": "Canon", "model": "EOS"}
    with patch.object(tff.os.path, "exists", return_value=True), \
            patch.object(tff.os.path, "commonpath", return_value=str(root)):
        result = await _strategy().process(None, _task(payload), db)

    assert result["success_count"] == 1
    assert len(db.added) == 1
    assert db.added[0].make == "Canon"
    assert db.added[0].model == "EOS"


# --- per-photo write path -------------------------------------------------


@pytest.mark.asyncio
async def test_process_updates_file_mtime_in_auto_mode(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    file_path = root / "a.jpg"
    file_path.write_bytes(b"x")

    photo_time = datetime(2024, 6, 1, 12, 0, 0)
    photo = _make_photo("p-1", str(file_path), photo_time=photo_time)
    db = _FakeDB(photos=[photo])

    utime_calls = []
    with patch.object(tff.os.path, "exists", return_value=True), \
            patch.object(tff.os.path, "commonpath", return_value=str(root)), \
            patch.object(tff.os, "utime", side_effect=lambda path, times: utime_calls.append((path, times))):
        result = await _strategy().process(
            None, _task({"target_root_path": str(root), "time_mode": "auto"}), db
        )

    assert result["success_count"] == 1
    assert len(utime_calls) == 1
    assert utime_calls[0][0] == str(file_path)
    assert utime_calls[0][1][0] == photo_time.timestamp()
    # auto 模式沿用库里已有的拍摄时间
    assert photo.photo_time == photo_time


@pytest.mark.asyncio
async def test_process_custom_mode_overrides_photo_time(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    file_path = root / "a.jpg"
    file_path.write_bytes(b"x")

    photo = _make_photo("p-1", str(file_path), photo_time=datetime(2020, 1, 1, 0, 0, 0))
    db = _FakeDB(photos=[photo])

    payload = {
        "target_root_path": str(root),
        "time_mode": "custom",
        "custom_time": "2024-06-01 12:00:00",
    }
    with patch.object(tff.os.path, "exists", return_value=True), \
            patch.object(tff.os.path, "commonpath", return_value=str(root)), \
            patch.object(tff.os, "utime"):
        result = await _strategy().process(None, _task(payload), db)

    assert result["success_count"] == 1
    assert photo.photo_time == datetime(2024, 6, 1, 12, 0, 0)


@pytest.mark.asyncio
async def test_process_none_mode_leaves_photo_time_untouched(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    file_path = root / "a.jpg"
    file_path.write_bytes(b"x")

    original = datetime(2020, 1, 1, 0, 0, 0)
    photo = _make_photo("p-1", str(file_path), photo_time=original)
    db = _FakeDB(photos=[photo])

    utime_calls = []
    with patch.object(tff.os.path, "exists", return_value=True), \
            patch.object(tff.os.path, "commonpath", return_value=str(root)), \
            patch.object(tff.os, "utime", side_effect=lambda path, times: utime_calls.append(path)):
        result = await _strategy().process(
            None, _task({"target_root_path": str(root), "time_mode": "none"}), db
        )

    assert result["success_count"] == 1
    assert photo.photo_time == original
    # none 模式不写文件时间
    assert utime_calls == []


@pytest.mark.asyncio
async def test_process_writes_exif_timestamp_and_make_model(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    file_path = root / "a.jpg"
    file_path.write_bytes(b"x")

    photo = _make_photo("p-1", str(file_path), photo_time=datetime(2024, 6, 1, 12, 0, 0))
    db = _FakeDB(photos=[photo])

    exif = {"Exif": {}, "0th": {}}
    inserted = {}

    def fake_dump(payload):
        inserted["payload"] = payload
        return b"exif-bytes"

    with patch.object(tff.os.path, "exists", return_value=True), \
            patch.object(tff.os.path, "commonpath", return_value=str(root)), \
            patch.object(tff.os, "utime"), \
            patch.object(tff.piexif, "load", return_value=exif), \
            patch.object(tff.piexif, "dump", side_effect=fake_dump), \
            patch.object(tff.piexif, "insert", side_effect=lambda data, path: inserted.__setitem__("path", path)), \
            patch.object(tff, "get_exif_data", return_value={"Make": "Canon"}), \
            patch.object(tff, "Image"):
        await _strategy().process(
            None,
            _task({"target_root_path": str(root), "make": "Canon", "model": "EOS"}),
            db,
        )

    assert inserted["path"] == str(file_path)
    assert inserted["payload"]["Exif"][tff.piexif.ExifIFD.DateTimeOriginal] == b"2024:06:01 12:00:00"
    assert inserted["payload"]["0th"][tff.piexif.ImageIFD.Make] == b"Canon"
    assert inserted["payload"]["0th"][tff.piexif.ImageIFD.Model] == b"EOS"
    assert photo.metadata_info.exif_info


@pytest.mark.asyncio
async def test_process_survives_exif_failure(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    file_path = root / "a.jpg"
    file_path.write_bytes(b"x")

    photo = _make_photo("p-1", str(file_path), photo_time=datetime(2024, 6, 1, 12, 0, 0))
    db = _FakeDB(photos=[photo])

    with patch.object(tff.os.path, "exists", return_value=True), \
            patch.object(tff.os.path, "commonpath", return_value=str(root)), \
            patch.object(tff.os, "utime"), \
            patch.object(tff.piexif, "load", side_effect=RuntimeError("broken exif")):
        result = await _strategy().process(
            None, _task({"target_root_path": str(root)}), db
        )

    # EXIF 写失败不应让整张照片失败
    assert result["success_count"] == 1


@pytest.mark.asyncio
async def test_process_triggers_conditional_album_update(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    file_path = root / "a.jpg"
    file_path.write_bytes(b"x")

    photo = _make_photo("p-1", str(file_path), photo_time=datetime(2024, 6, 1, 12, 0, 0))
    db = _FakeDB(photos=[photo])

    with patch.object(tff.os.path, "exists", return_value=True), \
            patch.object(tff.os.path, "commonpath", return_value=str(root)), \
            patch.object(tff.os, "utime"), \
            patch("app.crud.album.trigger_conditional_albums_update") as trigger:
        await _strategy().process(None, _task({"target_root_path": str(root)}), db)

    trigger.assert_called_once()
    assert trigger.call_args[0][1] == "user-1"
    assert list(trigger.call_args[0][2]) == ["p-1"]
