"""First-install railway imports must not block or strand onboarding."""
import threading

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from railway import initialization

pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


@pytest.fixture
def seed_environment(tmp_path, monkeypatch):
    from app.core import paths
    from railway import build_database
    from railway.db import session
    from railway.db.models.models import Base, Station

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    monkeypatch.setattr(session, "SessionLocal", sessions)
    monkeypatch.setattr(paths, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(build_database, "source_dir", str(tmp_path))
    monkeypatch.setattr(build_database, "TABLE_MODEL_MAPPING", {"station": Station})
    monkeypatch.setenv("RAILWAY_DB_URL", "sqlite:///:memory:")
    csv = tmp_path / "station.csv"
    csv.write_text(
        "station_id,telecode,station_name,station_pinyin,station_py,city\n"
        "1,AAA,测试站,ceshi,cs,测试市\n", encoding="utf-8"
    )
    yield sessions, Station, csv, build_database
    engine.dispose()


def test_seed_resumes_existing_database_and_preserves_rows(seed_environment):
    sessions, station, csv, importer = seed_environment
    with sessions() as db:
        importer.read_csv_to_db(db, "station", station)
    # Simulate a prior interrupted import without a completion marker.
    with csv.open("a", encoding="utf-8") as file:
        file.write("2,BBB,第二站,dier,de,测试市\n")
    initialization.ensure_seed_data()
    with sessions() as db:
        assert db.query(station).count() == 2
    # A completed import does not read seed files on the next startup.
    csv.unlink()
    initialization.ensure_seed_data()


def test_failed_import_does_not_mark_complete(seed_environment):
    _, _, csv, _ = seed_environment
    csv.unlink()
    with pytest.raises(FileNotFoundError):
        initialization.ensure_seed_data()
    assert not list(csv.parent.glob("*.complete"))


def test_reset_database_discards_stale_completion_marker(seed_environment):
    sessions, station, csv, _ = seed_environment
    initialization.ensure_seed_data()
    with sessions() as db:
        db.query(station).delete()
        db.commit()
    csv.unlink()
    with pytest.raises(FileNotFoundError):
        initialization.ensure_seed_data()
    assert not list(csv.parent.glob("*.complete"))


def test_background_import_returns_before_completion(tmp_path, monkeypatch):
    from app.core import paths
    from railway import start

    entered, release = threading.Event(), threading.Event()
    monkeypatch.setattr(paths, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(initialization, "_state", "pending")
    monkeypatch.setattr(initialization, "_thread", None)

    def slow_import():
        entered.set()
        release.wait(5)

    monkeypatch.setattr(start, "create_database", slow_import)
    initialization.start_background_initialization()
    try:
        assert entered.wait(2)
        with pytest.raises(HTTPException) as error:
            initialization.require_ready()
        assert error.value.status_code == 503
    finally:
        release.set()
        initialization._thread.join(3)
    initialization.require_ready()


def test_failed_background_import_explains_retry(tmp_path, monkeypatch):
    from app.core import paths
    from railway import start

    monkeypatch.setattr(paths, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(initialization, "_state", "pending")
    monkeypatch.setattr(start, "create_database", lambda: (_ for _ in ()).throw(RuntimeError("import failed")))
    initialization._initialize()
    with pytest.raises(HTTPException, match="初始化失败"):
        initialization.require_ready()


def test_railway_api_waits_without_opening_database(monkeypatch):
    from railway.db import dependencies
    monkeypatch.setattr(initialization, "_state", "pending")
    monkeypatch.setattr(dependencies, "SessionLocal", lambda: pytest.fail("database opened before readiness"))
    with pytest.raises(HTTPException) as error:
        next(dependencies.get_ready_db())
    assert error.value.status_code == 503
