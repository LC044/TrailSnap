"""Regression coverage for the frozen SQLite Alembic branch."""

from pathlib import Path
import json
import uuid

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
import pytest
from sqlalchemy import create_engine, inspect, text

import app.db.models  # noqa: F401
from app.db.base import Base
from app.db.models.task import Task
from sqlalchemy.orm import Session


pytestmark = [pytest.mark.smoke, pytest.mark.module_system]
SERVER_ROOT = Path(__file__).parents[2]


def test_desktop_fast_start_schema_revision_matches_sqlite_head():
    from desktop_entry import DESKTOP_SCHEMA_REVISION

    config = _config("sqlite://")
    assert DESKTOP_SCHEMA_REVISION == ScriptDirectory.from_config(config).get_current_head()


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
            database_revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            assert database_revision == ScriptDirectory.from_config(config).get_current_head()
    finally:
        engine.dispose()


def test_photo_task_migration_cascade_indexes_and_file_reclamation(tmp_path, monkeypatch):
    path = tmp_path / "legacy.sqlite"
    database_url = f"sqlite:///{path.as_posix()}"
    monkeypatch.setenv("TS_DB_URL", database_url)
    config = _config(database_url)
    command.upgrade(config, "de268f1b37fe")
    engine = create_engine(database_url)
    photo_id, orphan_id = uuid.uuid4(), uuid.uuid4()
    valid_task, global_task = str(uuid.uuid4()), str(uuid.uuid4())
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO photos(id,file_path,file_type,is_deleted) VALUES (:id,'test.jpg','image',0)"), {"id": str(photo_id)})
        rows = [{"id": valid_task, "payload": json.dumps({"photo_id": photo_id.hex})},
                {"id": global_task, "payload": json.dumps({"path": "unscanned.jpg"})}]
        rows.extend({"id": str(uuid.uuid4()), "payload": json.dumps({"photo_id": str(orphan_id), "legacy": "x" * 20000})} for _ in range(100))
        connection.execute(text("INSERT INTO tasks(id,type,status,priority,payload) VALUES (:id,'OCR','pending',7,:payload)"), rows)
    before_size = path.stat().st_size
    engine.dispose()
    command.upgrade(config, "head")
    with engine.connect() as connection:
        assert connection.execute(text("PRAGMA auto_vacuum")).scalar_one() == 1
        assert connection.execute(text("PRAGMA freelist_count")).scalar_one() == 0
        assert connection.execute(text("SELECT count(*) FROM tasks")).scalar_one() == 2
        assert connection.execute(text("SELECT photo_id FROM tasks WHERE id=:id"), {"id": valid_task}).scalar_one() == str(photo_id)
        assert connection.execute(text("SELECT photo_id FROM tasks WHERE id=:id"), {"id": global_task}).scalar_one() is None
        assert connection.execute(text("PRAGMA foreign_key_check")).all() == []
        plan = connection.execute(text("EXPLAIN QUERY PLAN SELECT id FROM tasks WHERE type='OCR' AND status='pending' AND (next_retry_at IS NULL OR next_retry_at <= CURRENT_TIMESTAMP) ORDER BY priority DESC,created_at ASC LIMIT 32")).all()
        details = " ".join(row[3] for row in plan)
        assert "ix_tasks_type_status_priority_created" in details
        assert "TEMP B-TREE" not in details
    assert path.stat().st_size < before_size / 2
    with engine.connect() as connection:
        connection.execute(text("PRAGMA foreign_keys=ON"))
        connection.commit()
        with Session(bind=connection) as session:
            linked = [Task(type="OCR", status=status, payload={"photo_id": str(photo_id), "legacy": "x" * 20000})
                      for status in ("pending", "processing", "failed") for _ in range(30)]
            session.bulk_save_objects(linked)
            session.commit()
            assert all(task.photo_id == photo_id for task in linked)
            expanded_size = path.stat().st_size
            session.execute(text("DELETE FROM photos WHERE id=:id"), {"id": str(photo_id)})
            session.commit()
            assert session.query(Task).count() == 1
            assert session.query(Task).one().id == uuid.UUID(global_task)
            assert path.stat().st_size < expanded_size / 2
    engine.dispose()
