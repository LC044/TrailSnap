"""Unit tests for the remaining ``app/service/tasks/time_from_filename.py``
branches.

Coverage scan 2026-10-30 showed the module at 88.2% with 16 missed lines.
The misses were:

* the album-scoped query (the photos are joined to ``AlbumPhoto``);
* the containment check blowing up (``os.path.commonpath`` raises when the
  photo lives on another drive);
* a failed ``os.utime`` -- the file time could not be rewritten, but the
  photo must still count as processed;
* piexif payloads without an ``Exif`` / ``0th`` section;
* the ``default_serializer`` used when the re-read EXIF still contains
  binary values;
* a per-photo failure that must not abort the whole batch;
* the periodic commit every 50 processed photos.

The strategy reaches into the file system, PIL and piexif, so every
dependency is stubbed: the tests assert what the strategy *decided*.
"""
from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest


pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


from app.service.tasks import time_from_filename as tff  # noqa: E402


class _FakeQuery:
    """Chainable stand-in for a SQLAlchemy query object."""

    def __init__(self, *, rows=None, first=None):
        self._rows = rows if rows is not None else []
        self._first = first
        self.joins = []

    def outerjoin(self, *args, **kwargs):
        return self

    def options(self, *args, **kwargs):
        return self

    def join(self, *args, **kwargs):
        self.joins.append(args)
        return self

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self._first

    def all(self):
        return list(self._rows)


class _FakeDB:
    """Minimal DB double that records the joins it was asked to perform."""

    def __init__(self, *, photos=None, album=None):
        self._photos = photos if photos is not None else []
        self._album = album
        self.added = []
        self.commits = 0
        self.photo_query = None

    def query(self, model):
        name = getattr(model, "__name__", str(model))
        if name == "Album":
            return _FakeQuery(first=self._album)
        self.photo_query = _FakeQuery(rows=self._photos)
        return self.photo_query

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.commits += 1


def _make_photo(photo_id="p-1", file_path="C:/photos/a.jpg", photo_time=None,
                make=None, model=None):
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


@pytest.fixture(autouse=True)
def _stub_album_trigger(monkeypatch):
    """The strategy triggers the album refresh through the real CRUD module."""
    import app.crud.album as album_crud

    monkeypatch.setattr(
        album_crud, "trigger_conditional_albums_update", lambda *args, **kwargs: None
    )

def _strategy():
    return tff.TimeFromFilenameStrategy()


ALBUM_ID = "6f1b0c1e-0b1e-4a3d-9c7a-9f0b2c3d4e5f"


# -------------------------------------------------------------------------
# album scoped query
# -------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_process_joins_album_photos_when_album_id_given(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    file_path = root / "a.jpg"
    file_path.write_bytes(b"x")

    photo = _make_photo("p-1", str(file_path), photo_time=datetime(2024, 6, 1, 12, 0, 0))
    db = _FakeDB(photos=[photo], album=SimpleNamespace(id=ALBUM_ID))

    with patch.object(tff.os.path, "exists", return_value=True), \
            patch.object(tff.os.path, "commonpath", return_value=str(root)), \
            patch.object(tff.os, "utime"):
        result = await _strategy().process(
            None, _task({"album_id": ALBUM_ID, "target_root_path": str(root)}), db
        )

    assert result["success_count"] == 1
    assert db.photo_query.joins, "album scoped query must join AlbumPhoto"


# -------------------------------------------------------------------------
# containment check blows up
# -------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_process_skips_photo_when_commonpath_raises(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    file_path = root / "a.jpg"
    file_path.write_bytes(b"x")

    photo = _make_photo("p-1", str(file_path), photo_time=datetime(2024, 6, 1, 12, 0, 0))
    db = _FakeDB(photos=[photo])

    with patch.object(tff.os.path, "exists", return_value=True), \
            patch.object(tff.os.path, "commonpath", side_effect=ValueError("different drive")):
        result = await _strategy().process(None, _task({"target_root_path": str(root)}), db)

    # The photo cannot be proven to live inside the target root -> skipped.
    assert result["success_count"] == 0
    assert result["total_processed"] == 0


# -------------------------------------------------------------------------
# utime failure
# -------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_process_survives_utime_failure(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    file_path = root / "a.jpg"
    file_path.write_bytes(b"x")

    photo = _make_photo("p-1", str(file_path), photo_time=datetime(2024, 6, 1, 12, 0, 0))
    db = _FakeDB(photos=[photo])

    with patch.object(tff.os.path, "exists", return_value=True), \
            patch.object(tff.os.path, "commonpath", return_value=str(root)), \
            patch.object(tff.os, "utime", side_effect=OSError("read-only volume")):
        result = await _strategy().process(None, _task({"target_root_path": str(root)}), db)

    # A file time that could not be written must not fail the photo.
    assert result["success_count"] == 1


# -------------------------------------------------------------------------
# piexif payloads without Exif / 0th sections
# -------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_process_creates_missing_exif_and_0th_sections(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    file_path = root / "a.jpg"
    file_path.write_bytes(b"x")

    photo = _make_photo("p-1", str(file_path), photo_time=datetime(2024, 6, 1, 12, 0, 0))
    db = _FakeDB(photos=[photo])

    inserted = {}

    def fake_dump(payload):
        inserted["payload"] = payload
        return b"exif-bytes"

    with patch.object(tff.os.path, "exists", return_value=True), \
            patch.object(tff.os.path, "commonpath", return_value=str(root)), \
            patch.object(tff.os, "utime"), \
            patch.object(tff.piexif, "load", return_value={}), \
            patch.object(tff.piexif, "dump", side_effect=fake_dump), \
            patch.object(tff.piexif, "insert", side_effect=lambda data, path: inserted.__setitem__("path", path)), \
            patch.object(tff, "get_exif_data", return_value={"Make": "Canon"}), \
            patch.object(tff, "Image"):
        result = await _strategy().process(
            None,
            _task({"target_root_path": str(root), "make": "Canon", "model": "EOS"}),
            db,
        )

    assert result["success_count"] == 1
    payload = inserted["payload"]
    assert payload["Exif"][tff.piexif.ExifIFD.DateTimeOriginal] == b"2024:06:01 12:00:00"
    assert payload["0th"][tff.piexif.ImageIFD.Make] == b"Canon"
    assert payload["0th"][tff.piexif.ImageIFD.Model] == b"EOS"


# -------------------------------------------------------------------------
# default serializer for binary EXIF values
# -------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_process_serialises_binary_exif_values(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    file_path = root / "a.jpg"
    file_path.write_bytes(b"x")

    photo = _make_photo("p-1", str(file_path), photo_time=datetime(2024, 6, 1, 12, 0, 0))
    db = _FakeDB(photos=[photo])

    with patch.object(tff.os.path, "exists", return_value=True), \
            patch.object(tff.os.path, "commonpath", return_value=str(root)), \
            patch.object(tff.os, "utime"), \
            patch.object(tff.piexif, "load", return_value={"Exif": {}, "0th": {}}), \
            patch.object(tff.piexif, "dump", return_value=b"exif-bytes"), \
            patch.object(tff.piexif, "insert"), \
            patch.object(tff, "get_exif_data", return_value={"Raw": b"\xff\xfe"}), \
            patch.object(tff, "Image"):
        await _strategy().process(None, _task({"target_root_path": str(root)}), db)

    assert photo.metadata_info is not None
    assert "Raw" in photo.metadata_info.exif_info


# -------------------------------------------------------------------------
# per photo failure
# -------------------------------------------------------------------------


class _BrokenPhoto:
    """A photo whose metadata cannot be read at all."""

    id = "p-boom"
    file_path = "C:/photos/boom.jpg"
    photo_time = datetime(2024, 6, 1, 12, 0, 0)

    @property
    def metadata_info(self):
        raise RuntimeError("metadata unavailable")


@pytest.mark.asyncio
async def test_process_keeps_going_after_a_broken_photo(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    (root / "boom.jpg").write_bytes(b"x")

    broken = _BrokenPhoto()
    broken.file_path = str(root / "boom.jpg")
    good = _make_photo("p-2", str(root / "good.jpg"), photo_time=datetime(2024, 6, 1, 12, 0, 0))
    (root / "good.jpg").write_bytes(b"x")

    db = _FakeDB(photos=[broken, good])

    with patch.object(tff.os.path, "exists", return_value=True), \
            patch.object(tff.os.path, "commonpath", return_value=str(root)), \
            patch.object(tff.os, "utime"):
        result = await _strategy().process(None, _task({"target_root_path": str(root)}), db)

    # The broken photo is skipped, the healthy one is still processed.
    assert result["success_count"] == 1
    assert result["total_processed"] == 2


# -------------------------------------------------------------------------
# periodic commit
# -------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_process_commits_periodically_for_large_batches(tmp_path):
    root = tmp_path / "root"
    root.mkdir()

    photos = []
    for index in range(50):
        path = root / f"p{index:03d}.jpg"
        path.write_bytes(b"x")
        photos.append(_make_photo(f"p-{index}", str(path), photo_time=datetime(2024, 6, 1, 12, 0, 0)))

    db = _FakeDB(photos=photos)

    with patch.object(tff.os.path, "exists", return_value=True), \
            patch.object(tff.os.path, "commonpath", return_value=str(root)), \
            patch.object(tff.os, "utime"):
        result = await _strategy().process(None, _task({"target_root_path": str(root)}), db)

    assert result["success_count"] == 50
    # initial commit + the every-50 checkpoint + the final commit
    assert db.commits == 3

