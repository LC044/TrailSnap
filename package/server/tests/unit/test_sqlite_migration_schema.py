"""Regression coverage for the frozen SQLite Alembic branch."""

from pathlib import Path

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import create_engine, inspect, text

import app.db.models  # noqa: F401
from app.db.base import Base


pytestmark = [pytest.mark.smoke, pytest.mark.module_system]
SERVER_ROOT = Path(__file__).parents[2]


def _config(database_url: str) -> Config:
    config = Config()
    config.set_main_option("script_location", str(SERVER_ROOT / "alembic_sqlite"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def test_frozen_sqlite_migrations_match_current_metadata(tmp_path, monkeypatch):
    database_url = f"sqlite:///{(tmp_path / 'schema.sqlite').as_posix()}"
    monkeypatch.setenv("TS_DB_URL", database_url)
    config = _config(database_url)

    command.upgrade(config, "head")
    # A second startup must be a no-op rather than replaying data migrations.
    command.upgrade(config, "head")

    engine = create_engine(database_url)
    try:
        schema = inspect(engine)
        actual_tables = set(schema.get_table_names()) - {"alembic_version"}
        expected_tables = set(Base.metadata.tables)
        assert actual_tables == expected_tables

        for table_name, table in Base.metadata.tables.items():
            actual_columns = {column["name"] for column in schema.get_columns(table_name)}
            assert actual_columns == set(table.columns.keys()), table_name

            actual_indexes = {index["name"] for index in schema.get_indexes(table_name)}
            expected_indexes = {index.name for index in table.indexes}
            assert actual_indexes == expected_indexes, table_name

        with engine.connect() as connection:
            assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "sqlite_0002"
    finally:
        engine.dispose()
