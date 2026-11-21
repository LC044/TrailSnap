"""Portable-library conversion preview guards."""
import json
import sqlite3

import pytest

from app.utils.portable_conversion import _preview_conversion

pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


def _make_library(tmp_path, settings=None, photos=()):
    source = tmp_path / "library"
    (source / "data").mkdir(parents=True)
    db = sqlite3.connect(source / "data" / "trailsnap.sqlite")
    db.execute("CREATE TABLE users (id TEXT, settings TEXT)")
    db.execute("CREATE TABLE photos (id TEXT, owner_id TEXT, file_path TEXT)")
    db.execute("CREATE TABLE albums (id TEXT)")
    db.execute("CREATE TABLE tasks (id TEXT)")
    db.execute("INSERT INTO users VALUES (?, ?)", ("u1", json.dumps(settings or {})))
    for photo_id, owner_id, file_path in photos:
        db.execute("INSERT INTO photos VALUES (?, ?, ?)", (photo_id, owner_id, file_path))
    db.commit()
    db.close()
    return source


def test_preview_conversion_reports_source_and_table_counts(tmp_path):
    source = _make_library(tmp_path)
    result = _preview_conversion(source)
    assert result["source"] == str(source)
    assert result["counts"] == {"users": 1, "photos": 0, "albums": 0, "tasks": 0}
    assert result["unregisteredPhotos"] == 0
    assert result["bytes"] > 0


def test_preview_conversion_lists_external_roots_as_unavailable(tmp_path):
    outside = tmp_path / "external"
    source = _make_library(tmp_path, settings={"storage": {"photo_storage_path": str(outside)}})
    result = _preview_conversion(source)
    assert len(result["externalRoots"]) == 1
    assert result["externalRoots"][0]["ownerId"] == "u1"
    assert result["externalRoots"][0]["available"] is False


def test_preview_conversion_counts_photos_outside_known_roots(tmp_path):
    outside = tmp_path / "external"
    outside.mkdir()
    source = _make_library(tmp_path, photos=[("p1", "u1", str(outside / "a.jpg"))])
    result = _preview_conversion(source)
    assert result["counts"]["photos"] == 1
    assert result["unregisteredPhotos"] == 1


def test_preview_conversion_ignores_excluded_directories(tmp_path):
    source = _make_library(tmp_path)
    baseline = _preview_conversion(source)["bytes"]
    server_dir = source / "server"
    server_dir.mkdir()
    (server_dir / "big.bin").write_bytes(b"0" * (1024 * 1024))
    result = _preview_conversion(source)
    assert result["bytes"] - baseline < 65536

