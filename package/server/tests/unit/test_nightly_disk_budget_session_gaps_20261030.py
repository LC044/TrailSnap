"""Unit tests for the remaining ``app/service/disk_budget.py`` and
``app/db/session.py`` branches.

Coverage scan 2026-10-30:

* ``app/service/disk_budget.py`` -- 89.5%, 11 missed lines.  The misses were
  the POSIX branch of ``DiskBudget.volume`` (never executed on Windows) and
  the three ``BudgetedFile`` capability delegates (``readable`` /
  ``writable`` / ``seekable``), which no caller needs but a decoder may ask
  for.
* ``app/db/session.py`` -- 89.2%, 4 missed lines.  The misses were the
  import-time environment resolution (desktop SQLite fallback and the
  "no DB URL at all" guard) plus the early return of the portable photo
  path listener when the library is not in portable mode.

The database-URL resolution happens while the module is imported, so it is
exercised in a clean subprocess instead of reloading the module in-process
(reloading would swap the engine of a live test session).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.service import disk_budget as db


pytestmark = [pytest.mark.smoke]


SERVER_ROOT = Path(__file__).resolve().parents[2]


# -------------------------------------------------------------------------
# disk_budget -- BudgetedFile capability delegates
# -------------------------------------------------------------------------


def test_budgeted_file_reports_stream_capabilities(tmp_path):
    path = tmp_path / "payload.bin"
    path.write_bytes(b"abc")

    handle = db.budgeted_open(str(path))
    try:
        assert handle.readable() is True
        assert handle.writable() is False
        assert handle.seekable() is True
    finally:
        handle.close()


# -------------------------------------------------------------------------
# disk_budget -- POSIX volume resolution
# -------------------------------------------------------------------------


class _OsShim:
    """A stand-in for the ``os`` module that pretends to be POSIX."""

    name = "posix"
    path = os.path
    fspath = staticmethod(os.fspath)
    curdir = os.curdir

    def __init__(self, stat):
        self._stat = stat

    def stat(self, path, *args, **kwargs):
        return self._stat(path, *args, **kwargs)


def test_volume_uses_device_id_of_nearest_existing_parent(tmp_path, monkeypatch):
    target = tmp_path / "missing" / "deeper"
    real_stat = os.stat

    def fake_stat(path, *args, **kwargs):
        if str(path).startswith(str(tmp_path / "missing")):
            raise OSError("no such directory")
        return real_stat(path, *args, **kwargs)

    monkeypatch.setattr(db, "os", _OsShim(fake_stat))
    volume = db.DiskBudget.volume(str(target))
    assert volume == real_stat(str(tmp_path)).st_dev


def test_volume_returns_absolute_path_when_no_ancestor_exists(tmp_path, monkeypatch):
    def always_fails(path, *args, **kwargs):
        raise OSError("no such directory")

    monkeypatch.setattr(db, "os", _OsShim(always_fails))
    volume = db.DiskBudget.volume(str(tmp_path / "gone"))

    # No ancestor can be stat'ed either, so the walk stops at the root.
    expected = os.path.abspath(str(tmp_path / "gone"))
    while os.path.dirname(expected) != expected:
        expected = os.path.dirname(expected)
    assert volume == expected


# -------------------------------------------------------------------------
# db/session -- import time environment resolution
# -------------------------------------------------------------------------


def _run_session_import(env_overrides, code):
    env = dict(os.environ)
    env.pop("TS_DB_URL", None)
    env.pop("DB_URL", None)
    env.update(env_overrides)
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(SERVER_ROOT),
        env=env,
        capture_output=True,
        text=True,
    )


def test_session_falls_back_to_desktop_sqlite(tmp_path):
    result = _run_session_import(
        {"TS_DESKTOP": "1", "TS_DATA_DIR": str(tmp_path)},
        "from app.db.session import DATABASE_URL, IS_SQLITE; print(DATABASE_URL); print(IS_SQLITE)",
    )
    assert result.returncode == 0, result.stderr
    url, is_sqlite = result.stdout.strip().splitlines()[-2:]
    assert url.startswith("sqlite:///")
    assert url.endswith("trailsnap.sqlite")
    assert is_sqlite == "True"


def test_session_requires_a_database_url():
    result = _run_session_import(
        {},
        "import app.db.session",
    )
    assert result.returncode != 0
    assert "DB_URL or TS_DB_URL" in result.stderr


# -------------------------------------------------------------------------
# db/session -- portable photo path listener
# -------------------------------------------------------------------------


def test_encode_portable_photo_paths_is_skipped_outside_portable_mode(monkeypatch):
    from app.db import session as session_module

    monkeypatch.setattr("app.service.storage_paths.portable_enabled", lambda: False)
    calls = []
    monkeypatch.setattr(
        "app.service.storage_paths.apply_photo_reference",
        lambda *args, **kwargs: calls.append(args),
    )

    sentinel = object()
    assert session_module._encode_portable_photo_paths(sentinel, None, None) is None
    assert calls == []

