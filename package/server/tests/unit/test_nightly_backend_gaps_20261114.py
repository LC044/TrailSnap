"""Nightly watch 2026-11-14: backend coverage gaps.

Targets (missed lines reported by tests/artifacts/nightly/2026-11-13/coverage-backend.xml):

- app/utils/desktop_data_migration.py (209-210 empty target replacement,
  181-192 byte-progress copy + digest verification)
- app/service/tasks/basic.py (98-105 exif serialisation, 122-123 md5 fallback,
  148-156 failure result)
- app/utils/portable_conversion.py (165-166 disk space guard,
  168-172 operation-scoped staging directory)
- app/service/tasks/metadata.py (342-351 exif serialisation,
  407-412 dimension back-fill)

All cases are hermetic: no network, no real model, no external disk.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.service.tasks import basic as basic_tasks
from app.service.tasks import metadata as metadata_tasks
from app.utils.desktop_data_migration import migrate_data_directory
from app.utils.portable_conversion import convert_to_portable


pytestmark = pytest.mark.smoke


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _library(root: Path) -> Path:
    """A minimal legacy library that ``migrate_data_directory`` accepts."""
    (root / "data/users/u/thumbnails").mkdir(parents=True)
    (root / "data/users/u/thumbnails/photo.jpg").write_bytes(b"thumbnail")
    database = root / "data/trailsnap.sqlite"
    with closing(sqlite3.connect(database)) as db, db:
        db.executescript(
            "CREATE TABLE photos (id TEXT PRIMARY KEY, file_path TEXT);"
            "CREATE TABLE users (id TEXT PRIMARY KEY, settings JSON);"
            "CREATE TABLE system_state (key TEXT PRIMARY KEY, value TEXT);"
        )
        db.execute("INSERT INTO photos VALUES (?, ?)", ("local", str(root / "data/users/u/uploads/photo.jpg")))
        db.execute("INSERT INTO users VALUES ('u', ?)", (json.dumps({"storage": {"storage_path": str(root / "data")}}),))
        db.execute("INSERT INTO system_state VALUES ('paths', ?)", (json.dumps({"paths": []}),))
    return database


def _legacy_library(root: Path) -> Path:
    """Legacy (pre-portable) installation layout accepted by convert_to_portable."""
    data = root / "data"
    data.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(data / "trailsnap.sqlite")
    try:
        connection.execute("CREATE TABLE users (id TEXT PRIMARY KEY, settings TEXT)")
        connection.execute(
            "CREATE TABLE photos (id TEXT PRIMARY KEY, owner_id TEXT, file_path TEXT, "
            "storage_root_id TEXT, storage_relative_path TEXT)"
        )
        connection.execute("CREATE TABLE albums (id TEXT PRIMARY KEY)")
        connection.execute("CREATE TABLE tasks (id TEXT PRIMARY KEY, payload TEXT)")
        connection.execute(
            "CREATE TABLE storage_roots (id TEXT PRIMARY KEY, owner_id TEXT, name TEXT, kind TEXT, location TEXT)"
        )
        connection.commit()
    finally:
        connection.close()
    return root


def _desktop_program(root: Path) -> Path:
    program = root / "program"
    (program / "server").mkdir(parents=True, exist_ok=True)
    (program / "trailsnap-desktop.exe").write_bytes(b"MZ")
    (program / "server" / "trailsnap-server.exe").write_bytes(b"MZ")
    return program


def _launcher(root: Path) -> Path:
    launcher = root / "portable-launcher.exe"
    launcher.write_bytes(b"MZ")
    return launcher


# ---------------------------------------------------------------------------
# app/utils/desktop_data_migration.py
# ---------------------------------------------------------------------------


def test_migration_replaces_an_existing_empty_target_directory(tmp_path):
    """An empty destination folder left over from a previous attempt is
    replaced instead of being treated as a non-empty destination."""
    source, target = tmp_path / "source", tmp_path / "target"
    _library(source)
    target.mkdir()

    migrate_data_directory(source, target)

    assert (target / "data/users/u/thumbnails/photo.jpg").read_bytes() == b"thumbnail"
    assert (target / "data" / "trailsnap.sqlite").is_file()


def test_migration_reports_byte_progress_and_rejects_a_corrupted_copy(tmp_path, monkeypatch):
    """The byte-progress copy path verifies the digest of every copied file
    and refuses to publish a copy whose content changed on disk."""
    source, target = tmp_path / "source", tmp_path / "target"
    _library(source)

    seen = []
    counter = {"n": 0}

    class _FakeDigest:
        def __init__(self):
            counter["n"] += 1
            self._value = counter["n"]

        def update(self, data):  # pragma: no cover - trivial
            return None

        def digest(self):
            # Every file gets its own digest value, so the copied file never
            # matches the digest of the file it was copied from.
            return bytes([self._value]) * 32

    monkeypatch.setattr(hashlib, "sha256", _FakeDigest)

    with pytest.raises(ValueError, match="复制文件校验失败"):
        migrate_data_directory(
            source,
            target,
            byte_progress=lambda done, total: seen.append((done, total)),
        )

    assert seen, "byte progress callback was never invoked"
    assert not (target / "data" / "trailsnap.sqlite").exists()


# ---------------------------------------------------------------------------
# app/service/tasks/basic.py
# ---------------------------------------------------------------------------


def _patch_basic(monkeypatch, meta):
    monkeypatch.setattr(basic_tasks.storage, "update_storage_root_cache", lambda *a, **k: None)
    monkeypatch.setattr(basic_tasks.storage, "get_file_size", lambda *a, **k: 123)
    monkeypatch.setattr(basic_tasks.storage, "get_image_dimensions", lambda *a, **k: (10, 20, 0))
    monkeypatch.setattr(basic_tasks.storage, "generate_thumbnail", lambda *a, **k: None)
    monkeypatch.setattr(basic_tasks.exif, "extract_metadata", lambda *a, **k: meta)
    monkeypatch.setattr(basic_tasks, "calculate_file_md5", lambda *a, **k: "d41d8cd98f00b204e9800998ecf8427e")


def test_process_basic_cpu_job_returns_a_failure_result_when_metadata_extraction_fails(monkeypatch, tmp_path):
    """A metadata extraction error is reported as a failed job result instead
    of propagating out of the worker."""
    monkeypatch.setattr(basic_tasks.storage, "update_storage_root_cache", lambda *a, **k: None)

    def _boom(*args, **kwargs):
        raise RuntimeError("metadata backend unavailable")

    monkeypatch.setattr(basic_tasks.exif, "extract_metadata", _boom)
    missing = tmp_path / "missing.txt"
    missing.write_text("not an image", encoding="utf-8")

    result = basic_tasks.process_basic_cpu_job(
        str(missing), MagicMock(), str(tmp_path), "u"
    )

    assert result["success"] is False
    assert "metadata backend unavailable" in result["error"]


def test_process_basic_cpu_job_serializes_binary_exif_values(monkeypatch, tmp_path):
    """EXIF payloads may contain bytes; they are stored as a JSON string."""
    meta = {
        "exif_info": {"Make": "Canon", "Serial": b"\x00\x01", "Tags": {"a", "b"}},
        "width": None,
        "height": None,
        "duration": None,
    }
    _patch_basic(monkeypatch, meta)
    photo = tmp_path / "photo.txt"
    photo.write_text("not an image", encoding="utf-8")

    result = basic_tasks.process_basic_cpu_job(
        str(photo), MagicMock(), str(tmp_path), "u"
    )

    assert result["success"] is True
    stored = json.loads(result["meta"]["exif_info"])
    assert stored["Make"] == "Canon"
    assert isinstance(stored["Serial"], str)
    assert isinstance(stored["Tags"], str)


def test_process_basic_cpu_job_falls_back_to_the_file_md5_helper(monkeypatch, tmp_path):
    """A non-image payload has no inline digest, so the md5 helper is used."""
    meta = {"exif_info": {}, "width": None, "height": None, "duration": None}
    _patch_basic(monkeypatch, meta)
    calls = []
    monkeypatch.setattr(
        basic_tasks, "calculate_file_md5", lambda path: calls.append(path) or "0" * 32
    )
    clip = tmp_path / "clip.txt"
    clip.write_text("not an image", encoding="utf-8")

    result = basic_tasks.process_basic_cpu_job(
        str(clip), MagicMock(), str(tmp_path), "u"
    )

    assert result["success"] is True
    assert result["md5_hash"] == "0" * 32
    assert calls == [str(clip)]


# ---------------------------------------------------------------------------
# app/utils/portable_conversion.py
# ---------------------------------------------------------------------------


def test_convert_to_portable_refuses_to_start_without_enough_disk_space(tmp_path, monkeypatch):
    """The conversion stops before touching the target when the destination
    disk cannot hold the library, the program and the snapshot."""
    source = _legacy_library(tmp_path / "legacy")
    program = _desktop_program(tmp_path)
    launcher = _launcher(tmp_path)
    target = tmp_path / "portable"
    target.mkdir()

    monkeypatch.setattr(
        "app.utils.desktop_import.conversion_space",
        lambda *args, **kwargs: {"enough": False},
    )

    with pytest.raises(ValueError, match="空间不足"):
        convert_to_portable(source, target, program, launcher)


def test_convert_to_portable_uses_the_operation_scoped_staging_directory(tmp_path, monkeypatch):
    """An import operation reuses a deterministic staging directory and records
    the operation id in it, so a crashed import can be resumed."""
    source = _legacy_library(tmp_path / "legacy")
    program = _desktop_program(tmp_path)
    launcher = _launcher(tmp_path)
    target = tmp_path / "portable"
    target.mkdir()

    monkeypatch.setenv("TS_IMPORT_OPERATION", "op-123")
    monkeypatch.setattr(
        "app.utils.desktop_import.conversion_space",
        lambda *args, **kwargs: {"enough": True},
    )
    monkeypatch.setattr(
        "app.utils.desktop_import.cleanup_staging",
        lambda *args, **kwargs: None,
    )

    import app.utils.portable_conversion as portable_conversion

    written = []
    real_write_json = portable_conversion.write_json

    def _spy(path, value):
        written.append((Path(path), value))
        return real_write_json(path, value)

    monkeypatch.setattr(portable_conversion, "write_json", _spy)

    def _stop(*args, **kwargs):
        raise RuntimeError("stop after staging")

    monkeypatch.setattr(
        "app.utils.desktop_data_migration.migrate_data_directory", _stop
    )

    with pytest.raises(RuntimeError, match="stop after staging"):
        convert_to_portable(source, target, program, launcher)

    operation_files = [
        (path, value) for path, value in written if path.name == "import-operation.json"
    ]
    assert operation_files, "the import operation marker was never written"
    path, value = operation_files[0]
    assert path.parent.name == ".trailsnap-portable-op-123"
    assert value["operationId"] == "op-123"
    assert value["target"] == str(target)


# ---------------------------------------------------------------------------
# app/service/tasks/metadata.py
# ---------------------------------------------------------------------------


def _photo(photo_id, filename):
    return SimpleNamespace(
        id=photo_id,
        filename=filename,
        width=None,
        height=None,
        duration=None,
        owner_id="u",
        panorama_override=None,
        processed_tasks=None,
        file_type=None,
    )


def test_update_photo_metadata_from_extract_serializes_binary_exif_values():
    """Binary EXIF values are stored as a JSON string, never as raw bytes."""
    photo = _photo("photo-1", "photo.jpg")
    db_meta = SimpleNamespace(photo_id="photo-1")
    db = MagicMock()

    metadata_tasks.update_photo_metadata_from_extract(
        db,
        photo,
        {
            "exif_info": {"Make": "Canon", "Raw": b"\x00\x01"},
            "width": None,
            "height": None,
            "duration": None,
        },
        commit=False,
        metadata_cache={"photo-1": db_meta},
        scenes=[],
    )

    stored = json.loads(db_meta.exif_info)
    assert stored["Make"] == "Canon"
    assert isinstance(stored["Raw"], str)


def test_update_photo_metadata_from_extract_fills_missing_dimensions():
    """Dimensions parsed from the container are written only when the photo
    does not carry them yet, so PROCESS_BASIC results are never overwritten."""
    photo = _photo("photo-2", "clip.mp4")
    db_meta = SimpleNamespace(photo_id="photo-2")
    db = MagicMock()

    metadata_tasks.update_photo_metadata_from_extract(
        db,
        photo,
        {"exif_info": {}, "width": 1920, "height": 1080, "duration": 12.5},
        commit=False,
        metadata_cache={"photo-2": db_meta},
        scenes=[],
    )

    assert photo.width == 1920
    assert photo.height == 1080
    assert photo.duration == 12.5


