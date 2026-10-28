"""2026-10-28 nightly coverage for ``app/utils/automatic_upgrade.py``.

The 2026-10-28 backend coverage scan reported ``utils/automatic_upgrade.py``
at 71.6% with 73 uncovered lines.  The uncovered code is the *safety* layer of
the first-launch upgrade: everything that decides whether an automatic
migration may start, continue or delete anything.

* ``_inventory`` -- the file list of the legacy root, the "managed" flag that
  decides what may be deleted later, and the refusal to follow links;
* ``_check_journal`` -- the guards that detect a tampered or relocated job;
* ``prepare`` -- the discovery guards (several / broken / already portable
  sources, a non-empty ``userdata``, an invalid build id);
* ``finish`` -- the guards that only allow a cleanup after a verified launch.

A regression here can delete user data, so every guard is asserted on the
reject side as well.
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


pytestmark = [pytest.mark.smoke, pytest.mark.module_desktop]


def _upgrade():
    from app.utils import automatic_upgrade

    return automatic_upgrade


def _instance(root: Path, instance_id: str) -> dict:
    return {
        "schemaVersion": 1,
        "mode": "portable",
        "instanceId": instance_id,
        "displayName": root.name,
        "activeBuild": "1.0.0",
        "previousBuild": None,
        "dataRoot": {"kind": "relative", "path": "userdata"},
        "serverPort": None,
        "fixedPort": False,
    }


def _job(source: Path, root: Path, phase: str = "copying", instance_id: str = "instance-1") -> dict:
    return {
        "schemaVersion": 1,
        "id": str(uuid.uuid4()),
        "source": str(source),
        "phase": phase,
        "instance": _instance(root, instance_id),
    }


# ---------------------------------------------------------------------------
# _inventory
# ---------------------------------------------------------------------------


def test_inventory_lists_files_and_marks_the_managed_ones(tmp_path):
    upgrade = _upgrade()
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "trailsnap.sqlite").write_bytes(b"db")
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "server.log").write_bytes(b"log")
    (tmp_path / "notes.txt").write_bytes(b"note")

    records = upgrade._inventory(tmp_path)

    paths = {record["path"]: record for record in records}
    assert set(paths) == {"data/trailsnap.sqlite", "logs/server.log", "notes.txt"}
    assert paths["data/trailsnap.sqlite"]["cleanup"] is True
    assert paths["logs/server.log"]["cleanup"] is True
    assert paths["notes.txt"]["cleanup"] is False
    assert all(len(record["sha256"]) == 64 for record in records)


def test_inventory_reports_progress_while_walking(tmp_path):
    upgrade = _upgrade()
    (tmp_path / "notes.txt").write_bytes(b"note")
    seen = []
    upgrade._inventory(tmp_path, progress=lambda completed, total: seen.append((completed, total)))
    assert seen and all(entry == (0, 0) for entry in seen)


def test_inventory_refuses_a_linked_legacy_root(tmp_path):
    upgrade = _upgrade()
    (tmp_path / "real.txt").write_bytes(b"real")
    try:
        os.symlink(tmp_path / "real.txt", tmp_path / "link.txt")
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not available on this platform")
    with pytest.raises(ValueError) as excinfo:
        upgrade._inventory(tmp_path)
    assert "链接" in str(excinfo.value)


def test_inventory_skips_the_excluded_entries(tmp_path):
    upgrade = _upgrade()
    (tmp_path / ".trailsnap-migration.json").write_bytes(b"{}")
    (tmp_path / "webview").mkdir()
    (tmp_path / "webview" / "state").write_bytes(b"x")
    (tmp_path / "notes.txt").write_bytes(b"note")

    paths = {record["path"] for record in upgrade._inventory(tmp_path)}

    assert paths == {"notes.txt"}


# ---------------------------------------------------------------------------
# _check_journal
# ---------------------------------------------------------------------------


def test_check_journal_rejects_an_unknown_schema(tmp_path):
    upgrade = _upgrade()
    source = tmp_path / "legacy"
    source.mkdir()
    job = _job(source, tmp_path)
    job["schemaVersion"] = 2
    with pytest.raises(ValueError) as excinfo:
        upgrade._check_journal(tmp_path, job)
    assert "自动迁移记录无效" in str(excinfo.value)


def test_check_journal_rejects_a_malformed_identifier(tmp_path):
    upgrade = _upgrade()
    source = tmp_path / "legacy"
    source.mkdir()
    job = _job(source, tmp_path)
    job["id"] = "not-a-uuid"
    with pytest.raises(ValueError):
        upgrade._check_journal(tmp_path, job)


def test_check_journal_rejects_a_source_inside_the_new_library(tmp_path):
    upgrade = _upgrade()
    source = tmp_path / "userdata"
    source.mkdir()
    job = _job(source, tmp_path)
    with pytest.raises(ValueError) as excinfo:
        upgrade._check_journal(tmp_path, job)
    assert "旧数据位置不能指向新图库" in str(excinfo.value)


def test_check_journal_returns_the_source_and_the_stage(tmp_path):
    upgrade = _upgrade()
    source = tmp_path / "legacy"
    source.mkdir()
    job = _job(source, tmp_path)
    resolved, stage = upgrade._check_journal(tmp_path, job)
    assert resolved == source.resolve()
    assert stage == tmp_path.parent / (".trailsnap-auto-" + job["id"])


# ---------------------------------------------------------------------------
# prepare
# ---------------------------------------------------------------------------


def test_prepare_is_a_no_op_for_an_existing_instance(tmp_path):
    upgrade = _upgrade()
    (tmp_path / "instance.json").write_text(json.dumps(_instance(tmp_path, "i-1")), encoding="utf-8")
    assert upgrade.prepare(tmp_path) == {"phase": "none"}


def test_prepare_returns_a_finished_job(tmp_path):
    upgrade = _upgrade()
    source = tmp_path / "legacy"
    source.mkdir()
    (tmp_path / "maintenance").mkdir()
    job = _job(source, tmp_path, phase="published")
    (tmp_path / "maintenance" / "automatic-upgrade.json").write_text(json.dumps(job), encoding="utf-8")
    (tmp_path / "instance.json").write_text(json.dumps(job["instance"]), encoding="utf-8")
    assert upgrade.prepare(tmp_path)["phase"] == "published"


def test_prepare_refuses_a_changed_instance_identity(tmp_path):
    upgrade = _upgrade()
    source = tmp_path / "legacy"
    source.mkdir()
    (tmp_path / "maintenance").mkdir()
    job = _job(source, tmp_path, phase="published")
    (tmp_path / "maintenance" / "automatic-upgrade.json").write_text(json.dumps(job), encoding="utf-8")
    (tmp_path / "instance.json").write_text(json.dumps(_instance(tmp_path, "other")), encoding="utf-8")
    with pytest.raises(ValueError) as excinfo:
        upgrade.prepare(tmp_path)
    assert "图库身份或位置已改变" in str(excinfo.value)


def test_prepare_is_a_no_op_without_any_candidate(tmp_path):
    upgrade = _upgrade()
    discovery = {"candidates": [], "notices": []}
    with patch("app.utils.automatic_upgrade.discover_libraries", return_value=discovery):
        assert upgrade.prepare(tmp_path) == {"phase": "none"}


def test_prepare_refuses_several_candidates(tmp_path):
    upgrade = _upgrade()
    discovery = {
        "candidates": [{"path": str(tmp_path / "a"), "error": None}, {"path": str(tmp_path / "b"), "error": None}],
        "notices": [],
    }
    with patch("app.utils.automatic_upgrade.discover_libraries", return_value=discovery):
        with pytest.raises(ValueError) as excinfo:
            upgrade.prepare(tmp_path)
    assert "多个或不可用的旧图库" in str(excinfo.value)


def test_prepare_refuses_a_broken_candidate(tmp_path):
    upgrade = _upgrade()
    discovery = {"candidates": [{"path": str(tmp_path / "a"), "error": "磁盘不可用"}], "notices": []}
    with patch("app.utils.automatic_upgrade.discover_libraries", return_value=discovery):
        with pytest.raises(ValueError) as excinfo:
            upgrade.prepare(tmp_path)
    assert "磁盘不可用" in str(excinfo.value)


def test_prepare_refuses_an_already_portable_source(tmp_path):
    upgrade = _upgrade()
    source = tmp_path / "legacy"
    source.mkdir()
    (source / "library.json").write_text("{}", encoding="utf-8")
    discovery = {"candidates": [{"path": str(source), "error": None}], "notices": []}
    with patch("app.utils.automatic_upgrade.discover_libraries", return_value=discovery):
        with pytest.raises(ValueError) as excinfo:
            upgrade.prepare(tmp_path)
    assert "已有便携图库" in str(excinfo.value)


def test_prepare_refuses_a_non_empty_userdata(tmp_path):
    upgrade = _upgrade()
    source = tmp_path / "legacy"
    source.mkdir()
    (tmp_path / "userdata").mkdir()
    (tmp_path / "userdata" / "keep.txt").write_text("x", encoding="utf-8")
    discovery = {"candidates": [{"path": str(source), "error": None}], "notices": []}
    with patch("app.utils.automatic_upgrade.discover_libraries", return_value=discovery):
        with pytest.raises(ValueError) as excinfo:
            upgrade.prepare(tmp_path)
    assert "userdata 已有数据" in str(excinfo.value)


def test_prepare_refuses_an_invalid_build_id(tmp_path):
    upgrade = _upgrade()
    source = tmp_path / "legacy"
    source.mkdir()
    (tmp_path / "portable.json").write_text(json.dumps({"activeBuild": "../escape"}), encoding="utf-8")
    discovery = {"candidates": [{"path": str(source), "error": None}], "notices": []}
    with patch("app.utils.automatic_upgrade.discover_libraries", return_value=discovery):
        with pytest.raises(ValueError) as excinfo:
            upgrade.prepare(tmp_path)
    assert "程序版本无效" in str(excinfo.value)


# ---------------------------------------------------------------------------
# finish
# ---------------------------------------------------------------------------


def test_finish_refuses_a_cleanup_before_validation(tmp_path):
    upgrade = _upgrade()
    source = tmp_path / "legacy"
    source.mkdir()
    (tmp_path / "maintenance").mkdir()
    job = _job(source, tmp_path, phase="published")
    (tmp_path / "maintenance" / "automatic-upgrade.json").write_text(json.dumps(job), encoding="utf-8")
    (tmp_path / "instance.json").write_text(json.dumps(job["instance"]), encoding="utf-8")
    with pytest.raises(ValueError) as excinfo:
        upgrade.finish(tmp_path, "cleanup")
    assert "禁止清理旧数据" in str(excinfo.value)


def test_finish_marks_a_published_job_as_validated(tmp_path):
    upgrade = _upgrade()
    source = tmp_path / "legacy"
    source.mkdir()
    (tmp_path / "maintenance").mkdir()
    job = _job(source, tmp_path, phase="published")
    (tmp_path / "maintenance" / "automatic-upgrade.json").write_text(json.dumps(job), encoding="utf-8")
    (tmp_path / "instance.json").write_text(json.dumps(job["instance"]), encoding="utf-8")
    finished = upgrade.finish(tmp_path, "validated")
    assert finished["phase"] == "validated"
    stored = json.loads((tmp_path / "maintenance" / "automatic-upgrade.json").read_text(encoding="utf-8"))
    assert stored["phase"] == "validated"


def test_finish_keeps_an_already_validated_job(tmp_path):
    upgrade = _upgrade()
    source = tmp_path / "legacy"
    source.mkdir()
    (tmp_path / "maintenance").mkdir()
    job = _job(source, tmp_path, phase="validated")
    (tmp_path / "maintenance" / "automatic-upgrade.json").write_text(json.dumps(job), encoding="utf-8")
    (tmp_path / "instance.json").write_text(json.dumps(job["instance"]), encoding="utf-8")
    assert upgrade.finish(tmp_path, "validated")["phase"] == "validated"


def test_finish_refuses_a_changed_target(tmp_path):
    upgrade = _upgrade()
    source = tmp_path / "legacy"
    source.mkdir()
    (tmp_path / "maintenance").mkdir()
    job = _job(source, tmp_path, phase="validated")
    (tmp_path / "maintenance" / "automatic-upgrade.json").write_text(json.dumps(job), encoding="utf-8")
    (tmp_path / "instance.json").write_text(json.dumps(_instance(tmp_path, "other")), encoding="utf-8")
    with pytest.raises(ValueError) as excinfo:
        upgrade.finish(tmp_path, "validated")
    assert "自动迁移目标已改变" in str(excinfo.value)


def test_automatic_upgrade_dispatches_on_the_action(tmp_path):
    upgrade = _upgrade()
    with patch("app.utils.automatic_upgrade.prepare", return_value={"phase": "none"}) as prepare:
        assert upgrade.automatic_upgrade(tmp_path, "prepare") == {"phase": "none"}
    prepare.assert_called_once()
    with patch("app.utils.automatic_upgrade.finish", return_value={"phase": "validated"}) as finish:
        assert upgrade.automatic_upgrade(tmp_path, "cleanup") == {"phase": "validated"}
    finish.assert_called_once()
