"""Nightly gap coverage for the desktop SQLite engine configuration."""

import importlib
import os

import pytest

pytestmark = pytest.mark.smoke


def test_sqlite_engine_enables_wal_and_large_pool(monkeypatch, tmp_path):
    original_ts = os.environ.get("TS_DB_URL")
    original_db = os.environ.get("DB_URL")
    database = tmp_path / "trailsnap.sqlite"
    monkeypatch.setenv("TS_DB_URL", f"sqlite:///{database.as_posix()}")
    monkeypatch.delenv("DB_URL", raising=False)

    try:
        session_module = importlib.import_module("app.db.session")
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
        if not original_ts:
            os.environ.pop("TS_DB_URL", None)
        else:
            os.environ["TS_DB_URL"] = original_ts
        if not original_db:
            os.environ.pop("DB_URL", None)
        else:
            os.environ["DB_URL"] = original_db
        if original_ts or original_db:
            importlib.reload(session_module)
