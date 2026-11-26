"""Nightly watch 2026-11-25 (part 3): cover the automatic-upgrade source guards.

``app/utils/automatic_upgrade.py::prepare`` validates the legacy source before a
single byte is copied.  Those guards decide whether the launcher may keep
deleting the old library afterwards, so they were worth a dedicated test file.

``tests/unit/test_automatic_upgrade.py`` already covers the happy path through
the real desktop entry point (several libraries, non-empty userdata).  The
guards below stop *before* any copy and were never exercised: discovery
notices, an unusable candidate, a source that is the disk root, a source that
is already a portable library, an invalid build name, the manual source
selection and a journal whose library identity changed.
"""
import json
from pathlib import Path

import pytest

from app.utils import automatic_upgrade
from app.utils.automatic_upgrade import prepare


def _write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _root(tmp_path: Path) -> Path:
    """A fresh library root that has no instance.json and no journal."""
    root = tmp_path / "library"
    root.mkdir()
    (root / "maintenance").mkdir()
    return root


def _install_discovery(monkeypatch, candidates, notices=()):
    """Replace the legacy-library discovery with a fixed answer."""
    def fake_discover(root, data_root, local=None):
        return {"candidates": list(candidates), "notices": list(notices)}

    # automatic_upgrade imports discover_libraries at module level.
    monkeypatch.setattr(automatic_upgrade, "discover_libraries", fake_discover)


def test_prepare_stops_when_discovery_reports_a_notice(tmp_path, monkeypatch):
    root = _root(tmp_path)
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    _install_discovery(monkeypatch, [{"path": str(legacy), "error": None}], notices=["图库正在使用中"])

    with pytest.raises(ValueError, match="检测到多个或不可用的旧图库"):
        prepare(root)


def test_prepare_stops_when_the_candidate_reports_an_error(tmp_path, monkeypatch):
    root = _root(tmp_path)
    _install_discovery(monkeypatch, [{"path": str(tmp_path / "missing"), "error": "旧图库路径不存在"}])

    with pytest.raises(ValueError, match="旧图库路径不存在"):
        prepare(root)


def test_prepare_stops_when_the_source_is_the_disk_root(tmp_path, monkeypatch):
    root = _root(tmp_path)
    _install_discovery(monkeypatch, [{"path": Path(tmp_path.anchor).as_posix(), "error": None}])

    with pytest.raises(ValueError, match="不能自动迁移磁盘根目录"):
        prepare(root)


def test_prepare_stops_when_the_source_is_already_a_portable_library(tmp_path, monkeypatch):
    root = _root(tmp_path)
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    (legacy / "library.json").write_text("{}", encoding="utf-8")
    _install_discovery(monkeypatch, [{"path": str(legacy), "error": None}])

    with pytest.raises(ValueError, match="已有便携图库"):
        prepare(root)


def test_prepare_stops_when_the_active_build_is_not_a_plain_name(tmp_path, monkeypatch):
    root = _root(tmp_path)
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    _write(root / "portable.json", {"activeBuild": "nested/build"})
    _install_discovery(monkeypatch, [{"path": str(legacy), "error": None}])

    with pytest.raises(ValueError, match="程序版本无效"):
        prepare(root)


def test_prepare_honours_the_manual_source_selection(tmp_path, monkeypatch):
    """A saved selection replaces discovery, so exactly one candidate survives."""
    root = _root(tmp_path)
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    _write(root / "maintenance" / "automatic-upgrade-source.json", {"source": str(legacy)})
    _install_discovery(monkeypatch, [
        {"path": str(tmp_path / "legacy-a"), "error": None},
        {"path": str(tmp_path / "legacy-b"), "error": None},
    ])

    # The selection file is validated by portable_conversion.validate_library_source;
    # the guard that matters here is that discovery candidates are replaced.
    from app.utils import portable_conversion

    monkeypatch.setattr(portable_conversion, "validate_library_source", lambda path: legacy)
    # An invalid build stops the run right after the source was accepted.
    _write(root / "portable.json", {"activeBuild": ".."})

    with pytest.raises(ValueError, match="程序版本无效"):
        prepare(root)


def test_prepare_rejects_a_journal_whose_library_identity_changed(tmp_path):
    """A finished journal is only trusted while the library still matches it."""
    root = _root(tmp_path)
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    job = {
        "id": "b7f1f1a2-0b9c-4c2e-9d3f-3f6b7a1c2d3e",
        "schemaVersion": 1,
        "phase": "published",
        "source": str(legacy),
        "instance": {"instanceId": "instance-1"},
        "media": [],
        "files": [],
    }
    _write(root / "maintenance" / "automatic-upgrade.json", job)
    _write(root / "instance.json", {"instanceId": "other", "dataRoot": {"kind": "relative", "path": "userdata"}})

    with pytest.raises(ValueError, match="图库身份或位置已改变"):
        prepare(root)
