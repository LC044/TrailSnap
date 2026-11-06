"""Old-schema upgrade and cluster behavior on isolated database copies."""
import os
from pathlib import Path
from uuid import uuid4
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text, inspect, insert
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from app.db.models.face import Face, FaceIdentity, FaceCluster
from app.db.models.photo import Photo, FileType
from app.db.models.user import User
from app.db.models.task import Task
from app.service import face_appearance_clusters as clusters

pytestmark = [pytest.mark.smoke, pytest.mark.module_face]
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(params=["sqlite", "postgresql"])
def legacy_database(request, tmp_path, monkeypatch):
    dialect = request.param
    admin = None
    name = None
    if dialect == "postgresql":
        if os.getenv("TS_FACE_TEST_POSTGRES") != "1":
            pytest.skip("Enable TS_FACE_TEST_POSTGRES for isolated PostgreSQL checks")
        url = make_url(os.environ["TS_DB_URL"])
        name = "trailsnap_face_test_" + uuid4().hex[:16]
        admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
        with admin.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{name}"'))
        url = url.set(database=name).render_as_string(hide_password=False)
        folder, previous = "alembic", "face_lists_pg_0022"
    else:
        url = f"sqlite:///{(tmp_path / 'legacy.sqlite').as_posix()}"
        folder, previous = "alembic_sqlite", "face_lists_sqlite_0022"
    monkeypatch.setenv("TS_DB_URL", url)
    config = Config()
    config.set_main_option("script_location", str(ROOT / folder))
    config.set_main_option("sqlalchemy.url", url)
    engine = create_engine(url)
    try:
        if dialect == "postgresql":
            with engine.begin() as connection:
                connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        command.upgrade(config, previous)
        yield engine, config, previous
    finally:
        engine.dispose()
        if admin is not None:
            with admin.connect() as connection:
                connection.execute(text("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=:name AND pid<>pg_backend_pid()"), {"name": name})
                connection.execute(text(f'DROP DATABASE "{name}"'))
            admin.dispose()


def test_upgrade_preserves_legacy_people_and_supports_rebuild(legacy_database):
    engine, config, previous = legacy_database
    owner, photo, identity = uuid4(), uuid4(), uuid4()
    dialect = engine.dialect.name
    def portable(value):
        return str(value) if dialect == "sqlite" else value
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO users(id,username,hashed_password) VALUES (:id,'legacy-face','hash')"), {"id": portable(owner)})
        connection.execute(text("INSERT INTO photos(id,owner_id,filename,file_path,file_type,is_deleted) VALUES (:id,:owner,'legacy.jpg','/legacy.jpg','image',false)"), {"id": portable(photo), "owner": portable(owner)})
        connection.execute(text("INSERT INTO face_identities(id,owner_id,identity_name,is_deleted,is_hidden) VALUES (:id,:owner,'孩子',false,false)"), {"id": portable(identity), "owner": portable(owner)})
        connection.execute(text("INSERT INTO faces(photo_id,face_identity_id,is_deleted) VALUES (:photo,:person,false)"), {"photo": portable(photo), "person": portable(identity)})
    command.upgrade(config, "head")
    command.upgrade(config, "head")
    assert "face_clusters" in inspect(engine).get_table_names()
    with Session(engine, autoflush=False) as db:
        queued = db.query(Task).filter(Task.type == "CLUSTER_FACES", Task.owner_id == owner).one()
        assert queued.status == "pending" and queued.payload == {"owner_id": str(owner), "auto": False}
        person = db.get(FaceIdentity, identity)
        face = db.query(Face).one()
        assert person.identity_name == "孩子"
        assert face.face_identity_id == identity and face.face_cluster_id is None
        face.face_feature = [1.0] + [0.0] * 511
        db.commit()
        clusters.process_faces(db, owner)
        db.refresh(face)
        assert face.face_identity_id == identity
        assert db.get(FaceCluster, face.face_cluster_id).identity_id == identity
        assert person.identity_name == "孩子"
        clusters.request_reset(db, owner)
        clusters.process_faces(db, owner)
        db.expire_all()
        assert db.get(FaceIdentity, identity).is_deleted
        assert db.get(Face, face.id).face_feature[0] == 1
    command.downgrade(config, previous)
    assert "face_clusters" not in inspect(engine).get_table_names()
    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM faces")).scalar_one() == 1


def test_upgrade_initialization_tasks_are_durable_and_not_duplicated(legacy_database):
    engine, config, _ = legacy_database
    owners = [uuid4() for _ in range(6)]
    photos = [uuid4() for _ in range(6)]
    pending_id, processing_id = uuid4(), uuid4()
    with engine.begin() as connection:
        connection.execute(insert(User.__table__), [
            {"id": owner, "username": f"owner-{i}", "hashed_password": "unused"}
            for i, owner in enumerate(owners)
        ])
        connection.execute(insert(Photo.__table__), [
            {"id": photo, "owner_id": owner, "filename": f"{i}.jpg", "file_path": f"/{i}.jpg",
             "file_type": FileType.image, "is_deleted": i == 5}
            for i, (owner, photo) in enumerate(zip(owners, photos))
        ])
        connection.execute(insert(Face.__table__), [
            {"photo_id": photo, "is_deleted": i == 4}
            for i, photo in enumerate(photos) if i != 3
        ])
        connection.execute(insert(Task.__table__), [
            {"id": pending_id, "owner_id": owners[0], "type": "CLUSTER_FACES", "status": "pending",
             "payload": {"auto": True, "custom": "preserved", "reset": False}},
            {"id": processing_id, "owner_id": owners[2], "type": "CLUSTER_FACES", "status": "processing",
             "payload": {"auto": True}},
        ])
    command.upgrade(config, "head")
    command.upgrade(config, "head")
    with Session(engine) as db:
        pending = db.query(Task).filter(Task.type == "CLUSTER_FACES", Task.status == "pending").all()
        assert {task.owner_id for task in pending} == set(owners[:3])
        assert len(pending) == 3
        reused = db.get(Task, pending_id)
        assert reused.payload == {"owner_id":str(owners[0]), "auto":False, "custom":"preserved", "reset":False}
        assert db.get(Task, processing_id).payload == {"auto":True}
        for task in pending:
            assert task.payload["auto"] is False
            assert task.payload["owner_id"] == str(task.owner_id)
            assert task.created_at is not None
            assert task.attempt_count == 0
    # Completing/deleting persisted work must not cause a later upgrade to enqueue it again.
    with engine.begin() as connection:
        connection.execute(Task.__table__.delete())
    command.upgrade(config, "head")
    with Session(engine) as db:
        assert db.query(Task).count() == 0
    assert "schedule_initialization" not in (ROOT / "main.py").read_text(encoding="utf-8")
