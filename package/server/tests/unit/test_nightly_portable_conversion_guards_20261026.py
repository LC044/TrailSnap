"""Nightly coverage for the legacy-library guards of ``app/utils/portable_conversion.py``.

The 2026-10-26 backend coverage scan listed ``utils/portable_conversion.py`` as
the single largest gap (41.8%, 167 missed lines).  Almost all of those lines sit
in the two places where a wrong answer destroys a user's photo library:

* ``validate_library_source`` / ``conversion_exclusions`` decide *which* folder
  is the old library and *what* must never be copied or deleted.
* ``convert_to_portable`` refuses impossible conversions before a single byte
  is written.

None of the happy paths need a real desktop installation, so the guards are
driven directly with throw-away directories and a minimal legacy SQLite file.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

pytestmark = [pytest.mark.smoke]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _legacy_library(root: Path, *, users=(), photos=()) -> Path:
    """Create a directory that looks like an old (pre-portable) installation."""
    data = root / "data"
    data.mkdir(parents=True, exist_ok=True)
    database = data / "trailsnap.sqlite"
    connection = sqlite3.connect(database)
    try:
        connection.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, settings TEXT)")
        connection.execute("CREATE TABLE photos (id INTEGER PRIMARY KEY, owner_id INTEGER, file_path TEXT)")
        connection.execute("CREATE TABLE albums (id INTEGER PRIMARY KEY)")
        connection.execute("CREATE TABLE tasks (id INTEGER PRIMARY KEY)")
        for owner, settings in users:
            connection.execute("INSERT INTO users (id, settings) VALUES (?, ?)", (owner, settings))
        for photo, owner, path in photos:
            connection.execute("INSERT INTO photos (id, owner_id, file_path) VALUES (?, ?, ?)",
                               (photo, owner, path))
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


# ---------------------------------------------------------------------------
# validate_library_source
# ---------------------------------------------------------------------------


def test_validate_library_source_rejects_a_relative_path(tmp_path, monkeypatch):
    from app.utils import portable_conversion

    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError, match="完整路径"):
        portable_conversion.validate_library_source(Path("legacy"))


def test_validate_library_source_rejects_a_missing_directory(tmp_path):
    from app.utils import portable_conversion

    with pytest.raises(ValueError, match="不存在或无法访问"):
        portable_conversion.validate_library_source(tmp_path / "missing")


def test_validate_library_source_rejects_a_file(tmp_path):
    from app.utils import portable_conversion

    database = tmp_path / "trailsnap.sqlite"
    database.write_bytes(b"")
    with pytest.raises(ValueError, match="不要选择数据库文件"):
        portable_conversion.validate_library_source(database)


def test_validate_library_source_points_at_the_data_subfolder(tmp_path):
    from app.utils import portable_conversion

    data = tmp_path / "data"
    data.mkdir()
    (data / "trailsnap.sqlite").write_bytes(b"")
    with pytest.raises(ValueError, match="选中了 data 子文件夹"):
        portable_conversion.validate_library_source(data)


def test_validate_library_source_rejects_a_new_instance_directory(tmp_path):
    from app.utils import portable_conversion

    library = tmp_path / "instance"
    (library / "userdata" / "data").mkdir(parents=True)
    (library / "userdata" / "data" / "trailsnap.sqlite").write_bytes(b"")
    with pytest.raises(ValueError, match="新版本的实例目录"):
        portable_conversion.validate_library_source(library)


def test_validate_library_source_requires_the_legacy_database(tmp_path):
    from app.utils import portable_conversion

    library = tmp_path / "empty"
    library.mkdir()
    with pytest.raises(ValueError, match="未找到旧图库数据库"):
        portable_conversion.validate_library_source(library)


def test_validate_library_source_accepts_a_legacy_root(tmp_path):
    from app.utils import portable_conversion

    library = _legacy_library(tmp_path / "legacy")
    assert portable_conversion.validate_library_source(library) == library.resolve()


# ---------------------------------------------------------------------------
# conversion_exclusions
# ---------------------------------------------------------------------------


def test_conversion_exclusions_always_protect_the_new_installation(tmp_path):
    from app.utils import portable_conversion

    library = _legacy_library(tmp_path / "legacy")
    excluded = portable_conversion.conversion_exclusions(library)
    assert {"server", "ai", "trailsnap-desktop.exe", "uninstall.exe"} <= excluded


def test_conversion_exclusions_detect_a_portable_installation(tmp_path):
    from app.utils import portable_conversion

    library = _legacy_library(tmp_path / "legacy")
    (library / "portable.json").write_text(json.dumps({"activeBuild": "1.0"}), encoding="utf-8")
    (library / "runtime.dll").write_bytes(b"")
    excluded = portable_conversion.conversion_exclusions(library)
    assert {"app", "maintenance", "userdata", "TrailSnap.exe", "portable.json"} <= excluded
    assert "runtime.dll" in excluded


def test_conversion_exclusions_exclude_the_relative_instance_data_root(tmp_path):
    from app.utils import portable_conversion

    library = _legacy_library(tmp_path / "legacy")
    (library / "instance.json").write_text(
        json.dumps({"dataRoot": {"kind": "relative", "path": "userdata"}}), encoding="utf-8")
    excluded = portable_conversion.conversion_exclusions(library)
    assert "userdata" in excluded
    assert "instance.json" in excluded


def test_conversion_exclusions_reject_an_invalid_instance_descriptor(tmp_path):
    from app.utils import portable_conversion

    library = _legacy_library(tmp_path / "legacy")
    (library / "instance.json").write_text(json.dumps({"dataRoot": {"kind": "elsewhere"}}), encoding="utf-8")
    with pytest.raises(ValueError, match="instance.json 数据位置无效"):
        portable_conversion.conversion_exclusions(library)


# ---------------------------------------------------------------------------
# validate_external_target
# ---------------------------------------------------------------------------


def test_validate_external_target_rejects_an_overlapping_root(tmp_path):
    from app.utils import portable_conversion

    external = tmp_path / "external"
    external.mkdir()
    preview = {"externalRoots": [{"ownerId": "1", "path": str(external), "available": True}]}

    with pytest.raises(ValueError, match="不能与外部照片文件夹相同"):
        portable_conversion.validate_external_target(preview, external)
    with pytest.raises(ValueError, match="不能与外部照片文件夹相同"):
        portable_conversion.validate_external_target(preview, external / "inner")
    with pytest.raises(ValueError, match="不能与外部照片文件夹相同"):
        portable_conversion.validate_external_target(preview, tmp_path)


def test_validate_external_target_accepts_an_unrelated_target(tmp_path):
    from app.utils import portable_conversion

    external = tmp_path / "external"
    external.mkdir()
    target = tmp_path / "new-instance"
    target.mkdir()
    preview = {"externalRoots": [{"ownerId": "1", "path": str(external), "available": True}]}
    portable_conversion.validate_external_target(preview, target)


# ---------------------------------------------------------------------------
# convert_to_portable guards
# ---------------------------------------------------------------------------


def test_convert_to_portable_rejects_identical_directories(tmp_path):
    from app.utils import portable_conversion

    library = _legacy_library(tmp_path / "legacy")
    program = _desktop_program(tmp_path / "program")
    launcher = tmp_path / "launcher.exe"
    launcher.write_bytes(b"MZ")

    with pytest.raises(ValueError, match="新旧目录不能相同"):
        portable_conversion.convert_to_portable(library, library, program, launcher)


def test_convert_to_portable_requires_an_empty_target(tmp_path):
    from app.utils import portable_conversion

    library = _legacy_library(tmp_path / "legacy")
    program = _desktop_program(tmp_path / "program")
    launcher = tmp_path / "launcher.exe"
    launcher.write_bytes(b"MZ")
    target = tmp_path / "new-instance"
    target.mkdir()
    (target / "leftover.txt").write_text("x", encoding="utf-8")

    with pytest.raises(ValueError, match="便携实例目标必须是空文件夹"):
        portable_conversion.convert_to_portable(library, target, program, launcher)


def test_convert_to_portable_requires_a_complete_desktop_program(tmp_path):
    from app.utils import portable_conversion

    library = _legacy_library(tmp_path / "legacy")
    program = tmp_path / "program"
    program.mkdir()
    launcher = tmp_path / "launcher.exe"
    launcher.write_bytes(b"MZ")
    target = tmp_path / "new-instance"
    target.mkdir()

    with pytest.raises(ValueError, match="转换需要完整的新桌面程序"):
        portable_conversion.convert_to_portable(library, target, program, launcher)


def test_convert_to_portable_rejects_an_unavailable_external_gallery(tmp_path):
    from app.utils import portable_conversion

    missing = tmp_path / "detached-disk"
    library = _legacy_library(tmp_path / "legacy", users=[(1, json.dumps(
        {"storage": {"external_directories": [str(missing)]}}))])
    program = _desktop_program(tmp_path / "program")
    launcher = tmp_path / "launcher.exe"
    launcher.write_bytes(b"MZ")
    target = tmp_path / "new-instance"
    target.mkdir()

    with pytest.raises(ValueError, match="外部图库磁盘不可用"):
        portable_conversion.convert_to_portable(library, target, program, launcher, copy_external=True)


def test_convert_to_portable_rejects_unregistered_photos(tmp_path):
    from app.utils import portable_conversion

    external = tmp_path / "external"
    external.mkdir()
    stray = tmp_path / "elsewhere"
    stray.mkdir()
    library = _legacy_library(
        tmp_path / "legacy",
        users=[(1, json.dumps({"storage": {"external_directories": [str(external)]}}))],
        photos=[(1, 1, str(stray / "unknown.jpg"))],
    )
    program = _desktop_program(tmp_path / "program")
    launcher = tmp_path / "launcher.exe"
    launcher.write_bytes(b"MZ")
    target = tmp_path / "new-instance"
    target.mkdir()

    with pytest.raises(ValueError, match="存在未登记存储根的照片"):
        portable_conversion.convert_to_portable(library, target, program, launcher, copy_external=True)
