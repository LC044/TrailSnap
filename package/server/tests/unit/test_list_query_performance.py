"""List responses stay independent of media availability and background backlog."""
from datetime import datetime
import importlib.util
import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import Session

import app.db.models  # noqa: F401
from app.crud.photo import get_photos_by_time
from app.crud.task import get_grouped_status
from app.db.base import Base
from app.db.models.photo import FileType, Photo
from app.db.models.task import Task, TaskType
from app.schemas.album import Album
from app.schemas.face import FaceIdentitySchema
from app.schemas.location import Location
from app.schemas.metadata import PhotoDetail
from app.schemas.photo import Photo as PhotoResponse, PhotoGroup, RecyclePhoto
from app.schemas.tag import TagStats
from app.service.ai_model_state import WAIT_PREFIX
from app.service import storage_paths

pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


@pytest.mark.parametrize("kind", ["photo", "group", "album", "people", "location", "tag", "detail", "recycle"])
def test_list_and_cover_responses_never_resolve_media_paths(monkeypatch, kind):
    def unexpected_io(*args, **kwargs):
        raise AssertionError("List validation must not resolve media paths")

    monkeypatch.setattr(storage_paths, "resolve_path", unexpected_io)
    photo = Photo(id=uuid4(), owner_id=uuid4(), filename="offline.jpg", size=42,
                  file_type=FileType.image, duration=0, is_deleted=False,
                  storage_root_id=uuid4(), storage_relative_path="offline.jpg")
    if kind == "photo":
        response = PhotoResponse.model_validate(photo)
    elif kind == "group":
        response = PhotoGroup(date="2026-10-20", items=[photo])
    elif kind == "album":
        response = Album(id=uuid4(), name="album", create_time=datetime.now(), cover=photo)
    elif kind == "people":
        response = FaceIdentitySchema(id=uuid4(), cover=photo)
    elif kind == "location":
        response = Location(name="city", level="city", count=1, cover=photo)
    elif kind == "tag":
        response = TagStats(id=uuid4(), tag_name="tag", count=1, cover=photo)
    elif kind == "detail":
        response = PhotoDetail.model_validate(photo)
    else:
        response = RecyclePhoto.model_validate(photo)
    payload = response.model_dump(mode="json")
    item = payload["items"][0] if kind == "group" else payload.get("cover", payload)
    assert item["id"] == str(photo.id)
    assert item["filename"] == "offline.jpg"
    assert "file_path" not in item
    assert "upload_time" not in item
    # Actual file access still passes through the checked filesystem boundary.
    with pytest.raises(AssertionError, match="must not resolve"):
        _ = photo.file_path


def test_grouped_status_counts_waits_and_uses_bounded_index_reads():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        rows = [Task(type=TaskType.OCR, status="pending", error=None, payload={}) for _ in range(500)]
        rows += [Task(type=TaskType.OCR, status=status, error=error, payload={})
                 for status, error in [("processing", None), ("failed", "failure"),
                                       ("pending", WAIT_PREFIX + "B"), ("pending", WAIT_PREFIX + "A"),
                                       ("pending", "ordinary error"), ("completed", WAIT_PREFIX + "0"),
                                       ("cancelled", None)]]
        rows.append(Task(type=TaskType.SCAN_FOLDER, status="pending", payload={}))
        db.add_all(rows)
        db.commit()
        # Like the migration, give the planner the actual backlog distribution.
        db.connection().exec_driver_sql('ANALYZE ix_tasks_type_status')
        db.connection().exec_driver_sql('ANALYZE ix_tasks_pending_error_type')
        statements = []

        def capture(conn, cursor, statement, parameters, context, executemany):
            statements.append((statement, parameters))

        event.listen(engine, "before_cursor_execute", capture)
        try:
            groups = get_grouped_status(db, {TaskType.OCR})
        finally:
            event.remove(engine, "before_cursor_execute", capture)
        group = next(row for row in groups if row["category"] == TaskType.OCR)
        assert group["pending"] == 504
        assert group["failed"] == 1
        assert group["completed"] == 0
        assert group["status"] == "paused"
        assert group["waiting_reason"] == WAIT_PREFIX + "A"
        assert len(groups) == 10
        assert all(row["category"] != TaskType.SCAN_FOLDER for row in groups)
        assert [row["priority"] for row in groups] == sorted((row["priority"] for row in groups), reverse=True)
        assert len(statements) == 2
        plans = [" ".join(row[3] for row in db.connection().exec_driver_sql(
            "EXPLAIN QUERY PLAN " + sql, args)) for sql, args in statements]
        assert "COVERING INDEX ix_tasks_type_status" in plans[0]
        assert "ix_tasks_pending_error_type" in plans[1]
    engine.dispose()


def test_photo_pagination_keeps_owner_deletion_dates_and_index_order():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    owner = uuid4()
    with Session(engine) as db:
        expected = []
        for day, photo_owner, deleted in [(1, owner, False), (2, owner, False), (3, owner, False),
                                           (4, owner, True), (5, uuid4(), False)]:
            photo = Photo(id=uuid4(), owner_id=photo_owner, file_path="offline.jpg", size=1,
                          file_type=FileType.image, photo_time=datetime(2026, 10, day), is_deleted=deleted)
            db.add(photo)
            if photo_owner == owner and not deleted:
                expected.append(photo.id)
        db.commit()
        assert [p.id for p in get_photos_by_time(db, owner, skip=1, limit=1)] == [expected[1]]
        assert [p.id for p in get_photos_by_time(db, owner, limit=0, start_time=datetime(2026, 10, 2))] == expected[:0:-1]
        statement = db.query(Photo).filter(Photo.owner_id == owner, Photo.is_deleted == False).order_by(Photo.photo_time.desc()).limit(100).statement
        compiled = statement.compile(engine, compile_kwargs={"literal_binds": True})
        plan = " ".join(row[3] for row in db.connection().exec_driver_sql("EXPLAIN QUERY PLAN " + str(compiled)))
        assert "ix_photos_owner_deleted_time_id" in plan
        assert "TEMP B-TREE" not in plan
    engine.dispose()


def test_list_index_migration_upgrades_and_downgrades_existing_sqlite(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'lists.sqlite').as_posix()}"
    monkeypatch.setenv("TS_DB_URL", url)
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parents[2] / "alembic_sqlite"))
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "portable_sqlite_0020")
    engine = create_engine(url)
    names = {"photos": "ix_photos_owner_deleted_time_id", "tasks": "ix_tasks_pending_error_type",
             "photo_metadata": "ix_photo_metadata_location_summary"}
    try:
        for revision, present in [("head", True), ("portable_sqlite_0020", False), ("head", True)]:
            if present:
                command.upgrade(config, revision)
            else:
                command.downgrade(config, revision)
            for table, name in names.items():
                assert (name in {index["name"] for index in inspect(engine).get_indexes(table)}) is present
    finally:
        engine.dispose()


@pytest.mark.postgres
def test_list_index_postgres_migration_in_rolled_back_schema(request):
    if "postgres" not in request.config.getoption("markexpr"):
        pytest.skip("Select postgres explicitly to use the configured test server")
    url = os.environ.get("TS_DB_URL") or os.environ.get("DB_URL", "")
    if not url.startswith("postgresql"):
        pytest.skip("A PostgreSQL test server is required")
    path = Path(__file__).parents[2] / "alembic/versions/3b51634972a4_cover_location_summary_queries.py"
    spec = importlib.util.spec_from_file_location("list_index_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine(url, connect_args={"connect_timeout": 5})
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                schema = "list_index_test_" + uuid4().hex
                connection.execute(text(f'CREATE SCHEMA "{schema}"'))
                connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
                connection.exec_driver_sql("CREATE TABLE photos (id uuid PRIMARY KEY, owner_id uuid, is_deleted boolean, photo_time timestamp)")
                connection.exec_driver_sql("CREATE TABLE tasks (type varchar(50), status varchar(20), error text)")
                connection.exec_driver_sql("CREATE TABLE photo_metadata (photo_id uuid, province text, city text, district text, country text, scene_id uuid, latitude numeric, longitude numeric)")
                # Arbitrarily large ordinary error text must stay out of index keys.
                connection.execute(text("INSERT INTO tasks VALUES ('OCR','pending',:error)"), {"error": "x" * 20000})
                with Operations.context(MigrationContext.configure(connection)):
                    migration.upgrade()
                    indexes = inspect(connection).get_indexes("tasks", schema=schema)
                    pending = next(row for row in indexes if row["name"] == "ix_tasks_pending_error_type")
                    assert pending["column_names"] == ["type", "status"]
                    assert "error IS NOT NULL" in pending["dialect_options"]["postgresql_where"]
                    assert "ix_photos_owner_deleted_time_id" in {row["name"] for row in inspect(connection).get_indexes("photos", schema=schema)}
                    migration.downgrade()
                    assert not inspect(connection).get_indexes("tasks", schema=schema)
                    assert connection.exec_driver_sql("SELECT length(error) FROM tasks").scalar_one() == 20000
            finally:
                transaction.rollback()
    finally:
        engine.dispose()
