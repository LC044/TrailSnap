"""Run only the new migration on isolated SQLite or offline PostgreSQL."""
import importlib.util
from io import StringIO
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect

from app.db.base import Base
from app.db.models.toolbox import ToolboxPlan, ToolboxPlanItem

pytestmark = [pytest.mark.smoke, pytest.mark.module_toolbox]
ROOT = Path(__file__).resolve().parents[2]


def migration(folder, filename):
    spec = importlib.util.spec_from_file_location("toolbox_migration", ROOT / folder / "versions" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_sqlite_migration_matches_models_and_downgrades():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        Base.metadata.create_all(connection, tables=[
            table for table in Base.metadata.sorted_tables
            if table.name not in {"toolbox_plans", "toolbox_plan_items"}
        ])
        module = migration("alembic_sqlite", "toolbox_sqlite_0024_toolbox_preview_plans.py")
        module.op = Operations(MigrationContext.configure(connection))
        module.upgrade()
        inspector = inspect(connection)
        for model in (ToolboxPlan, ToolboxPlanItem):
            actual = {column["name"] for column in inspector.get_columns(model.__tablename__)}
            assert actual == set(model.__table__.columns.keys())
            actual_indexes = {index["name"] for index in inspector.get_indexes(model.__tablename__)}
            assert actual_indexes == {index.name for index in model.__table__.indexes}
        module.downgrade()
        assert "toolbox_plans" not in inspect(connection).get_table_names()
    engine.dispose()


def test_postgresql_migration_compiles_without_database_access():
    output = StringIO()
    context = MigrationContext.configure(dialect_name="postgresql", opts={"as_sql": True, "output_buffer": output})
    module = migration("alembic", "toolbox_pg_0024_toolbox_preview_plans.py")
    module.op = Operations(context)
    module.upgrade()
    sql = output.getvalue()
    assert "CREATE TABLE toolbox_plans" in sql
    assert "CREATE TABLE toolbox_plan_items" in sql
    assert "UUID" in sql
    assert "ix_toolbox_items_plan_status" in sql
