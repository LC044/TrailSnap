"""Nightly watch 2026-11-25 (part 2): cover the automatic-upgrade journal guards.

``app/utils/automatic_upgrade.py`` decides whether a legacy data root may be
deleted after the first verified launch. The journal validation and the
"cleanup before validation" guard were not covered by any test.
"""
import json
import uuid
from pathlib import Path

import pytest

from app.utils.automatic_upgrade import _check_journal, finish, prepare


def _write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _library(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "library"
    source = tmp_path / "legacy"
    root.mkdir()
    source.mkdir()
    return root, source


def _job(source: Path, phase: str = "published") -> dict:
    return {
        "id": str(uuid.uuid4()),
        "schemaVersion": 1,
        "phase": phase,
        "source": str(source),
        "instance": {"instanceId": "instance-1"},
        "media": [],
        "files": [],
    }


def test_check_journal_accepts_a_consistent_job(tmp_path):
    root, source = _library(tmp_path)
    job = _job(source)

    resolved, stage = _check_journal(root, job)

    assert resolved == source.resolve()
    assert stage.name.startswith(".trailsnap-auto-")


def test_check_journal_rejects_an_unknown_schema_version(tmp_path):
    root, source = _library(tmp_path)
    job = _job(source)
    job["schemaVersion"] = 2

    with pytest.raises(ValueError, match="记录无效"):
        _check_journal(root, job)


def test_check_journal_rejects_a_mismatched_job_id(tmp_path):
    root, source = _library(tmp_path)
    job = _job(source)
    # A non-canonical (upper-case) UUID does not round-trip, so the journal is rejected.
    job["id"] = str(uuid.uuid4()).upper()

    with pytest.raises(ValueError, match="记录无效"):
        _check_journal(root, job)


def test_check_journal_rejects_a_source_inside_the_new_library(tmp_path):
    root, source = _library(tmp_path)
    inside = root / "userdata" / "legacy"
    inside.mkdir(parents=True)
    job = _job(inside)

    with pytest.raises(ValueError, match="不能指向新图库"):
        _check_journal(root, job)


def test_check_journal_rejects_a_source_pointing_at_the_disk_root(tmp_path):
    root, _ = _library(tmp_path)
    job = _job(Path(tmp_path.anchor))

    with pytest.raises(ValueError, match="磁盘根目录"):
        _check_journal(root, job)


def test_finish_refuses_to_clean_before_the_launch_was_validated(tmp_path):
    root, source = _library(tmp_path)
    job = _job(source, phase="published")
    _write(root / "maintenance" / "automatic-upgrade.json", job)
    _write(root / "instance.json", {"instanceId": "instance-1", "dataRoot": {"kind": "relative", "path": "userdata"}})

    with pytest.raises(ValueError, match="禁止清理旧数据"):
        finish(root, "cleanup")


def test_finish_marks_the_job_as_validated(tmp_path):
    root, source = _library(tmp_path)
    job = _job(source, phase="published")
    _write(root / "maintenance" / "automatic-upgrade.json", job)
    _write(root / "instance.json", {"instanceId": "instance-1", "dataRoot": {"kind": "relative", "path": "userdata"}})

    updated = finish(root, "validated")

    assert updated["phase"] == "validated"
    stored = json.loads((root / "maintenance" / "automatic-upgrade.json").read_text(encoding="utf-8"))
    assert stored["phase"] == "validated"


def test_finish_rejects_a_changed_library_identity(tmp_path):
    root, source = _library(tmp_path)
    job = _job(source, phase="published")
    _write(root / "maintenance" / "automatic-upgrade.json", job)
    _write(root / "instance.json", {"instanceId": "other-instance", "dataRoot": {"kind": "relative", "path": "userdata"}})

    with pytest.raises(ValueError, match="目标已改变"):
        finish(root, "validated")


def test_prepare_returns_none_when_the_library_has_no_legacy_source(tmp_path):
    root, _ = _library(tmp_path)
    (root / "instance.json").write_text(json.dumps({"instanceId": "instance-1"}), encoding="utf-8")

    assert prepare(root) == {"phase": "none"}

