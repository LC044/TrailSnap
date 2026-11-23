"""Nightly gap coverage: desktop data migration helpers.

`remove_staging_directory` must delete read-only files it owns (the Windows
copy-on-write leftovers of the migration), and `migrate_data_directory` must
copy the old library into the new one, verify the copy byte by byte and
publish it atomically.
"""

import json
import os
import stat
from pathlib import Path

import pytest

from app.utils import desktop_data_migration as migration


pytestmark = pytest.mark.smoke


def test_remove_staging_directory_deletes_read_only_files(tmp_path):
    staging = tmp_path / "staging"
    staging.mkdir()
    read_only = staging / "locked.bin"
    read_only.write_bytes(b"payload")
    os.chmod(read_only, stat.S_IREAD)

    migration.remove_staging_directory(staging)

    assert not staging.exists()


def test_remove_staging_directory_refuses_links(tmp_path):
    staging = tmp_path / "staging"
    staging.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("keep me", encoding="utf-8")
    link = staging / "link.txt"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not available on this platform")

    with pytest.raises(ValueError):
        migration.remove_staging_directory(staging)

    assert outside.exists()


def test_migrate_data_directory_rejects_identical_directories(tmp_path):
    source = tmp_path / "data"
    source.mkdir()

    with pytest.raises(ValueError):
        migration.migrate_data_directory(source, source)


def test_migrate_data_directory_rejects_nested_directories(tmp_path):
    source = tmp_path / "data"
    source.mkdir()
    nested = source / "inner"
    nested.mkdir()

    with pytest.raises(ValueError):
        migration.migrate_data_directory(source, nested)


def test_migrate_data_directory_copies_and_publishes(tmp_path):
    source = tmp_path / "old"
    (source / "photos").mkdir(parents=True)
    (source / "photos" / "a.jpg").write_bytes(b"image-bytes")
    (source / "notes.txt").write_text("hello", encoding="utf-8")
    target = tmp_path / "new"

    checkpoints = []
    byte_progress = []
    migration.migrate_data_directory(
        source,
        target,
        checkpoint=lambda: checkpoints.append(1),
        byte_progress=lambda done, total: byte_progress.append((done, total)),
    )

    assert (target / "photos" / "a.jpg").read_bytes() == b"image-bytes"
    assert (target / "notes.txt").read_text(encoding="utf-8") == "hello"
    assert checkpoints, "the copy loop must report checkpoints"
    assert byte_progress, "the copy loop must report byte progress"

    marker = json.loads((target / migration.MARKER).read_text(encoding="utf-8"))
    assert marker["source"] == str(source.resolve())
    assert marker["target"] == str(target.resolve())


def test_migrate_data_directory_rejects_a_non_empty_target(tmp_path):
    source = tmp_path / "old"
    source.mkdir()
    (source / "a.txt").write_text("x", encoding="utf-8")
    target = tmp_path / "new"
    target.mkdir()
    (target / "existing.txt").write_text("y", encoding="utf-8")

    with pytest.raises(ValueError):
        migration.migrate_data_directory(source, target)

    assert (target / "existing.txt").exists()


def test_migrate_data_directory_is_idempotent_for_a_completed_run(tmp_path):
    source = tmp_path / "old"
    source.mkdir()
    (source / "a.txt").write_text("x", encoding="utf-8")
    target = tmp_path / "new"

    migration.migrate_data_directory(source, target)
    # A second run must recognise the marker and return without touching data.
    migration.migrate_data_directory(source, target)

    assert (target / "a.txt").read_text(encoding="utf-8") == "x"
