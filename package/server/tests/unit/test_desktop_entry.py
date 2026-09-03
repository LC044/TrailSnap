"""Fast-path checks for the frozen desktop sidecar bootstrap."""

import sqlite3

from fastapi import FastAPI
from fastapi.testclient import TestClient

import desktop_entry


def test_database_is_current_for_bundled_schema(tmp_path):
    database = tmp_path / "trailsnap.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        connection.execute(
            "INSERT INTO alembic_version(version_num) VALUES (?)",
            (desktop_entry.DESKTOP_SCHEMA_REVISION,),
        )

    assert desktop_entry._database_is_current(database) is True


def test_database_is_current_rejects_missing_or_old_schema(tmp_path):
    assert desktop_entry._database_is_current(tmp_path / "missing.sqlite") is False

    database = tmp_path / "old.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        connection.execute("INSERT INTO alembic_version(version_num) VALUES ('sqlite_0004')")

    assert desktop_entry._database_is_current(database) is False


def test_desktop_sidecar_accepts_frontend_api_prefix():
    app = FastAPI()

    @app.get("/health-check")
    def health_check():
        return {"status": "ok"}

    desktop_entry._apply_desktop_api_prefix(app)
    client = TestClient(app)

    assert client.get("/api/health-check").status_code == 200
    assert client.get("/health-check").status_code == 200
