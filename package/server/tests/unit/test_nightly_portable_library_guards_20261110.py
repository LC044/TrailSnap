"""Nightly gap coverage for app/utils/portable_library.py guard branches.

Covers the defensive paths of snapshot/restore/prepare that the nightly
coverage scan reported as uncovered:

* snapshot destination that is the library root or nested inside it
* a snapshot manifest that belongs to a different portable library
* a restore manifest whose relative path escapes the library root
* a restore manifest whose recorded checksum no longer matches
* a library.json written with an unsupported schema/path format
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest

from app.utils.portable_library import (
    prepare_portable_library,
    restore_library,
    snapshot_library,
)

pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


def _make_root(tmp_path: Path, library_id: str | None = None) -> Path:
    root = tmp_path / "library"
    (root / "data").mkdir(parents=True)
    metadata = {
        "schemaVersion": 1,
        "libraryId": library_id or str(uuid.uuid4()),
        "pathFormat": 1,
        "minimumReader": "portable-v1",
        "lastRoot": str(root),
    }
    (root / "library.json").write_text(json.dumps(metadata), encoding="utf-8")
    (root / "data" / "trailsnap.sqlite").write_bytes(b"")
    return root


def test_snapshot_rejects_destination_equal_to_library_root(tmp_path):
    root = _make_root(tmp_path)

    with pytest.raises(ValueError, match="Invalid snapshot destination"):
        snapshot_library(root, root)


def test_snapshot_rejects_destination_containing_the_library(tmp_path):
    root = _make_root(tmp_path)

    # The snapshot destination must not contain the library it copies from,
    # otherwise the snapshot would recursively include itself.
    with pytest.raises(ValueError, match="Invalid snapshot destination"):
        snapshot_library(root, tmp_path)


def test_snapshot_rejects_manifest_of_another_library(tmp_path):
    root = _make_root(tmp_path)
    destination = tmp_path / "snapshot"
    destination.mkdir()
    (destination / "snapshot.json").write_text(
        json.dumps({"schemaVersion": 1, "source": str(tmp_path / "other"), "libraryId": str(uuid.uuid4()), "files": []}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Snapshot belongs to another library"):
        snapshot_library(root, destination)


def test_restore_rejects_manifest_path_escaping_the_library_root(tmp_path):
    root = _make_root(tmp_path)
    snapshot = tmp_path / "snapshot"
    (snapshot / "data").mkdir(parents=True)
    (snapshot / "snapshot.json").write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "source": str(root),
                "libraryId": json.loads((root / "library.json").read_text(encoding="utf-8"))["libraryId"],
                "files": [{"path": "../escaped.txt", "existed": False, "sha256": None}],
                "media": [],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Snapshot path escapes its root"):
        restore_library(root, snapshot)


def test_restore_rejects_checksum_mismatch(tmp_path):
    root = _make_root(tmp_path)
    snapshot = tmp_path / "snapshot"
    (snapshot / "data").mkdir(parents=True)
    (snapshot / "data" / "notes.txt").write_text("current", encoding="utf-8")
    (snapshot / "snapshot.json").write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "source": str(root),
                "libraryId": json.loads((root / "library.json").read_text(encoding="utf-8"))["libraryId"],
                "files": [{"path": "data/notes.txt", "existed": True, "sha256": "0" * 64}],
                "media": [],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Snapshot checksum mismatch"):
        restore_library(root, snapshot)


def test_prepare_rejects_unsupported_library_format(tmp_path):
    root = tmp_path / "library"
    root.mkdir()
    (root / "library.json").write_text(
        json.dumps({"schemaVersion": 2, "libraryId": str(uuid.uuid4()), "pathFormat": 2}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Unsupported portable library format"):
        prepare_portable_library(root)

