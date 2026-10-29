"""List queries avoid EXIF/embedding row reads without changing scope or counts."""
from datetime import datetime
import importlib.util
import os
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.orm import Session
from alembic.migration import MigrationContext
from alembic.operations import Operations

import app.db.models
from app.crud.face import get_identities_with_details, get_group_albums
from app.crud.location import get_location_statistics, get_map_markers, get_location_years, get_locations
from app.db.base import Base
from app.db.models.face import Face, FaceIdentity
from app.db.models.photo import Photo, FileType
from app.db.models.photo_metadata import PhotoMetadata

pytestmark = [pytest.mark.smoke, pytest.mark.module_album]


def test_geography_uses_covering_projection_without_statistics():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    owner, other = uuid4(), uuid4()
    with Session(engine) as db:
        visible = None
        for user, deleted in [(owner, False), (owner, True), (other, False)]:
            photo = Photo(id=uuid4(), owner_id=user, filename="test.jpg", file_path="offline.jpg",
                          file_type=FileType.image, photo_time=datetime(2024, 1, 1), is_deleted=deleted)
            db.add(photo)
            db.add(PhotoMetadata(photo_id=photo.id, city="City", province="Province", country="Country",
                                 latitude=30, longitude=110, exif_info="x" * 16000))
            if user == owner and not deleted:
                visible = photo.id
        db.commit()
        statements = []
        def capture(conn, cursor, sql, params, ctx, many):
            statements.append((sql, params))
        event.listen(engine, "before_cursor_execute", capture)
        try:
            assert [row["id"] for row in get_map_markers(db, owner)] == [str(visible)]
            assert get_location_years(db, owner) == [2024]
            assert get_location_statistics(db, owner)["city_count"] == 1
            assert get_locations(db, owner)[0]["count"] == 1
        finally:
            event.remove(engine, "before_cursor_execute", capture)
        for sql, params in statements:
            plan = " ".join(row[3] for row in db.connection().exec_driver_sql("EXPLAIN QUERY PLAN " + sql, params))
            assert "COVERING INDEX ix_photo_metadata_location_summary" in plan
            assert "exif_info" not in sql
            assert not ("SCAN visible_location_photos" in plan and "SCAN location_metadata_summary" in plan), plan
    engine.dispose()


@pytest.mark.postgres
def test_face_covering_pg_migration_preserves_rows_in_rolled_back_schema(request):
    if "postgres" not in request.config.getoption("markexpr"):
        pytest.skip("Select postgres explicitly to use the test server")
    url = os.environ.get("TS_DB_URL", "")
    if not url.startswith("postgresql"):
        pytest.skip("PostgreSQL test server required")
    path = Path(__file__).parents[2] / "alembic/versions/20261029_face_list_covering.py"
    spec = importlib.util.spec_from_file_location("face_covering_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine(url, connect_args={"connect_timeout": 5})
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                schema = "face_covering_test_" + uuid4().hex
                connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
                connection.exec_driver_sql(f'SET LOCAL search_path TO "{schema}"')
                connection.exec_driver_sql("CREATE TABLE faces (photo_id uuid, face_identity_id uuid)")
                connection.exec_driver_sql("INSERT INTO faces VALUES (gen_random_uuid(), gen_random_uuid())")
                with Operations.context(MigrationContext.configure(connection)):
                    migration.upgrade()
                    indexes = inspect(connection).get_indexes("faces", schema=schema)
                    assert indexes[0]["column_names"] == ["photo_id", "face_identity_id"]
                    migration.downgrade()
                    assert not inspect(connection).get_indexes("faces", schema=schema)
                    assert connection.exec_driver_sql("SELECT count(*) FROM faces").scalar_one() == 1
            finally:
                transaction.rollback()
    finally:
        engine.dispose()


def test_person_count_deduplicates_and_preserves_existing_deleted_face_semantics():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    owner = uuid4()
    with Session(engine) as db:
        person = FaceIdentity(id=uuid4(), owner_id=owner, identity_name="Person")
        photo = Photo(id=uuid4(), owner_id=owner, filename="test.jpg", file_path="offline.jpg",
                      file_type=FileType.image, size=1)
        db.add_all([person, photo]); db.flush()
        cover = Face(photo_id=photo.id, face_identity_id=person.id, face_feature=[0.1] * 512)
        db.add(cover); db.flush(); person.default_face_id = cover.id
        db.add(Face(photo_id=photo.id, face_identity_id=person.id, is_deleted=True))
        db.commit(); db.expunge_all()
        statements = []
        def capture(conn, cursor, sql, params, ctx, many):
            statements.append((sql, params))
        event.listen(engine, "before_cursor_execute", capture)
        try:
            rows = get_identities_with_details(db, owner_id=owner)
            assert get_group_albums(db, owner_id=owner) == []
        finally:
            event.remove(engine, "before_cursor_execute", capture)
        assert len(rows) == 1 and rows[0].face_count == 1
        assert rows[0].cover_photo is not None
        assert not any("face_feature" in sql for sql, _ in statements)
        plan = " ".join(row[3] for row in db.connection().exec_driver_sql(
            "EXPLAIN QUERY PLAN " + statements[0][0], statements[0][1]))
        assert "COVERING INDEX ix_faces_photo_identity" in plan
        group_sql, group_params = statements[-1]
        group_plan = " ".join(row[3] for row in db.connection().exec_driver_sql(
            "EXPLAIN QUERY PLAN " + group_sql, group_params))
        assert "USING INDEX ix_faces_identity_alive" in group_plan or "COVERING INDEX ix_faces_identity_alive" in group_plan
        assert not ("SCAN identity_owner_photos" in group_plan and "SCAN identity_photo_relations" in group_plan)
    engine.dispose()
