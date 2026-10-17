"""Docker's PostgreSQL path: upgrade an isolated historical database in place."""
import os
import uuid
from pathlib import Path
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from alembic import command
from alembic.config import Config

pytestmark = [pytest.mark.module_portable_upgrade]


def test_postgres_additive_upgrade_preserves_docker_paths_and_accounts(monkeypatch):
    raw = os.getenv("TS_DB_URL") or os.getenv("DB_URL")
    if not raw or make_url(raw).get_backend_name() != "postgresql":
        pytest.skip("Configure a PostgreSQL test server in tests/.env.test")
    url = make_url(raw)
    name = "trailsnap_portable_test_" + uuid.uuid4().hex[:16]
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    created = False
    try:
        with admin.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{name}"'))
            created = True
        scratch = url.set(database=name).render_as_string(hide_password=False)
        monkeypatch.setenv("TS_DB_URL", scratch)
        monkeypatch.delenv("TS_DESKTOP", raising=False)
        monkeypatch.delenv("TS_DESKTOP_PORTABLE", raising=False)
        engine = create_engine(scratch)
        try:
            with engine.begin() as connection:
                connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
            config.set_main_option("script_location", str(Path(__file__).resolve().parents[2] / "alembic"))
            command.upgrade(config, "4c8b8ca1eaac")
            owner, photo = uuid.uuid4(), uuid.uuid4()
            path = "/app/data/users/" + str(owner) + "/uploads/旧照片.jpg"
            with engine.begin() as connection:
                connection.execute(text("INSERT INTO users(id,username,email,hashed_password,settings) VALUES (:id,'docker-legacy','legacy@example.com','existing-hash',CAST(:settings AS JSON))"), {"id":owner,"settings":'{"storage":{"photo_storage_path":"/app/data"}}'})
                connection.execute(text("INSERT INTO photos(id,owner_id,file_path,file_type,is_deleted) VALUES (:id,:owner,:path,'image',false)"), {"id":photo,"owner":owner,"path":path})
                before = connection.execute(text("SELECT id,username,hashed_password,settings::text FROM users")).all()
            command.upgrade(config,"head")
            command.upgrade(config,"head")
            with engine.connect() as connection:
                assert connection.execute(text("SELECT id,username,hashed_password,settings::text FROM users")).all() == before
                assert connection.execute(text("SELECT file_path,storage_root_id,storage_relative_path FROM photos")).one() == (path,None,None)
                assert connection.execute(text("SELECT count(*) FROM storage_roots")).scalar() == 0
            from app.db.models.photo import Photo
            with Session(engine) as db:
                assert db.query(Photo.file_path).filter(Photo.file_path==path).scalar() == path
                assert db.get(Photo,photo).file_path == path
                db.get(Photo,photo).file_path = path.replace("旧照片", "renamed")
                db.commit()
                assert db.get(Photo,photo).storage_root_id is None
        finally:
            engine.dispose()
    finally:
        if created:
            with admin.connect() as connection:
                connection.execute(text("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=:name AND pid<>pg_backend_pid()"), {"name":name})
                connection.execute(text(f'DROP DATABASE "{name}"'))
        admin.dispose()
