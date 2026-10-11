"""Regression coverage for offline desktop library relocation."""

import json
from contextlib import closing
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
from types import SimpleNamespace

import pytest

from app.utils.desktop_data_migration import MARKER, migrate_data_directory, rebase_value

pytestmark = pytest.mark.smoke


def library(root):
    (root / "data/users/u/thumbnails").mkdir(parents=True)
    (root / "data/users/u/thumbnails/photo.jpg").write_bytes(b"thumbnail")
    (root / "models").mkdir()
    (root / "models/model.bin").write_bytes(b"model")
    (root / "runtime/llama.cpp").mkdir(parents=True)
    (root / "runtime/llama.cpp/llama-server.exe").write_bytes(b"runtime")
    (root / "ai-config.json").write_text(json.dumps({"model": str(root / "models/model.bin")}), encoding="utf-8")
    database = root / "data/trailsnap.sqlite"
    with closing(sqlite3.connect(database)) as db, db:
        db.executescript('CREATE TABLE photos (id TEXT PRIMARY KEY, file_path TEXT); CREATE TABLE users (id TEXT PRIMARY KEY, settings JSON); CREATE TABLE system_state (key TEXT PRIMARY KEY, value TEXT);')
        db.executemany("INSERT INTO photos VALUES (?, ?)", [
            ("local", str(root / "data/users/u/uploads/photo.jpg")),
            ("external", str(root.parent / "external/photo.jpg")),
            ("similar", str(root.with_name(root.name + "-other") / "photo.jpg")),
        ])
        db.execute("INSERT INTO users VALUES ('u', ?)", (json.dumps({"storage": {"storage_path": str(root / "data"), "external_directories": [str(root.parent / "external")]}}),))
        db.execute("INSERT INTO system_state VALUES ('paths', ?)", (json.dumps({"paths": [str(root / "models")]}),))
        db.execute("INSERT INTO system_state VALUES ('plain', 'not json')")
    return database


def test_migration_rebases_managed_paths_and_preserves_original_and_external_files(tmp_path):
    source, target = tmp_path / "旧数据", tmp_path / "新数据"
    database = library(source)
    original = database.read_bytes()
    migrate_data_directory(source, target)
    assert database.read_bytes() == original
    assert (target / "data/users/u/thumbnails/photo.jpg").read_bytes() == b"thumbnail"
    assert (target / "models/model.bin").read_bytes() == b"model"
    assert (target / "runtime/llama.cpp/llama-server.exe").read_bytes() == b"runtime"
    with closing(sqlite3.connect(target / "data/trailsnap.sqlite")) as db:
        paths = dict(db.execute("SELECT id, file_path FROM photos"))
        assert paths["local"] == str(target / "data/users/u/uploads/photo.jpg")
        assert paths["external"] == str(tmp_path / "external/photo.jpg")
        assert paths["similar"] == str(source.with_name(source.name + "-other") / "photo.jpg")
        settings = json.loads(db.execute("SELECT settings FROM users").fetchone()[0])
        assert settings["storage"]["storage_path"] == str(target / "data")
        assert settings["storage"]["external_directories"] == [str(tmp_path / "external")]
        assert json.loads(db.execute("SELECT value FROM system_state WHERE key='paths'").fetchone()[0])["paths"] == [str(target / "models")]
    assert json.loads((target / "ai-config.json").read_text(encoding="utf-8"))["model"] == str(target / "models/model.bin")
    # Retry after a crash between publishing the directory and saving launcher config.
    migrate_data_directory(source, target)


@pytest.mark.parametrize("relation", ["same", "child", "parent"])
def test_migration_rejects_overlapping_paths(tmp_path, relation):
    source = tmp_path / "source"
    library(source)
    target = {"same": source, "child": source / "child", "parent": tmp_path}[relation]
    with pytest.raises(ValueError, match="互相包含"):
        migrate_data_directory(source, target)


def test_nonempty_destination_is_never_overwritten(tmp_path):
    source, target = tmp_path / "source", tmp_path / "target"
    library(source)
    target.mkdir()
    (target / "keep.txt").write_text("keep")
    with pytest.raises(ValueError, match="空文件夹"):
        migrate_data_directory(source, target)
    assert (target / "keep.txt").read_text() == "keep"


def test_corrupt_database_rolls_back_without_publishing_copy(tmp_path):
    source, target = tmp_path / "source", tmp_path / "target"
    database = library(source)
    database.write_bytes(b"corrupt database")
    target.mkdir()
    with pytest.raises(sqlite3.DatabaseError):
        migrate_data_directory(source, target)
    assert database.read_bytes() == b"corrupt database"
    assert list(target.iterdir()) == []
    assert not list(tmp_path.glob(".trailsnap-migration-*"))


def test_insufficient_disk_space_leaves_original_untouched(tmp_path, monkeypatch):
    source, target = tmp_path / "source", tmp_path / "target"
    library(source)
    monkeypatch.setattr(shutil, "disk_usage", lambda _: shutil._ntuple_diskusage(100, 100, 0))
    with pytest.raises(ValueError, match="空间不足"):
        migrate_data_directory(source, target)
    assert (source / "models/model.bin").read_bytes() == b"model"
    assert not target.exists()


def test_wal_database_is_recovered_and_rebased(tmp_path):
    source, target = tmp_path / "source", tmp_path / "target"
    database = library(source)
    connection = sqlite3.connect(database)
    try:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("INSERT INTO photos VALUES ('wal', ?)", (str(source / "data/wal.jpg"),))
        connection.commit()
        assert database.with_name(database.name + "-wal").exists()
        migrate_data_directory(source, target)
        with closing(sqlite3.connect(target / "data/trailsnap.sqlite")) as db:
            assert db.execute("SELECT file_path FROM photos WHERE id='wal'").fetchone()[0] == str(target / "data/wal.jpg")
    finally:
        connection.close()


def test_rebase_handles_slashes_and_path_boundaries(tmp_path):
    source, target = tmp_path / "source", tmp_path / "target"
    assert rebase_value((source / "photo.jpg").as_posix(), source, target) == str(target / "photo.jpg")
    assert rebase_value(str(source) + "-other/photo.jpg", source, target) == str(source) + "-other/photo.jpg"


def test_frozen_entry_cli_migrates_without_starting_server(tmp_path):
    source, target = tmp_path / "source", tmp_path / "target"
    library(source)
    entry = Path(__file__).resolve().parents[2] / "desktop_entry.py"
    result = subprocess.run(
        [sys.executable, str(entry), "--migrate-data", str(source), str(target), "--parent-pid", str(os.getpid())],
        capture_output=True, text=True, encoding="utf-8", timeout=30,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    assert result.returncode == 0, result.stderr
    assert (target / MARKER).is_file()
    assert not (target / "data/desktop_session.secret").exists()


def test_unreadable_source_directory_does_not_publish_incomplete_copy(tmp_path, monkeypatch):
    source, target = tmp_path / "source", tmp_path / "target"
    library(source)
    def denied_walk(root, *, onerror):
        onerror(PermissionError("unreadable source"))
        yield
    monkeypatch.setattr(os, "walk", denied_walk)
    with pytest.raises(PermissionError, match="unreadable"):
        migrate_data_directory(source, target)
    assert not target.exists()


def test_active_old_sidecar_prevents_migration(tmp_path, monkeypatch):
    import psutil
    from app.utils import desktop_data_migration as migration

    source, target = tmp_path / "source", tmp_path / "target"
    library(source)
    clock = iter([0, 6])
    monkeypatch.setattr(migration, "time", SimpleNamespace(monotonic=lambda: next(clock), sleep=lambda _: None))
    process = SimpleNamespace(info={"pid": 99999999, "name": "trailsnap-server.exe", "cwd": str(source / "data")})
    monkeypatch.setattr(psutil, "process_iter", lambda _: [process])
    with pytest.raises(ValueError, match="后台服务"):
        migrate_data_directory(source, target)
    assert not target.exists()
