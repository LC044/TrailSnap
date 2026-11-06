"""Nightly watch 2026-11-04: desktop import and verification edge contracts."""
from contextlib import closing
from pathlib import Path
import sqlite3

import pytest

from app.utils import desktop_import
from app.utils import desktop_verification
from app.utils import portable_conversion

pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


def test_discovery_reports_unreadable_legacy_database(tmp_path):
    installation = tmp_path / "old-install"
    current = tmp_path / "current"
    (installation / "data").mkdir(parents=True)
    current.mkdir()
    (installation / "data/trailsnap.sqlite").write_bytes(b"not a sqlite database")

    result = desktop_import.discover_libraries(installation, current)

    assert result["candidates"] == [
        {
            "path": str(installation.resolve()),
            "photos": None,
            "error": "数据库暂时无法读取，请退出旧版后重试；请保留原目录。",
        }
    ]
    assert result["currentPhotos"] == 0


def test_conversion_space_rejects_disconnected_external_root(tmp_path, monkeypatch):
    source = tmp_path / "source"
    target = tmp_path / "target"
    program = tmp_path / "program"
    for path in (source, target, program):
        path.mkdir()
    (source / "data").mkdir()

    monkeypatch.setattr(
        portable_conversion,
        "preview_conversion",
        lambda _source: {
            "bytes": 1,
            "externalRoots": [{"available": False, "path": str(tmp_path / "missing")}],
        },
    )
    monkeypatch.setattr(
        portable_conversion,
        "validate_external_target",
        lambda _preview, _target: None,
    )

    with pytest.raises(ValueError, match="外部照片磁盘未连接"):
        desktop_import.conversion_space(source, target, program, True)


def test_cleanup_rejects_uppercase_uuid_operation_id(tmp_path):
    operation = "A0B1C2D3-E4F5-4A5B-8C6D-7E8F9012A3BC"
    with pytest.raises(ValueError, match="复制操作标识无效"):
        desktop_import.cleanup_staging(tmp_path / "target", operation)


def _create_verification_database(root: Path) -> Path:
    (root / "data").mkdir(parents=True)
    database = root / "data/trailsnap.sqlite"
    with closing(sqlite3.connect(database)) as db:
        db.execute(
            "CREATE TABLE storage_roots(id TEXT, owner_id TEXT, kind TEXT, location TEXT)"
        )
        db.execute(
            "CREATE TABLE photos(id TEXT, owner_id TEXT, file_path TEXT, storage_root_id TEXT, storage_relative_path TEXT)"
        )
        db.commit()
    return database


def test_photo_paths_resolves_managed_and_external_storage_roots(tmp_path):
    root = tmp_path / "library"
    database = _create_verification_database(root)
    with closing(sqlite3.connect(database)) as db:
        db.executemany(
            "INSERT INTO storage_roots VALUES (?,?,?,?)",
            [
                ("managed", "owner", "managed", "data/managed"),
                ("external", "owner", "external", str(root.parent / "external")),
            ],
        )
        db.executemany(
            "INSERT INTO photos VALUES (?,?,?,?,?)",
            [
                ("managed-photo", "owner", "legacy.jpg", "managed", "photo.jpg"),
                ("external-photo", "owner", "legacy.mp4", "external", "video.mp4"),
            ],
        )
        db.commit()

        rows = list(desktop_verification.photo_paths(db, root))

    assert rows == [
        (
            "managed-photo",
            "owner",
            str((root / "data/managed/photo.jpg").resolve()),
        ),
        (
            "external-photo",
            "owner",
            str((root.parent / "external/video.mp4").resolve()),
        ),
    ]


def test_photo_paths_rejects_invalid_storage_reference(tmp_path):
    root = tmp_path / "library"
    database = _create_verification_database(root)
    with closing(sqlite3.connect(database)) as db:
        db.execute(
            "INSERT INTO photos VALUES (?,?,?,?,?)",
            ("broken-photo", "owner", "legacy.jpg", "missing-root", "photo.jpg"),
        )
        db.commit()

        with pytest.raises(ValueError, match="存储目录引用无效"):
            list(desktop_verification.photo_paths(db, root))
