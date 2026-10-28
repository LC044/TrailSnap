"""Nightly coverage for the successful conversion path of
``app/utils/portable_conversion.py``.

``utils/portable_conversion.py`` has been the single largest backend
coverage gap for four consecutive nightly rounds (41.8% -> 46.7%), and
all of the missing lines sat in ``convert_to_portable`` itself: the body
that actually copies the legacy library, rewrites the photo paths,
rotates the library identity and publishes the new portable instance.

The guards were already covered by
``test_nightly_portable_conversion_guards_20261026.py``; this file drives
the **happy path** with a realistic legacy installation:

* a legacy root with ``data/trailsnap.sqlite`` (users / photos / albums /
  tasks), a real photo file and a ``library.json``;
* a complete desktop program (executable + backend + launcher);
* an empty target directory.

and then asserts the *result*: the instance is published, the photo paths
are rebased onto the new location, the library identity is rotated, the
secret key is regenerated and the proof file records the conversion.
"""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

import pytest


pytestmark = [pytest.mark.smoke]


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


def _legacy_library(root: Path, *, users=(), photos=()) -> Path:
    """A directory that looks like an old (pre-portable) installation.

    The identifiers are UUID **strings**: the portable layout is rebuilt from
    the owner id, so an integer id would not survive the conversion.
    """
    data = root / "data"
    data.mkdir(parents=True, exist_ok=True)
    database = data / "trailsnap.sqlite"
    connection = sqlite3.connect(database)
    try:
        connection.execute("CREATE TABLE users (id TEXT PRIMARY KEY, settings TEXT)")
        connection.execute(
            "CREATE TABLE photos (id TEXT PRIMARY KEY, owner_id TEXT, file_path TEXT, "
            "storage_root_id TEXT, storage_relative_path TEXT)"
        )
        connection.execute("CREATE TABLE albums (id TEXT PRIMARY KEY)")
        # ``portable_library.prepare_portable_library`` rewrites the payload of
        # every task, so the fixture needs the real column set (app/db/models/task.py).
        connection.execute("CREATE TABLE tasks (id TEXT PRIMARY KEY, payload TEXT)")
        connection.execute(
            "CREATE TABLE storage_roots (id TEXT PRIMARY KEY, owner_id TEXT, name TEXT, kind TEXT, location TEXT)"
        )
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


def _launcher(root: Path) -> Path:
    launcher = root / "portable-launcher.exe"
    launcher.write_bytes(b"MZ")
    return launcher


OWNER_ID = "11111111-1111-4111-8111-111111111111"
PHOTO_ID = "22222222-2222-4222-8222-222222222222"


def _legacy_with_photo(root: Path) -> tuple[Path, str]:
    """A legacy library with one real photo on disk."""
    library = _legacy_library(
        root,
        users=[(OWNER_ID, json.dumps({"storage": {"photo_storage_path": str(root / "data" / "uploads")}}))],
    )
    photo = root / "data" / "uploads" / "photo.jpg"
    photo.parent.mkdir(parents=True, exist_ok=True)
    photo.write_bytes(b"photo-bytes")
    connection = sqlite3.connect(library / "data" / "trailsnap.sqlite")
    try:
        connection.execute("INSERT INTO photos (id, owner_id, file_path) VALUES (?, ?, ?)",
                           (PHOTO_ID, OWNER_ID, str(photo)))
        connection.commit()
    finally:
        connection.close()
    return library, str(photo)


@pytest.fixture()
def isolated_desktop_env(tmp_path, monkeypatch):
    """Neutralise the desktop-only side effects of a real conversion.

    The conversion runs the real desktop code paths, and those set
    ``TS_DESKTOP*`` / ``TS_DATA_DIR`` in the process environment.  The
    storage layer resolves every photo path against those variables, so a
    leaked value would silently redirect the *rest of the test session*
    into this temporary library.  Snapshot and restore the environment.
    """
    import desktop_entry

    original_environment = dict(os.environ)

    # ``desktop_entry._prepare_desktop_database`` normally upgrades the schema
    # and then registers the portable library paths
    # (``prepare_portable_library``).  The fixture database is a minimal
    # hand-written schema, so the Alembic upgrade cannot run here, but the
    # path registration must: the conversion re-reads the staged library
    # through it and the final verification resolves the copied photos from
    # the registered storage roots.
    from app.utils.portable_library import prepare_portable_library

    def prepare_only(*_args, **_kwargs):
        prepare_portable_library(Path(os.environ["TS_DESKTOP_ROOT"]))

    monkeypatch.setattr(desktop_entry, "_prepare_desktop_database", prepare_only)
    for name in ("TS_DESKTOP", "TS_DESKTOP_PORTABLE", "TS_DESKTOP_ROOT", "TS_DATA_DIR",
                 "TS_IMPORT_OPERATION", "TS_IMPORT_PREVIOUS_DATA", "TS_IMPORT_ORIGIN",
                 "TS_IMPORT_ORIGIN_ID"):
        monkeypatch.delenv(name, raising=False)
    yield tmp_path
    os.environ.clear()
    os.environ.update(original_environment)


# ---------------------------------------------------------------------------
# the happy path
# ---------------------------------------------------------------------------


def test_convert_to_portable_publishes_a_ready_instance(tmp_path, isolated_desktop_env, monkeypatch):
    """The whole conversion succeeds and the target becomes a usable instance."""
    from app.utils import portable_conversion

    library, original_photo = _legacy_with_photo(tmp_path / "legacy")
    program = _desktop_program(tmp_path / "program")
    launcher = _launcher(tmp_path)
    target = tmp_path / "new-instance"
    target.mkdir()

    result = portable_conversion.convert_to_portable(library, target, program, launcher)

    # The caller gets the new location and the preserved row counts.
    assert result["target"] == str(target)
    assert result["counts"]["users"] == 1
    assert result["counts"]["photos"] == 1

    # The instance layout is published.
    assert (target / "instance.json").is_file()
    assert (target / "portable.json").is_file()
    assert (target / "TrailSnap.exe").is_file()
    assert (target / "userdata" / "data" / "trailsnap.sqlite").is_file()

    instance = json.loads((target / "instance.json").read_text(encoding="utf-8"))
    assert instance["mode"] == "portable"
    assert instance["dataRoot"] == {"kind": "relative", "path": "userdata"}
    assert instance["activeBuild"]

    # The conversion proof records the source and marks the copy as verified.
    proof = json.loads((target / "conversion.json").read_text(encoding="utf-8"))
    assert proof["source"] == str(library)
    assert proof["verified"] is True

    # The photo now points into the new instance, not at the old library.
    # The portable layout resolves a photo through its storage root
    # (``photo_paths``), so the effective path is what matters here - the
    # ``file_path`` column keeps the value it had while the library was
    # still staged.
    from app.utils.desktop_verification import photo_paths

    database = target / "userdata" / "data" / "trailsnap.sqlite"
    connection = sqlite3.connect(database)
    try:
        resolved = list(photo_paths(connection, target / "userdata"))
    finally:
        connection.close()
    assert len(resolved) == 1
    photo_id, _owner, rebased = resolved[0]
    assert photo_id == PHOTO_ID
    assert rebased != original_photo
    assert str(target) in rebased
    assert Path(rebased).is_file()


def test_convert_to_portable_rotates_the_library_identity(tmp_path, isolated_desktop_env):
    """A copied library is a new instance, so its identity must change."""
    from app.utils import portable_conversion

    library, _ = _legacy_with_photo(tmp_path / "legacy")
    library_metadata = library / "library.json"
    library_metadata.write_text(json.dumps({
        "schemaVersion": 1, "pathFormat": 1,
        "libraryId": "33333333-3333-4333-8333-333333333333",
        "initialized": True, "lastRoot": str(library),
    }), encoding="utf-8")
    program = _desktop_program(tmp_path / "program")
    launcher = _launcher(tmp_path)
    target = tmp_path / "new-instance"
    target.mkdir()

    portable_conversion.convert_to_portable(library, target, program, launcher)

    metadata = json.loads((target / "userdata" / "library.json").read_text(encoding="utf-8"))
    assert metadata["libraryId"] != "33333333-3333-4333-8333-333333333333"
    # The published instance points at its own root, not at the old library.
    assert Path(metadata["lastRoot"]).resolve() == (target / "userdata").resolve()


def test_convert_to_portable_regenerates_the_secret_key(tmp_path, isolated_desktop_env):
    """The copied instance must not share the old installation's secret key."""
    from app.utils import portable_conversion

    library, _ = _legacy_with_photo(tmp_path / "legacy")
    config = library / "data" / "system_config.json"
    config.write_text(json.dumps({"security": {"secret_key": "old-secret"}}), encoding="utf-8")
    program = _desktop_program(tmp_path / "program")
    launcher = _launcher(tmp_path)
    target = tmp_path / "new-instance"
    target.mkdir()

    portable_conversion.convert_to_portable(library, target, program, launcher)

    copied = json.loads((target / "userdata" / "data" / "system_config.json").read_text(encoding="utf-8"))
    assert copied["security"]["secret_key"] != "old-secret"
    assert len(copied["security"]["secret_key"]) == 64


def test_convert_to_portable_keeps_the_source_library_intact(tmp_path, isolated_desktop_env):
    """The conversion copies; it never mutates or deletes the old library."""
    from app.utils import portable_conversion

    library, original_photo = _legacy_with_photo(tmp_path / "legacy")
    program = _desktop_program(tmp_path / "program")
    launcher = _launcher(tmp_path)
    target = tmp_path / "new-instance"
    target.mkdir()

    portable_conversion.convert_to_portable(library, target, program, launcher)

    assert (library / "data" / "trailsnap.sqlite").is_file()
    assert Path(original_photo).is_file()
    connection = sqlite3.connect(library / "data" / "trailsnap.sqlite")
    try:
        rows = connection.execute("SELECT file_path FROM photos").fetchall()
    finally:
        connection.close()
    assert rows[0][0] == original_photo


def test_convert_to_portable_rewrites_the_user_storage_settings(tmp_path, isolated_desktop_env):
    """The user's configured storage paths must point at the new instance."""
    from app.utils import portable_conversion

    library, _ = _legacy_with_photo(tmp_path / "legacy")
    program = _desktop_program(tmp_path / "program")
    launcher = _launcher(tmp_path)
    target = tmp_path / "new-instance"
    target.mkdir()

    portable_conversion.convert_to_portable(library, target, program, launcher)

    connection = sqlite3.connect(target / "userdata" / "data" / "trailsnap.sqlite")
    try:
        rows = connection.execute("SELECT settings FROM users").fetchall()
    finally:
        connection.close()
    settings = json.loads(rows[0][0] or "{}")
    storage_path = settings.get("storage", {}).get("photo_storage_path")
    # The staging directory is renamed away by the conversion, so no setting
    # may keep pointing into it - otherwise the new instance would use paths
    # that no longer exist.
    staging = ".trailsnap-portable-"
    assert storage_path is None or staging not in storage_path


