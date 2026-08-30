"""Fast-path checks for the frozen desktop sidecar bootstrap."""

import sqlite3

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
