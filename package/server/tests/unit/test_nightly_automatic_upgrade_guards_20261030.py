"""Unit tests for the remaining ``app/utils/automatic_upgrade.py`` branches.

Coverage scan 2026-10-30 showed the module at 89.1% with 28 missed lines.
The misses were the guards that decide whether an old library may be
migrated and cleaned up:

* the source may not be the disk root, may not be a portable library, and
  the new ``userdata`` may not contain data yet;
* the staging directory must belong to this job -- a foreign staging
  directory is never deleted;
* the published library must carry this job's ownership marker;
* the legacy desktop pointer's server port is carried over to the new
  instance;
* the inventory refuses to walk a directory that contains a link.

``prepare``/``finish`` touch the file system, so the heavy helpers
(media baseline, data migration, database preparation) are stubbed and the
assertions target the decisions the module made.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch
from uuid import UUID

import pytest


pytestmark = [pytest.mark.smoke]


from app.utils import automatic_upgrade as au  # noqa: E402


FIXED_ID = UUID("11111111-2222-3333-4444-555555555555")
FIXED_ID_TEXT = str(FIXED_ID)


# -------------------------------------------------------------------------
# helpers
# -------------------------------------------------------------------------


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _make_root(tmp_path) -> Path:
    root = tmp_path / "new"
    root.mkdir()
    _write_json(root / "portable.json", {"activeBuild": "1.2.3"})
    return root


def _make_source(tmp_path) -> Path:
    source = tmp_path / "legacy"
    (source / "data").mkdir(parents=True)
    # The legacy lock opens this file; it must exist on Windows.
    (source / "data" / "trailsnap.sqlite").write_bytes(b"")
    return source


def _discovery(source, notices=None, candidates=None):
    return {
        "candidates": candidates if candidates is not None
        else [{"path": str(source), "error": None}],
        "notices": notices or [],
    }


@pytest.fixture()
def stub_heavy_steps(monkeypatch):
    """Replace every step that would touch a real library / database."""
    calls = {"remove_staging": [], "migrate": [], "replace": []}

    monkeypatch.setattr(au, "_prepare", lambda data: None)
    monkeypatch.setattr(au, "media_baseline", lambda *args, **kwargs: [])
    monkeypatch.setattr(au, "verify_media", lambda *args, **kwargs: None)
    monkeypatch.setattr(au, "migrate_data_directory", lambda *args, **kwargs: calls["migrate"].append(args))
    monkeypatch.setattr(
        au, "remove_staging_directory", lambda stage: calls["remove_staging"].append(stage)
    )
    monkeypatch.setattr(
        "app.utils.portable_library.prepare_portable_library", lambda data: None
    )
    return calls


# -------------------------------------------------------------------------
# source guards
# -------------------------------------------------------------------------


def test_prepare_refuses_to_migrate_the_disk_root(tmp_path, monkeypatch):
    root = _make_root(tmp_path)
    monkeypatch.setattr(
        au, "discover_libraries",
        lambda *args, **kwargs: _discovery(None, candidates=[{"path": os.path.abspath(os.sep), "error": None}]),
    )

    with pytest.raises(ValueError, match="磁盘根目录"):
        au.prepare(root)


def test_prepare_refuses_a_portable_source_library(tmp_path, monkeypatch):
    root = _make_root(tmp_path)
    source = _make_source(tmp_path)
    (source / "library.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(au, "discover_libraries", lambda *args, **kwargs: _discovery(source))

    with pytest.raises(ValueError, match="便携图库"):
        au.prepare(root)


def test_prepare_refuses_when_userdata_already_has_data(tmp_path, monkeypatch):
    root = _make_root(tmp_path)
    source = _make_source(tmp_path)
    (root / "userdata").mkdir()
    (root / "userdata" / "keep.txt").write_text("keep", encoding="utf-8")
    monkeypatch.setattr(au, "discover_libraries", lambda *args, **kwargs: _discovery(source))

    with pytest.raises(ValueError, match="userdata 已有数据"):
        au.prepare(root)


# -------------------------------------------------------------------------
# staging directory ownership
# -------------------------------------------------------------------------


def test_prepare_refuses_a_foreign_staging_directory(tmp_path, monkeypatch):
    root = _make_root(tmp_path)
    source = _make_source(tmp_path)
    monkeypatch.setattr(au, "discover_libraries", lambda *args, **kwargs: _discovery(source))
    monkeypatch.setattr(au.uuid, "uuid4", lambda: FIXED_ID)

    stage = root.parent / (".trailsnap-auto-" + FIXED_ID_TEXT)
    stage.mkdir()
    _write_json(stage / "automatic-upgrade-owner.json", {"operationId": "someone-else"})

    with pytest.raises(ValueError, match="迁移临时目录需检查"):
        au.prepare(root)


def test_prepare_removes_the_staging_directory_owned_by_this_job(tmp_path, monkeypatch, stub_heavy_steps):
    root = _make_root(tmp_path)
    source = _make_source(tmp_path)
    monkeypatch.setattr(au, "discover_libraries", lambda *args, **kwargs: _discovery(source))
    monkeypatch.setattr(au.uuid, "uuid4", lambda: FIXED_ID)

    stage = root.parent / (".trailsnap-auto-" + FIXED_ID_TEXT)
    stage.mkdir()
    _write_json(stage / "automatic-upgrade-owner.json", {"operationId": FIXED_ID_TEXT})

    job = au.prepare(root)

    assert job["phase"] == "published"
    assert stub_heavy_steps["remove_staging"] == [stage]
    assert stub_heavy_steps["migrate"], "the data directory must be migrated"


# -------------------------------------------------------------------------
# publishing an already prepared job
# -------------------------------------------------------------------------


def test_prepare_refuses_a_published_library_owned_by_another_job(tmp_path, monkeypatch):
    root = _make_root(tmp_path)
    source = _make_source(tmp_path)

    _write_json(root / "maintenance" / "automatic-upgrade.json", {
        "schemaVersion": 1,
        "id": FIXED_ID_TEXT,
        "source": str(source.resolve()),
        "phase": "prepared",
        "instance": {"instanceId": "abc", "dataRoot": {"kind": "relative", "path": "userdata"}},
    })
    userdata = root / "userdata"
    userdata.mkdir()
    _write_json(userdata / "automatic-upgrade-owner.json", {"operationId": "someone-else"})

    with pytest.raises(ValueError, match="新图库不属于本次迁移"):
        au.prepare(root)


# -------------------------------------------------------------------------
# the legacy server port is carried over
# -------------------------------------------------------------------------


def test_prepare_carries_over_the_legacy_server_port(tmp_path, monkeypatch, stub_heavy_steps):
    root = _make_root(tmp_path)
    source = _make_source(tmp_path)
    monkeypatch.setattr(au, "discover_libraries", lambda *args, **kwargs: _discovery(source))
    monkeypatch.setattr(au.uuid, "uuid4", lambda: FIXED_ID)

    local = tmp_path / "localappdata"
    local.mkdir()
    _write_json(local / "TrailSnap-desktop.json", {"root": str(source.resolve()), "server_port": 4321})
    monkeypatch.setenv("LOCALAPPDATA", str(local))

    job = au.prepare(root)

    assert job["instance"]["serverPort"] == 4321
    instance = json.loads((root / "instance.json").read_text(encoding="utf-8"))
    assert instance["serverPort"] == 4321


# -------------------------------------------------------------------------
# inventory refuses directories that contain a link
# -------------------------------------------------------------------------


def test_inventory_refuses_a_directory_that_contains_a_link(tmp_path, monkeypatch):
    source = tmp_path / "legacy"
    (source / "data").mkdir(parents=True)
    (source / "data" / "link.txt").write_text("x", encoding="utf-8")

    real_is_symlink = Path.is_symlink

    def fake_is_symlink(self):
        if self.name == "link.txt":
            return True
        return real_is_symlink(self)

    monkeypatch.setattr(Path, "is_symlink", fake_is_symlink)

    with pytest.raises(ValueError, match="含链接"):
        au._inventory(source)


def test_inventory_records_managed_files_only(tmp_path):
    source = tmp_path / "legacy"
    (source / "data").mkdir(parents=True)
    (source / "data" / "trailsnap.sqlite").write_bytes(b"")
    (source / "notes.txt").write_text("hello", encoding="utf-8")

    records = {row["path"]: row for row in au._inventory(source)}

    assert records["data/trailsnap.sqlite"]["cleanup"] is True
    assert records["notes.txt"]["cleanup"] is False

