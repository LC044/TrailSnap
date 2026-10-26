"""Nightly coverage for the upgrade journal guards of ``app/utils/automatic_upgrade.py``.

The 2026-10-26 backend coverage scan listed ``utils/automatic_upgrade.py`` at
56.4% with 112 missed lines.  The missed code is the part that decides whether
the launcher may *delete* the user's legacy photo library:

* ``_check_journal`` validates the persisted job (schema, id, source path).
* ``prepare`` refuses to continue when the new library identity moved.
* ``finish`` refuses to clean up before a real launch validated the copy.

Every one of those branches is a pure guard over a JSON journal, so they are
exercised with a throw-away root directory.
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

import pytest

pytestmark = [pytest.mark.smoke]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _job(source_dir: Path, **overrides) -> dict:
    job = {
        "schemaVersion": 1,
        "id": str(uuid.uuid4()),
        "source": str(source_dir),
        "phase": "published",
        "instance": {"instanceId": str(uuid.uuid4()), "dataRoot": {"kind": "relative", "path": "userdata"}},
    }
    job.update(overrides)
    return job


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def _root(tmp_path: Path) -> Path:
    root = tmp_path / "instance"
    (root / "maintenance").mkdir(parents=True)
    return root


def _instance_config(job: dict) -> dict:
    return {"instanceId": job["instance"]["instanceId"], "dataRoot": {"kind": "relative", "path": "userdata"}}


# ---------------------------------------------------------------------------
# _check_journal
# ---------------------------------------------------------------------------


def test_check_journal_rejects_an_unknown_schema(tmp_path):
    from app.utils import automatic_upgrade

    root = _root(tmp_path)
    with pytest.raises(ValueError, match="自动迁移记录无效"):
        automatic_upgrade._check_journal(root, _job(tmp_path / "legacy", schemaVersion=2))


def test_check_journal_rejects_a_malformed_identifier(tmp_path):
    from app.utils import automatic_upgrade

    root = _root(tmp_path)
    with pytest.raises(ValueError):
        automatic_upgrade._check_journal(root, _job(tmp_path / "legacy", id="not-a-uuid"))


def test_check_journal_rejects_a_changed_source_path(tmp_path):
    from app.utils import automatic_upgrade

    root = _root(tmp_path)
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    # The persisted path is not the resolved path anymore -> refuse to clean up.
    job = _job(legacy, source=str(legacy) + os.sep)
    with pytest.raises(ValueError, match="旧数据根目录已改变"):
        automatic_upgrade._check_journal(root, job)


def test_check_journal_rejects_a_disk_root(tmp_path):
    from app.utils import automatic_upgrade

    root = _root(tmp_path)
    anchor = Path(Path(os.path.abspath(os.sep)).anchor)
    job = _job(anchor, source=str(anchor))
    with pytest.raises(ValueError, match="指向磁盘根目录"):
        automatic_upgrade._check_journal(root, job)


def test_check_journal_rejects_a_source_inside_the_new_library(tmp_path):
    from app.utils import automatic_upgrade

    root = _root(tmp_path)
    nested = root / "userdata" / "legacy"
    nested.mkdir(parents=True)
    job = _job(nested)
    with pytest.raises(ValueError, match="旧数据位置不能指向新图库"):
        automatic_upgrade._check_journal(root, job)


def test_check_journal_returns_the_source_and_the_staging_sibling(tmp_path):
    from app.utils import automatic_upgrade

    root = _root(tmp_path)
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    job = _job(legacy)

    source, stage = automatic_upgrade._check_journal(root, job)
    assert source == legacy.resolve()
    assert stage == root.parent / (".trailsnap-auto-" + job["id"])


# ---------------------------------------------------------------------------
# prepare
# ---------------------------------------------------------------------------


def test_prepare_returns_none_when_the_library_is_already_converted(tmp_path):
    from app.utils import automatic_upgrade

    root = _root(tmp_path)
    _write_json(root / "instance.json", {"instanceId": str(uuid.uuid4())})
    assert automatic_upgrade.prepare(root) == {"phase": "none"}


def test_prepare_returns_none_when_no_legacy_candidate_exists(tmp_path, monkeypatch):
    from app.utils import automatic_upgrade

    root = _root(tmp_path)
    monkeypatch.setattr(automatic_upgrade, "discover_libraries",
                        lambda *args, **kwargs: {"candidates": [], "notices": []})
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    assert automatic_upgrade.prepare(root) == {"phase": "none"}


def test_prepare_returns_a_published_job(tmp_path):
    from app.utils import automatic_upgrade

    root = _root(tmp_path)
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    job = _job(legacy)
    _write_json(root / "maintenance" / "automatic-upgrade.json", job)
    _write_json(root / "instance.json", _instance_config(job))

    assert automatic_upgrade.prepare(root) == job


def test_prepare_refuses_a_changed_library_identity(tmp_path):
    from app.utils import automatic_upgrade

    root = _root(tmp_path)
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    job = _job(legacy)
    _write_json(root / "maintenance" / "automatic-upgrade.json", job)
    _write_json(root / "instance.json", {"instanceId": str(uuid.uuid4()),
                                         "dataRoot": {"kind": "relative", "path": "userdata"}})

    with pytest.raises(ValueError, match="图库身份或位置已改变"):
        automatic_upgrade.prepare(root)


# ---------------------------------------------------------------------------
# finish
# ---------------------------------------------------------------------------


def test_finish_refuses_cleanup_before_validation(tmp_path):
    from app.utils import automatic_upgrade

    root = _root(tmp_path)
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    job = _job(legacy, phase="published")
    _write_json(root / "maintenance" / "automatic-upgrade.json", job)
    _write_json(root / "instance.json", _instance_config(job))

    with pytest.raises(ValueError, match="未通过启动验证"):
        automatic_upgrade.finish(root, "cleanup")


def test_finish_marks_the_job_as_validated(tmp_path):
    from app.utils import automatic_upgrade

    root = _root(tmp_path)
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    job = _job(legacy, phase="published")
    _write_json(root / "maintenance" / "automatic-upgrade.json", job)
    _write_json(root / "instance.json", _instance_config(job))

    assert automatic_upgrade.finish(root, "validated")["phase"] == "validated"
    stored = json.loads((root / "maintenance" / "automatic-upgrade.json").read_text(encoding="utf-8"))
    assert stored["phase"] == "validated"


def test_finish_keeps_an_already_validated_job(tmp_path):
    from app.utils import automatic_upgrade

    root = _root(tmp_path)
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    job = _job(legacy, phase="validated")
    _write_json(root / "maintenance" / "automatic-upgrade.json", job)
    _write_json(root / "instance.json", _instance_config(job))

    assert automatic_upgrade.finish(root, "validated")["phase"] == "validated"


def test_finish_refuses_a_changed_library_identity(tmp_path):
    from app.utils import automatic_upgrade

    root = _root(tmp_path)
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    job = _job(legacy, phase="published")
    _write_json(root / "maintenance" / "automatic-upgrade.json", job)
    _write_json(root / "instance.json", {"instanceId": str(uuid.uuid4()),
                                         "dataRoot": {"kind": "relative", "path": "userdata"}})

    with pytest.raises(ValueError, match="自动迁移目标已改变"):
        automatic_upgrade.finish(root, "cleanup")


def test_finish_returns_a_completed_job_without_touching_the_legacy_folder(tmp_path):
    from app.utils import automatic_upgrade

    root = _root(tmp_path)
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    (legacy / "keep.txt").write_text("x", encoding="utf-8")
    job = _job(legacy, phase="completed")
    _write_json(root / "maintenance" / "automatic-upgrade.json", job)
    _write_json(root / "instance.json", _instance_config(job))

    assert automatic_upgrade.finish(root, "cleanup")["phase"] == "completed"
    assert (legacy / "keep.txt").is_file()


