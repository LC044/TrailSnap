"""Nightly coverage for the preview half of ``app.utils.portable_conversion`` (2026-10-24).

The 2026-10-24 backend coverage gap ranked ``utils/portable_conversion.py``
first (41.1%, 169 of 287 statements uncovered). The 2026-10-22 nightly file
covered the *validation* helpers only; the remaining half -- ``preview_conversion``
and ``validate_external_target`` -- was still unexecuted.

``preview_conversion`` is what the desktop UI shows before an import: it opens
the legacy library read-only, reports row counts, discovers the external photo
roots that must not be deleted, and counts photos that live outside every
registered root. Those answers drive real destructive decisions (the user is
asked to confirm an import, then files are deleted), so the discovery rules are
worth pinning down.

The tests build a genuine SQLite legacy library on disk, because the function
reads it with a read-only URI and the photo-path rules depend on the real
schema.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from app.utils.portable_conversion import (
    preview_conversion,
    validate_external_target,
)


pytestmark = [pytest.mark.smoke]


def _make_legacy_library(root: Path) -> Path:
    """Create a legacy library folder with a readable SQLite database."""
    (root / "data").mkdir(parents=True, exist_ok=True)
    database = root / "data" / "trailsnap.sqlite"
    with sqlite3.connect(database) as db:
        db.execute("CREATE TABLE users (id TEXT PRIMARY KEY, settings TEXT)")
        db.execute("CREATE TABLE photos (id INTEGER PRIMARY KEY, owner_id TEXT, file_path TEXT)")
        db.execute("CREATE TABLE albums (id INTEGER PRIMARY KEY)")
        db.execute("CREATE TABLE tasks (id INTEGER PRIMARY KEY)")
    return root


def _add_user(root: Path, owner: str, settings: dict | None = None) -> None:
    with sqlite3.connect(root / "data" / "trailsnap.sqlite") as db:
        db.execute(
            "INSERT INTO users (id, settings) VALUES (?, ?)",
            (owner, json.dumps(settings or {}, ensure_ascii=False)),
        )


def _add_photo(root: Path, photo_id: int, owner: str, file_path: str) -> None:
    with sqlite3.connect(root / "data" / "trailsnap.sqlite") as db:
        db.execute(
            "INSERT INTO photos (id, owner_id, file_path) VALUES (?, ?, ?)",
            (photo_id, owner, file_path),
        )


def _add_album(root: Path) -> None:
    with sqlite3.connect(root / "data" / "trailsnap.sqlite") as db:
        db.execute("INSERT INTO albums (id) VALUES (1)")


def _add_task(root: Path) -> None:
    with sqlite3.connect(root / "data" / "trailsnap.sqlite") as db:
        db.execute("INSERT INTO tasks (id) VALUES (1)")


# ---------------------------------------------------------------------------
# preview_conversion -- counts and size
# ---------------------------------------------------------------------------


def test_preview_reports_row_counts_for_every_managed_table(tmp_path):
    """The preview tells the user how much will be migrated."""
    source = _make_legacy_library(tmp_path / "legacy")
    _add_user(source, "owner-1")
    _add_photo(source, 1, "owner-1", str(source / "data" / "photos" / "a.jpg"))
    _add_album(source)
    _add_task(source)

    preview = preview_conversion(source)

    assert preview["counts"] == {"users": 1, "photos": 1, "albums": 1, "tasks": 1}


def test_preview_reports_source_path_and_bytes(tmp_path):
    """The preview reports the resolved source and the total size to copy."""
    source = _make_legacy_library(tmp_path / "legacy")
    (source / "photos").mkdir()
    (source / "photos" / "a.jpg").write_bytes(b"0123456789")

    preview = preview_conversion(source)

    assert preview["source"] == str(source.resolve())
    assert preview["bytes"] >= 10


def test_preview_skips_symlinks_when_summing_size(tmp_path):
    """A symlink is not copied, so it must not inflate the reported size."""
    source = _make_legacy_library(tmp_path / "legacy")
    (source / "photos").mkdir()
    (source / "photos" / "a.jpg").write_bytes(b"0123456789")
    try:
        (source / "photos" / "link.jpg").symlink_to(source / "photos" / "a.jpg")
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not creatable in this environment")

    without_symlink = preview_conversion(source)["bytes"]
    (source / "photos" / "link.jpg").unlink()

    assert preview_conversion(source)["bytes"] == without_symlink


# ---------------------------------------------------------------------------
# preview_conversion -- external root discovery
# ---------------------------------------------------------------------------


def test_preview_lists_external_directories_from_user_settings(tmp_path):
    """External photo folders declared in settings are reported as external roots."""
    source = _make_legacy_library(tmp_path / "legacy")
    outside = tmp_path / "outside"
    outside.mkdir()
    _add_user(source, "owner-1", {"storage": {"external_directories": [str(outside)]}})

    preview = preview_conversion(source)

    assert [(item["ownerId"], item["path"]) for item in preview["externalRoots"]] == [
        ("owner-1", str(outside.resolve()))
    ]
    assert preview["externalRoots"][0]["available"] is True


def test_preview_marks_missing_external_root_as_unavailable(tmp_path):
    """An unplugged external disk must be reported as unavailable."""
    source = _make_legacy_library(tmp_path / "legacy")
    missing = tmp_path / "missing"
    _add_user(source, "owner-1", {"storage": {"external_directories": [str(missing)]}})

    preview = preview_conversion(source)

    assert preview["externalRoots"][0]["available"] is False


def test_preview_ignores_external_root_inside_the_source(tmp_path):
    """A root that lives inside the legacy folder is copied, not external."""
    source = _make_legacy_library(tmp_path / "legacy")
    inside = source / "photos"
    inside.mkdir()
    _add_user(source, "owner-1", {"storage": {"external_directories": [str(inside)]}})

    preview = preview_conversion(source)

    assert preview["externalRoots"] == []


def test_preview_reports_external_root_registered_in_storage_roots(tmp_path):
    """Roots registered in the storage_roots table are discovered too."""
    source = _make_legacy_library(tmp_path / "legacy")
    outside = tmp_path / "outside"
    outside.mkdir()
    _add_user(source, "owner-1")
    with sqlite3.connect(source / "data" / "trailsnap.sqlite") as db:
        db.execute(
            "CREATE TABLE storage_roots (id INTEGER PRIMARY KEY, owner_id TEXT, kind TEXT, location TEXT)"
        )
        db.execute(
            "INSERT INTO storage_roots (owner_id, kind, location) VALUES (?, 'external', ?)",
            ("owner-1", str(outside)),
        )

    preview = preview_conversion(source)

    assert [item["path"] for item in preview["externalRoots"]] == [str(outside.resolve())]


def test_preview_ignores_managed_storage_roots(tmp_path):
    """Managed roots live inside the library and are not external."""
    source = _make_legacy_library(tmp_path / "legacy")
    _add_user(source, "owner-1")
    with sqlite3.connect(source / "data" / "trailsnap.sqlite") as db:
        db.execute(
            "CREATE TABLE storage_roots (id INTEGER PRIMARY KEY, owner_id TEXT, kind TEXT, location TEXT)"
        )
        db.execute(
            "INSERT INTO storage_roots (owner_id, kind, location) VALUES (?, 'managed', ?)",
            ("owner-1", "photos"),
        )

    preview = preview_conversion(source)

    assert preview["externalRoots"] == []


def test_preview_derives_external_root_from_absolute_photo_storage_path(tmp_path):
    """An absolute photo root outside the library is reported as external."""
    source = _make_legacy_library(tmp_path / "legacy")
    outside = tmp_path / "outside"
    outside.mkdir()
    _add_user(source, "owner-1", {"storage": {"photo_storage_path": str(outside)}})

    preview = preview_conversion(source)

    assert [item["path"] for item in preview["externalRoots"]] == [
        str((outside / "users" / "owner-1").resolve())
    ]


def test_preview_deduplicates_repeated_external_roots(tmp_path):
    """The same folder declared twice is reported once."""
    source = _make_legacy_library(tmp_path / "legacy")
    outside = tmp_path / "outside"
    outside.mkdir()
    _add_user(
        source,
        "owner-1",
        {"storage": {"external_directories": [str(outside), str(outside)]}},
    )

    preview = preview_conversion(source)

    assert len(preview["externalRoots"]) == 1


# ---------------------------------------------------------------------------
# preview_conversion -- unregistered photos
# ---------------------------------------------------------------------------


def test_preview_counts_photos_outside_every_known_root(tmp_path):
    """A photo that belongs to no known root would be lost during conversion."""
    source = _make_legacy_library(tmp_path / "legacy")
    stray = tmp_path / "stray"
    stray.mkdir()
    _add_user(source, "owner-1")
    _add_photo(source, 1, "owner-1", str(stray / "a.jpg"))

    preview = preview_conversion(source)

    assert preview["unregisteredPhotos"] == 1


def test_preview_does_not_count_photos_inside_the_library(tmp_path):
    """Photos stored inside the legacy folder are migrated normally."""
    source = _make_legacy_library(tmp_path / "legacy")
    _add_user(source, "owner-1")
    _add_photo(source, 1, "owner-1", str(source / "photos" / "a.jpg"))

    preview = preview_conversion(source)

    assert preview["unregisteredPhotos"] == 0


def test_preview_does_not_count_photos_inside_a_registered_external_root(tmp_path):
    """A photo under a registered external root is accounted for."""
    source = _make_legacy_library(tmp_path / "legacy")
    outside = tmp_path / "outside"
    outside.mkdir()
    _add_user(source, "owner-1", {"storage": {"external_directories": [str(outside)]}})
    _add_photo(source, 1, "owner-1", str(outside / "a.jpg"))

    preview = preview_conversion(source)

    assert preview["unregisteredPhotos"] == 0


# ---------------------------------------------------------------------------
# validate_external_target
# ---------------------------------------------------------------------------


def test_validate_target_rejects_the_external_root_itself(tmp_path):
    """The new instance must not be written into an external photo folder."""
    outside = tmp_path / "outside"
    outside.mkdir()
    preview = {"externalRoots": [{"ownerId": "o", "path": str(outside.resolve()), "available": True}]}

    with pytest.raises(ValueError, match="不能与外部照片文件夹相同"):
        validate_external_target(preview, outside)


def test_validate_target_rejects_a_folder_inside_the_external_root(tmp_path):
    """Writing inside an external photo folder would mix the two libraries."""
    outside = tmp_path / "outside"
    inside = outside / "new"
    inside.mkdir(parents=True)
    preview = {"externalRoots": [{"ownerId": "o", "path": str(outside.resolve()), "available": True}]}

    with pytest.raises(ValueError, match="不能与外部照片文件夹相同"):
        validate_external_target(preview, inside)


def test_validate_target_rejects_a_folder_containing_the_external_root(tmp_path):
    """Writing over the parent of an external root would delete its photos."""
    outside = tmp_path / "outside"
    outside.mkdir()
    preview = {"externalRoots": [{"ownerId": "o", "path": str(outside.resolve()), "available": True}]}

    with pytest.raises(ValueError, match="不能与外部照片文件夹相同"):
        validate_external_target(preview, tmp_path)


def test_validate_target_accepts_an_unrelated_sibling_folder(tmp_path):
    """A sibling folder of the external root is the recommended choice."""
    outside = tmp_path / "outside"
    outside.mkdir()
    target = tmp_path / "portable"
    target.mkdir()
    preview = {"externalRoots": [{"ownerId": "o", "path": str(outside.resolve()), "available": True}]}

    assert validate_external_target(preview, target) is None


def test_validate_target_accepts_a_target_without_external_roots(tmp_path):
    """Without external roots any empty folder is acceptable."""
    target = tmp_path / "portable"
    target.mkdir()

    assert validate_external_target({"externalRoots": []}, target) is None
