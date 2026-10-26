"""Nightly coverage for ``app.utils.automatic_upgrade`` guard rails.

The 2026-10-21 backend coverage gap ranked ``utils/automatic_upgrade.py``
at 47.1% (136 of 257 statements uncovered). The uncovered region is the
*decision* half of the module: ``_inventory`` decides which legacy files may
later be deleted, and ``_check_journal`` decides whether a persisted
migration job may be resumed at all.

Both helpers are deliberately conservative -- they raise ``ValueError`` with
operator-facing Chinese messages instead of guessing. Those branches were
never executed by any test, so a regression in them would silently allow an
automatic upgrade to delete a changed file or to target the new live
library.
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from pathlib import Path

import pytest

from app.utils.automatic_upgrade import (
    _check_journal,
    _inventory,
    _read,
    finish,
    prepare,
)


pytestmark = [pytest.mark.smoke]

MANAGED_ROOTS = {"data", "logs", "models", "runtime", "extensions", "ai-extensions"}


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _valid_job(root: Path, source: Path) -> dict:
    """Build a journal payload that ``_check_journal`` accepts."""
    return {
        "schemaVersion": 1,
        "id": str(uuid.uuid4()),
        "source": str(source.resolve()),
        "phase": "copying",
        "instance": {"instanceId": str(uuid.uuid4()), "dataRoot": {"kind": "relative", "path": "userdata"}},
    }


# ---------------------------------------------------------------------------
# _read
# ---------------------------------------------------------------------------


def test_read_parses_json_document(tmp_path):
    """The journal reader is a thin JSON wrapper."""
    path = tmp_path / "job.json"
    _write_json(path, {"phase": "copying"})

    assert _read(path) == {"phase": "copying"}


def test_read_raises_on_missing_file(tmp_path):
    """A missing journal surfaces as an OSError."""
    with pytest.raises(OSError):
        _read(tmp_path / "absent.json")


# ---------------------------------------------------------------------------
# _inventory
# ---------------------------------------------------------------------------


def test_inventory_lists_files_sorted_by_relative_path(tmp_path):
    """The inventory is sorted so the deletion set is deterministic."""
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "b.txt").write_text("b", encoding="utf-8")
    (tmp_path / "data" / "a.txt").write_text("a", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("n", encoding="utf-8")

    records = _inventory(tmp_path)

    assert [row["path"] for row in records] == [
        "data/a.txt",
        "data/b.txt",
        "notes.txt",
    ]


def test_inventory_marks_managed_roots_for_cleanup(tmp_path):
    """Only files inside managed roots may be deleted later."""
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "keep.txt").write_text("x", encoding="utf-8")
    (tmp_path / "photos").mkdir()
    (tmp_path / "photos" / "pic.jpg").write_bytes(b"jpg")
    (tmp_path / "ai-config.json").write_text("{}", encoding="utf-8")

    records = {row["path"]: row for row in _inventory(tmp_path)}

    assert records["data/keep.txt"]["cleanup"] is True
    assert records["ai-config.json"]["cleanup"] is True
    # A folder that is not managed belongs to another application.
    assert records["photos/pic.jpg"]["cleanup"] is False


def test_inventory_records_content_hash(tmp_path):
    """Every record carries the SHA-256 of the file at inventory time."""
    (tmp_path / "notes.txt").write_text("hello", encoding="utf-8")

    records = _inventory(tmp_path)

    assert len(records) == 1
    assert records[0]["sha256"] == hashlib.sha256(b"hello").hexdigest()


def test_inventory_hash_matches_when_progress_callback_is_used(tmp_path):
    """The streaming hash path must agree with the plain ``file_hash`` path."""
    (tmp_path / "notes.txt").write_text("hello", encoding="utf-8")
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "x.bin").write_bytes(b"\x00\x01\x02")

    plain = {row["path"]: row["sha256"] for row in _inventory(tmp_path)}
    seen = []
    streamed = {
        row["path"]: row["sha256"]
        for row in _inventory(tmp_path, progress=lambda done, total: seen.append((done, total)))
    }

    assert plain == streamed
    assert seen, "the progress callback should be invoked while hashing"


def test_inventory_skips_excluded_entries(tmp_path):
    """The live server folder is never part of the copy/delete set."""
    (tmp_path / "server").mkdir()
    (tmp_path / "server" / "app.py").write_text("x", encoding="utf-8")
    (tmp_path / "trailsnap-desktop.exe").write_bytes(b"MZ")
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "a.txt").write_text("a", encoding="utf-8")

    records = _inventory(tmp_path)

    paths = {row["path"] for row in records}
    assert paths == {"data/a.txt"}


def test_inventory_skips_webview_backup_folders(tmp_path):
    """Leftover WebView folders belong to the desktop shell, not the library."""
    (tmp_path / "webview").mkdir()
    (tmp_path / "webview" / "cache.bin").write_bytes(b"x")
    (tmp_path / "webview-backup-1").mkdir()
    (tmp_path / "webview-backup-1" / "cache.bin").write_bytes(b"x")
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "a.txt").write_text("a", encoding="utf-8")

    records = _inventory(tmp_path)

    assert {row["path"] for row in records} == {"data/a.txt"}


def test_inventory_rejects_symlinks(tmp_path):
    """A symlink inside the legacy tree stops the automatic migration."""
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "a.txt").write_text("a", encoding="utf-8")
    link = tmp_path / "data" / "link.txt"
    try:
        os.symlink(tmp_path / "data" / "a.txt", link)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not available on this platform")

    with pytest.raises(ValueError) as error:
        _inventory(tmp_path)

    assert "含链接" in str(error.value)


# ---------------------------------------------------------------------------
# _check_journal -- journal validity
# ---------------------------------------------------------------------------


def test_check_journal_accepts_a_valid_job(tmp_path):
    """A well formed job yields the source and the staging folder."""
    root = tmp_path / "new"
    root.mkdir()
    source = tmp_path / "legacy"
    source.mkdir()
    job = _valid_job(root, source)

    resolved, stage = _check_journal(root, job)

    assert resolved == source.resolve()
    assert stage == root.parent / (".trailsnap-auto-" + job["id"])


def test_check_journal_rejects_unknown_schema_version(tmp_path):
    """A journal written by a newer launcher is not resumed."""
    root = tmp_path / "new"
    root.mkdir()
    source = tmp_path / "legacy"
    source.mkdir()
    job = _valid_job(root, source)
    job["schemaVersion"] = 2

    with pytest.raises(ValueError) as error:
        _check_journal(root, job)

    assert "自动迁移记录无效" in str(error.value)


def test_check_journal_rejects_malformed_job_id(tmp_path):
    """A job id that is not a UUID is refused."""
    root = tmp_path / "new"
    root.mkdir()
    source = tmp_path / "legacy"
    source.mkdir()
    job = _valid_job(root, source)
    job["id"] = "not-a-uuid"

    with pytest.raises(ValueError):
        _check_journal(root, job)


def test_check_journal_rejects_uppercase_job_id(tmp_path):
    """The stored id must round-trip through ``uuid.UUID`` unchanged."""
    root = tmp_path / "new"
    root.mkdir()
    source = tmp_path / "legacy"
    source.mkdir()
    job = _valid_job(root, source)
    job["id"] = job["id"].upper()

    with pytest.raises(ValueError) as error:
        _check_journal(root, job)

    assert "自动迁移记录无效" in str(error.value)


def test_check_journal_rejects_missing_source(tmp_path):
    """A job whose source disappeared cannot be resumed."""
    root = tmp_path / "new"
    root.mkdir()
    job = _valid_job(root, tmp_path / "legacy")

    with pytest.raises(OSError):
        _check_journal(root, job)


def test_check_journal_rejects_changed_source_spelling(tmp_path):
    """The source path must still point at the same folder."""
    root = tmp_path / "new"
    root.mkdir()
    source = tmp_path / "legacy"
    source.mkdir()
    job = _valid_job(root, source)
    job["source"] = job["source"] + os.sep

    with pytest.raises(ValueError) as error:
        _check_journal(root, job)

    assert "已改变" in str(error.value)


def test_check_journal_rejects_disk_root_source(tmp_path):
    """Migrating the whole disk root is never allowed."""
    root = tmp_path / "new"
    root.mkdir()
    job = _valid_job(root, Path(tmp_path.anchor))
    job["source"] = tmp_path.anchor

    with pytest.raises(ValueError) as error:
        _check_journal(root, job)

    assert "磁盘根目录" in str(error.value)


def test_check_journal_rejects_source_inside_new_library(tmp_path):
    """The old data may not live inside the new ``userdata`` folder."""
    root = tmp_path / "new"
    userdata = root / "userdata"
    userdata.mkdir(parents=True)
    source = userdata / "legacy"
    source.mkdir()
    job = _valid_job(root, source)

    with pytest.raises(ValueError) as error:
        _check_journal(root, job)

    assert "旧数据位置不能指向新图库" in str(error.value)


# ---------------------------------------------------------------------------
# prepare / finish -- early guards
# ---------------------------------------------------------------------------


def test_prepare_returns_none_phase_for_existing_instance(tmp_path):
    """An already provisioned instance has nothing to upgrade."""
    root = tmp_path / "new"
    root.mkdir()
    _write_json(root / "instance.json", {"schemaVersion": 1, "instanceId": "x"})

    assert prepare(root) == {"phase": "none"}


def test_prepare_rejects_changed_instance_identity(tmp_path):
    """A published job must still describe the instance it created."""
    root = tmp_path / "new"
    root.mkdir()
    source = tmp_path / "legacy"
    source.mkdir()
    job = _valid_job(root, source)
    job["phase"] = "published"
    _write_json(root / "maintenance" / "automatic-upgrade.json", job)
    _write_json(
        root / "instance.json",
        {"instanceId": "a-different-id", "dataRoot": {"kind": "relative", "path": "userdata"}},
    )

    with pytest.raises(ValueError) as error:
        prepare(root)

    assert "图库身份或位置已改变" in str(error.value)


def test_finish_refuses_cleanup_before_validation(tmp_path):
    """Cleanup is blocked until the new library passed the launch check."""
    root = tmp_path / "new"
    root.mkdir()
    source = tmp_path / "legacy"
    source.mkdir()
    job = _valid_job(root, source)
    job["phase"] = "copying"
    _write_json(root / "maintenance" / "automatic-upgrade.json", job)
    _write_json(
        root / "instance.json",
        {
            "instanceId": job["instance"]["instanceId"],
            "dataRoot": {"kind": "relative", "path": "userdata"},
        },
    )

    with pytest.raises(ValueError) as error:
        finish(root, "cleanup")

    assert "禁止清理旧数据" in str(error.value)


def test_finish_marks_validated_after_launch_check(tmp_path):
    """A successful launch moves the job from published to validated."""
    root = tmp_path / "new"
    root.mkdir()
    source = tmp_path / "legacy"
    source.mkdir()
    job = _valid_job(root, source)
    job["phase"] = "published"
    _write_json(root / "maintenance" / "automatic-upgrade.json", job)
    _write_json(
        root / "instance.json",
        {
            "instanceId": job["instance"]["instanceId"],
            "dataRoot": {"kind": "relative", "path": "userdata"},
        },
    )

    result = finish(root, "validated")

    assert result["phase"] == "validated"
    stored = json.loads((root / "maintenance" / "automatic-upgrade.json").read_text(encoding="utf-8"))
    assert stored["phase"] == "validated"
