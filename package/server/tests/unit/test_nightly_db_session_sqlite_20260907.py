"""Nightly gap coverage for the desktop SQLite engine configuration."""

import importlib
import os

import pytest

pytestmark = pytest.mark.smoke


def test_sqlite_engine_enables_wal_and_large_pool(monkeypatch, tmp_path):
    from app.db import session as session_module

    original_ts = os.environ.get("TS_DB_URL")
    original_db = os.environ.get("DB_URL")
    database = tmp_path / "trailsnap.sqlite"
    monkeypatch.setenv("TS_DB_URL", f"sqlite:///{database.as_posix()}")
    monkeypatch.delenv("DB_URL", raising=False)

    try:
        reloaded = importlib.reload(session_module)
        assert reloaded.IS_SQLITE is True
        assert reloaded.engine.url.database == database.as_posix()
        assert reloaded.engine.pool.size() == 20
        assert reloaded.engine.pool._max_overflow == 40

        with reloaded.engine.connect() as connection:
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
            assert connection.exec_driver_sql("PRAGMA journal_mode").scalar() == "wal"
            assert connection.exec_driver_sql("PRAGMA busy_timeout").scalar() == 30000
    finally:
        if original_ts is None:
            os.environ.pop("TS_DB_URL", None)
        else:
            os.environ["TS_DB_URL"] = original_ts
        if original_db is None:
            os.environ.pop("DB_URL", None)
        else:
            os.environ["DB_URL"] = original_db
        importlib.reload(session_module)
