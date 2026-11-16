"""2026-11-16 nightly coverage for ``app/utils/desktop_data_migration.py``.

The 2026-11-16 backend coverage scan reported ``utils/desktop_data_migration.py``
at 93.4% with 12 missed lines.  The remaining gaps are the guard rails of the
offline library relocation:

* ``_wait_for_sidecars`` surviving a dead parent process (lines 84-85),
  ignoring a process that cannot be inspected (lines 98-99) and refusing to
  continue while an old client is still running (lines 103-104);
* ``remove_staging_directory`` refusing a link instead of deleting it
  (line 110) and re-raising an error that is not a read-only file
  (line 116);
* ``migrate_data_directory`` refusing a link inside the library
  (line 157), detecting a corrupted copy (line 198) and publishing into an
  existing empty target directory (line 216).
"""

from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import psutil
import pytest

from app.utils import desktop_data_migration as migration
from app.utils.desktop_data_migration import (
    MARKER,
    _wait_for_sidecars,
    migrate_data_directory,
    remove_staging_directory,
)


pytestmark = [pytest.mark.smoke, pytest.mark.module_portable_upgrade]


def _library(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "data").mkdir(exist_ok=True)
    (root / "data/photo.jpg").write_bytes(b"photo")
    (root / "ai-config.json").write_text("{}", encoding="utf-8")


def _silence_sidecars(monkeypatch) -> None:
    """No other 行影集 client is running during the unit test."""
    monkeypatch.setattr(psutil, "Process", lambda *a, **k: SimpleNamespace(parents=lambda: []))
    monkeypatch.setattr(psutil, "process_iter", lambda *a, **k: iter([]))


# ---------------------------------------------------------------------------
# _wait_for_sidecars
# ---------------------------------------------------------------------------


def test_wait_for_sidecars_survives_a_dead_parent(monkeypatch, tmp_path):
    def dead_parent(*_args, **_kwargs):
        raise psutil.NoSuchProcess(4242)

    monkeypatch.setattr(psutil, "Process", dead_parent)
    monkeypatch.setattr(psutil, "process_iter", lambda *a, **k: iter([]))

    _wait_for_sidecars(tmp_path)


def test_wait_for_sidecars_ignores_a_process_it_cannot_inspect(monkeypatch, tmp_path):
    class Broken:
        @property
        def info(self):
            raise psutil.Error("access denied")

    monkeypatch.setattr(psutil, "Process", lambda *a, **k: SimpleNamespace(parents=lambda: []))
    monkeypatch.setattr(psutil, "process_iter", lambda *a, **k: iter([Broken()]))

    _wait_for_sidecars(tmp_path)


def test_wait_for_sidecars_refuses_to_run_while_an_old_client_lives(monkeypatch, tmp_path):
    class Sidecar:
        info = {"pid": 4242, "name": "trailsnap-server.exe", "cwd": str(tmp_path)}

    monkeypatch.setattr(psutil, "Process", lambda *a, **k: SimpleNamespace(parents=lambda: []))
    monkeypatch.setattr(psutil, "process_iter", lambda *a, **k: iter([Sidecar()]))

    clock = {"now": 0.0}
    monkeypatch.setattr("time.monotonic", lambda: clock["now"])
    monkeypatch.setattr("time.sleep", lambda _seconds: clock.__setitem__("now", clock["now"] + 1))

    with pytest.raises(ValueError, match="后台服务运行"):
        _wait_for_sidecars(tmp_path)


# ---------------------------------------------------------------------------
# remove_staging_directory
# ---------------------------------------------------------------------------


def test_remove_staging_directory_refuses_a_link(monkeypatch, tmp_path):
    staging = tmp_path / "staging"
    staging.mkdir()
    monkeypatch.setattr(Path, "is_symlink", lambda self: True)

    with pytest.raises(ValueError, match="链接"):
        remove_staging_directory(staging)


def test_remove_staging_directory_reraises_an_unexpected_error(monkeypatch, tmp_path):
    staging = tmp_path / "staging"
    staging.mkdir()
    target = staging / "file.txt"
    target.write_text("data", encoding="utf-8")

    def fake_rmtree(path, onerror=None):
        onerror(os.unlink, str(target), (OSError, ValueError("boom"), None))

    monkeypatch.setattr(shutil, "rmtree", fake_rmtree)

    with pytest.raises(ValueError, match="boom"):
        remove_staging_directory(staging)


# ---------------------------------------------------------------------------
# migrate_data_directory
# ---------------------------------------------------------------------------


def test_migration_refuses_a_link_inside_the_library(monkeypatch, tmp_path):
    source, target = tmp_path / "source", tmp_path / "target"
    _library(source)
    link = source / "data" / "link.jpg"
    link.write_bytes(b"link")

    original_is_symlink = Path.is_symlink

    def fake_is_symlink(self):
        if str(self).endswith("link.jpg"):
            return True
        return original_is_symlink(self)

    monkeypatch.setattr(Path, "is_symlink", fake_is_symlink)
    _silence_sidecars(monkeypatch)

    with pytest.raises(ValueError, match="含有链接"):
        migrate_data_directory(source, target)


def test_migration_detects_a_corrupted_copy(monkeypatch, tmp_path):
    source, target = tmp_path / "source", tmp_path / "target"
    _library(source)
    _silence_sidecars(monkeypatch)

    digests = iter([b"first", b"second"])
    monkeypatch.setattr(hashlib, "file_digest", lambda *a, **k: SimpleNamespace(digest=lambda: next(digests)))

    with pytest.raises(ValueError, match="复制文件校验失败"):
        migrate_data_directory(source, target)


def test_migration_publishes_into_an_existing_empty_target(monkeypatch, tmp_path):
    source, target = tmp_path / "source", tmp_path / "target"
    _library(source)
    target.mkdir()
    _silence_sidecars(monkeypatch)

    migrate_data_directory(source, target)

    assert (target / "data/photo.jpg").read_bytes() == b"photo"
    assert (target / MARKER).is_file()

