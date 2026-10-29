"""2026-10-30 nightly gap tests for the ``copy_external`` branch of
``app/utils/portable_conversion.py``.

``utils/portable_conversion.py`` has been the largest backend coverage gap
for five consecutive nightly rounds.  Every other branch of
``convert_to_portable`` is already covered; the remaining ~40 uncovered
lines are the ``copy_external=True`` body: copying an external photo library
into the new instance, rebasing the photo rows, rewriting the user settings
and remapping the queued task payloads.

This file drives that branch with a realistic legacy installation:

* a legacy root with ``data/trailsnap.sqlite`` (users / photos / albums /
  tasks / storage_roots) and one photo inside the library;
* a second, **external** photo library outside the legacy root that is
  registered for the same user;
* a complete desktop program and launcher;
* an empty target directory.
"""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

import pytest


pytestmark = [pytest.mark.smoke]


OWNER_ID = "11111111-1111-4111-8111-111111111111"
INTERNAL_PHOTO_ID = "22222222-2222-4222-8222-222222222222"
EXTERNAL_PHOTO_ID = "33333333-3333-4333-8333-333333333333"


def _legacy_library(root: Path, *, users=(), photos=(), tasks=()) -> Path:
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
        # ``copy_external`` rewrites the payload of every task, so the fixture
        # needs the real column set (app/db/models/task.py).
        connection.execute("CREATE TABLE tasks (id TEXT PRIMARY KEY, owner_id TEXT, payload TEXT)")
        connection.execute(
            "CREATE TABLE storage_roots (id TEXT PRIMARY KEY, owner_id TEXT, name TEXT, kind TEXT, location TEXT)"
        )
        for owner, settings in users:
            connection.execute("INSERT INTO users (id, settings) VALUES (?, ?)", (owner, settings))
        for photo, owner, path in photos:
            connection.execute(
                "INSERT INTO photos (id, owner_id, file_path) VALUES (?, ?, ?)", (photo, owner, path)
            )
        for task_id, owner, payload in tasks:
            connection.execute(
                "INSERT INTO tasks (id, owner_id, payload) VALUES (?, ?, ?)", (task_id, owner, payload)
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


@pytest.fixture()
def isolated_desktop_env(tmp_path, monkeypatch):
    """Neutralise the desktop-only side effects of a real conversion."""
    import desktop_entry

    original_environment = dict(os.environ)
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


def _library_with_external(tmp_path: Path, *, custom_storage: bool = False):
    """A legacy library plus an external photo library of the same owner."""
    external = (tmp_path / "external").resolve()
    external.mkdir(parents=True, exist_ok=True)
    external_photo = external / "outside.jpg"
    external_photo.write_bytes(b"external-photo-bytes")

    library_root = tmp_path / "legacy"
    storage = {"external_directories": [str(external)]}
    if custom_storage:
        # ``photo_storage_path`` points at the parent of ``users/<owner>`` so the
        # external root is the user's own managed base.
        storage["photo_storage_path"] = str(tmp_path / "managed")
        (tmp_path / "managed" / "users" / OWNER_ID).mkdir(parents=True, exist_ok=True)
        (tmp_path / "managed" / "users" / OWNER_ID / "inside.jpg").write_bytes(b"managed-photo-bytes")
        managed_photo = tmp_path / "managed" / "users" / OWNER_ID / "inside.jpg"
    else:
        storage["photo_storage_path"] = str(library_root / "data" / "uploads")
        managed_photo = library_root / "data" / "uploads" / "inside.jpg"
        managed_photo.parent.mkdir(parents=True, exist_ok=True)
        managed_photo.write_bytes(b"managed-photo-bytes")

    library = _legacy_library(
        library_root,
        users=[(OWNER_ID, json.dumps({"storage": storage}))],
        photos=[
            (INTERNAL_PHOTO_ID, OWNER_ID, str(managed_photo)),
            (EXTERNAL_PHOTO_ID, OWNER_ID, str(external_photo)),
        ],
        tasks=[("task-1", OWNER_ID, json.dumps({"target_root_path": str(external)}))],
    )
    return library, external, managed_photo, external_photo


def test_convert_to_portable_copies_the_external_library(tmp_path, isolated_desktop_env):
    """The external library is copied into the new instance and referenced."""
    from app.utils import portable_conversion

    library, external, _managed, external_photo = _library_with_external(tmp_path)
    program = _desktop_program(tmp_path / "program")
    launcher = _launcher(tmp_path)
    target = tmp_path / "new-instance"
    target.mkdir()

    preview = portable_conversion.preview_conversion(library)
    assert [item["path"] for item in preview["externalRoots"]] == [str(external)]
    assert preview["unregisteredPhotos"] == 0

    result = portable_conversion.convert_to_portable(
        library, target, program, launcher, copy_external=True
    )

    assert result["counts"]["photos"] == 2
    proof = json.loads((target / "conversion.json").read_text(encoding="utf-8"))
    assert proof["externalCopied"] is True

    # The external photo now lives inside the new instance.  The portable
    # layout resolves a photo through its storage root, so the effective path
    # is what matters - the legacy ``file_path`` column keeps the value it had
    # while the library was still staged.
    from app.utils.desktop_verification import photo_paths

    database = target / "userdata" / "data" / "trailsnap.sqlite"
    connection = sqlite3.connect(database)
    try:
        resolved = {photo_id: path for photo_id, _owner, path in
                    photo_paths(connection, target / "userdata")}
    finally:
        connection.close()
    copied_path = Path(resolved[EXTERNAL_PHOTO_ID])
    assert copied_path.is_file()
    assert copied_path.read_bytes() == external_photo.read_bytes()
    assert str(target) in str(copied_path)
    # The original external library is untouched.
    assert external_photo.is_file()


def test_convert_to_portable_rewrites_the_external_directories_setting(tmp_path, isolated_desktop_env):
    """The user's external directory list points at the copied library."""
    from app.utils import portable_conversion

    library, _external, _managed, _external_photo = _library_with_external(tmp_path)
    program = _desktop_program(tmp_path / "program")
    launcher = _launcher(tmp_path)
    target = tmp_path / "new-instance"
    target.mkdir()

    portable_conversion.convert_to_portable(library, target, program, launcher, copy_external=True)

    database = target / "userdata" / "data" / "trailsnap.sqlite"
    connection = sqlite3.connect(database)
    try:
        raw = connection.execute("SELECT settings FROM users WHERE id=?", (OWNER_ID,)).fetchone()[0]
    finally:
        connection.close()
    settings = json.loads(raw or "{}")
    directories = settings.get("storage", {}).get("external_directories", [])
    assert directories
    # The copied library is referenced relative to the new instance.
    assert all(item.startswith("ts-instance:") for item in directories)


def test_convert_to_portable_keeps_a_custom_user_storage_base(tmp_path, isolated_desktop_env):
    """A user whose own base is the external root keeps that layout."""
    from app.utils import portable_conversion

    library, _external, _managed, _external_photo = _library_with_external(tmp_path, custom_storage=True)
    program = _desktop_program(tmp_path / "program")
    launcher = _launcher(tmp_path)
    target = tmp_path / "new-instance"
    target.mkdir()

    portable_conversion.convert_to_portable(library, target, program, launcher, copy_external=True)

    from app.utils.desktop_verification import photo_paths

    database = target / "userdata" / "data" / "trailsnap.sqlite"
    connection = sqlite3.connect(database)
    try:
        resolved = {photo_id: path for photo_id, _owner, path in
                    photo_paths(connection, target / "userdata")}
        raw = connection.execute("SELECT settings FROM users WHERE id=?", (OWNER_ID,)).fetchone()[0]
    finally:
        connection.close()
    settings = json.loads(raw or "{}")
    storage_path = settings.get("storage", {}).get("photo_storage_path")
    assert storage_path
    # The user base moved into the new instance together with the photos and
    # is stored relative to that instance.
    assert storage_path.startswith("ts-instance:")
    copied = Path(resolved[EXTERNAL_PHOTO_ID])
    assert copied.is_file()
    assert str(target) in str(copied)
