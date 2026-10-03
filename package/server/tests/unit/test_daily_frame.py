"""Daily-frame persistence, isolation, immutable jobs and real encoder checks."""
import json
import subprocess
import importlib.util
from io import StringIO, BytesIO
from datetime import date, datetime
from uuid import uuid4

import pytest
from fastapi import HTTPException
from jose import JWTError, jwt
from PIL import Image
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request
from pathlib import Path

from app.db.models.user import User
from app.db.models.photo import Photo, FileType
from app.db.models.daily_frame import DailyFrameWork
from app.db.models.task import Task
from app.schemas.daily_frame import CalendarSettings, FrameSelection, FilmSettings, FilmCreate
from app.service import daily_frame as service
from app.service import daily_frame_render as render

pytestmark = [pytest.mark.smoke, pytest.mark.module_album]


def seed(db, tmp_path, name="daily-owner", day=date(2022, 1, 2)):
    owner = User(id=uuid4(), username=name, hashed_password="x", is_active=True)
    db.add(owner)
    db.commit()
    service.initialize(db, owner.id, CalendarSettings(timezone="Asia/Shanghai"))
    path = tmp_path / f"{name}.jpg"
    Image.new("RGB", (160, 100), "red").save(path)
    photo = Photo(id=uuid4(), owner_id=owner.id, filename=path.name, file_path=str(path),
                  file_type=FileType.image, photo_time=datetime.combine(day, datetime.min.time()), is_deleted=False)
    db.add(photo)
    db.commit()
    return owner, photo


def test_selection_conflicts_undo_and_owner_isolation(face_sqlite_session, tmp_path):
    db = face_sqlite_session
    owner, photo = seed(db, tmp_path)
    stranger, _ = seed(db, tmp_path, "daily-stranger")
    day = date(2022, 1, 2)
    with pytest.raises(HTTPException) as exc:
        service.save(db, stranger.id, day, FrameSelection(photo_id=photo.id))
    assert exc.value.status_code == 404
    db.rollback()
    saved = service.save(db, owner.id, day, FrameSelection(photo_id=photo.id, caption="今天\n很好"))
    assert saved["version"] == 1 and saved["caption"] == "今天 很好"
    assert service.calendar_range(db, owner.id, day, day)["days"][0]["candidate_count"] == 1
    assert service.calendar_range(db, stranger.id, day, day)["days"][0]["frame"] is None
    with pytest.raises(HTTPException) as exc:
        service.save(db, owner.id, day, FrameSelection(photo_id=photo.id))
    assert exc.value.status_code == 409
    db.rollback()
    with pytest.raises(HTTPException):
        service.initialize(db, owner.id, CalendarSettings(timezone="UTC"))
    db.rollback()
    assert service.remove(db, owner.id, day, 1)["version"] == 2
    assert service.undo_remove(db, owner.id, day, 2)["version"] == 3
    photo.photo_time = datetime(2022, 1, 3)
    db.commit()
    assert service.frame(db, owner.id, day)["date_changed"]
    assert service.save(db, owner.id, day, FrameSelection(photo_id=photo.id, version=3))["version"] == 4


def test_fill_preserves_selected_invalid_and_rechecks_conflicts(face_sqlite_session, tmp_path):
    db = face_sqlite_session
    owner, photo = seed(db, tmp_path)
    day = date(2022, 1, 2)
    suggestion = service.suggestions(db, owner.id, date(2022, 1, 1), date(2022, 1, 31))["items"][0]
    assert suggestion["photo_id"] == str(photo.id)
    service.save(db, owner.id, day, FrameSelection(photo_id=photo.id))
    with pytest.raises(HTTPException) as exc:
        service.save(db, owner.id, day, FrameSelection(photo_id=photo.id), only_empty=True)
    assert exc.value.status_code == 409
    db.rollback()
    photo.is_deleted = True
    db.commit()
    assert not service.frame(db, owner.id, day)["available"]
    assert service.frame(db, owner.id, day)["photo_id"] is None
    assert service.suggestions(db, owner.id, day, day)["preserved"] == 1
    plan = service.composition(db, owner.id, FilmSettings(start_date=day, end_date=day))
    assert plan["duration"] == 0 and len(plan["invalid"]) == 1


def test_jobs_deduplicate_snapshot_cancel_and_retry(face_sqlite_session, tmp_path, monkeypatch):
    from app.service.task_manager import TaskManager
    monkeypatch.setattr(TaskManager, "start_worker_if_needed", lambda self: None)
    monkeypatch.setattr(render, "capabilities", lambda: {"available": True, "reason": None})
    db = face_sqlite_session
    owner, photo = seed(db, tmp_path)
    day = date(2022, 1, 2)
    service.save(db, owner.id, day, FrameSelection(photo_id=photo.id))
    settings = FilmSettings(start_date=day, end_date=day)
    plan = service.composition(db, owner.id, settings)
    payload = FilmCreate(**settings.model_dump(), fingerprint=plan["fingerprint"])
    work = service.create_work(db, owner.id, payload)
    assert service.create_work(db, owner.id, payload).id == work.id
    assert db.query(Task).filter_by(owner_id=owner.id).count() == 1
    snapshot = json.dumps(work.snapshot)
    service.save(db, owner.id, day, FrameSelection(photo_id=photo.id, caption="变化", version=1))
    assert json.dumps(work.snapshot) == snapshot
    with pytest.raises(HTTPException) as exc:
        service.create_work(db, owner.id, payload)
    assert exc.value.status_code == 409
    db.rollback()
    service.stop_work(db, owner.id, work.id)
    assert service.serialize_work(db, work)["status"] == "cancelled"
    assert service.retry_work(db, owner.id, work.id).generation == 2
    service.stop_work(db, owner.id, work.id, delete=True)
    with pytest.raises(HTTPException):
        service.owned_work(db, owner.id, work.id)


def test_media_ticket_cannot_be_used_as_login_or_other_asset(face_sqlite_session, tmp_path):
    from app.api.daily_frame import media_ticket, media_user
    from app.core.system_config import system_config
    db = face_sqlite_session
    owner, photo = seed(db, tmp_path)
    path = f"/daily-frame/assets/{photo.id}"
    def request(url):
        return Request({"type": "http", "method": "GET", "path": url, "headers": [],
                        "query_string": b"mode=motion", "scheme": "http", "server": ("localhost", 80)})
    ticket = media_ticket(owner, request(path + "/access"), "motion")["token"]
    assert media_user(request(path + "/file"), ticket, None, db).id == owner.id
    with pytest.raises(HTTPException):
        media_user(request("/daily-frame/assets/other/file"), ticket, None, db)
    security = system_config.config.security
    with pytest.raises(JWTError):
        jwt.decode(ticket, security.secret_key, algorithms=[security.algorithm])


def test_api_envelopes_and_scoped_source_access(face_sqlite_session, tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.daily_frame import router
    from app.api.deps import get_current_user
    from app.dependencies import get_db
    db = face_sqlite_session
    owner, photo = seed(db, tmp_path)
    app = FastAPI(root_path="/api")
    app.include_router(router, prefix="/daily-frame")
    app.dependency_overrides[get_current_user] = lambda: owner
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as client:
        invalid = client.get("/daily-frame/calendar?start=invalid&end=2022-01-02")
        assert invalid.status_code == 422 and invalid.json()["code"] == 422
        saved = client.put("/daily-frame/days/2022-01-02", json={"photo_id": str(photo.id)})
        assert saved.status_code == 200 and saved.json()["data"]["version"] == 1
        stale = client.put("/daily-frame/days/2022-01-02", json={"photo_id": str(photo.id)})
        assert stale.status_code == 409 and stale.json()["code"] == 409
        extra = client.put("/daily-frame/days/2022-01-02", json={"photo_id": str(photo.id), "photo": {}})
        assert extra.status_code == 422
        ticket = client.get(f"/daily-frame/assets/{photo.id}/access?mode=still").json()["data"]["token"]
        response = client.get(f"/daily-frame/assets/{photo.id}/file?mode=still&token={ticket}")
        assert response.status_code == 200 and response.headers["content-type"] == "image/jpeg"
        assert client.get(f"/daily-frame/assets/{photo.id}/file?mode=motion&token={ticket}").status_code == 401


def test_real_render_short_video_and_still_have_exactly_one_second(tmp_path):
    if not render.capabilities()["available"]:
        pytest.skip("Optional FFmpeg and Chinese font are unavailable")
    settings = FilmSettings(start_date=date(2022, 1, 2), end_date=date(2022, 1, 2)).model_dump(mode="json")
    image = tmp_path / "source.jpg"
    Image.new("RGB", (120, 80), "red").save(image)
    short = tmp_path / "short.mp4"
    subprocess.run([render.ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
                    "-i", "color=c=blue:s=120x80:r=30:d=0.4", "-an", "-c:v", "libx264", str(short)],
                   check=True, timeout=30, **render.process_options())
    for index, (mode, source) in enumerate([("still", image), ("motion", short)]):
        result = render.encode_segment(str(source), {"mode": mode, "start_seconds": 0, "day": "2022-01-02", "caption": "今天很好"},
                                       settings, tmp_path, index, True, lambda: None)
        info = json.loads(subprocess.check_output([render.ffprobe_path(), "-v", "error", "-show_streams", "-of", "json", str(result)], **render.process_options()))
        assert len(info["streams"]) == 1
        video = info["streams"][0]
        assert (video["width"], video["height"]) == (360, 640)
        assert int(video["nb_frames"]) == 30
        assert float(video["duration"]) == pytest.approx(1)
    changing = tmp_path / "changing.mp4"
    subprocess.run([render.ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                    "color=c=red:s=120x80:r=30:d=1", "-f", "lavfi", "-i", "color=c=blue:s=120x80:r=30:d=2",
                    "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[out]", "-map", "[out]", "-c:v", "libx264", str(changing)],
                   check=True, timeout=30, **render.process_options())
    result = render.encode_segment(str(changing), {"mode": "motion", "start_seconds": 1.2, "day": "2022-01-02", "caption": ""},
                                   settings, tmp_path, 2, True, lambda: None)
    frame = subprocess.check_output([render.ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-i", str(result),
                                     "-frames:v", "1", "-f", "image2pipe", "-c:v", "png", "-"], timeout=30, **render.process_options())
    with Image.open(BytesIO(frame)) as decoded:
        red, green, blue = decoded.convert("RGB").getpixel((180, 300))
        assert blue > 200 and red < 30 and green < 30


def test_deleted_source_fails_durably_with_date_and_rejects_retry(face_sqlite_session, tmp_path, monkeypatch):
    from app.db import session
    from app.service.task_manager import TaskManager
    monkeypatch.setattr(TaskManager, "start_worker_if_needed", lambda self: None)
    monkeypatch.setattr(render, "capabilities", lambda: {"available": True, "reason": None})
    db = face_sqlite_session
    monkeypatch.setattr(session, "SessionLocal", sessionmaker(bind=db.get_bind(), autoflush=False))
    monkeypatch.setattr(render, "DATA_DIR", str(tmp_path))
    owner, photo = seed(db, tmp_path)
    day = date(2022, 1, 2)
    service.save(db, owner.id, day, FrameSelection(photo_id=photo.id))
    settings = FilmSettings(start_date=day, end_date=day)
    plan = service.composition(db, owner.id, settings)
    work = service.create_work(db, owner.id, FilmCreate(**settings.model_dump(), fingerprint=plan["fingerprint"]))
    photo.is_deleted = True
    db.commit()
    with pytest.raises(RuntimeError, match="2022-01-02"):
        render.render_work(work.id, work.generation, work.task_id)
    db.expire_all()
    assert work.status == "failed" and "2022-01-02" in work.error
    assert not list(render.output_root(owner.id).iterdir())
    with pytest.raises(HTTPException) as exc:
        service.retry_work(db, owner.id, work.id)
    assert exc.value.status_code == 400


def test_persistent_render_publishes_silent_1080p_snapshot_and_deletes_only_work(face_sqlite_session, tmp_path, monkeypatch):
    if not render.capabilities()["available"]:
        pytest.skip("Optional FFmpeg and Chinese font are unavailable")
    from app.db import session
    from app.service.task_manager import TaskManager
    monkeypatch.setattr(TaskManager, "start_worker_if_needed", lambda self: None)
    db = face_sqlite_session
    monkeypatch.setattr(session, "SessionLocal", sessionmaker(bind=db.get_bind(), autoflush=False))
    monkeypatch.setattr(render, "DATA_DIR", str(tmp_path))
    owner, photo = seed(db, tmp_path)
    day = date(2022, 1, 2)
    service.save(db, owner.id, day, FrameSelection(photo_id=photo.id, caption="原来的文字"))
    settings = FilmSettings(start_date=day, end_date=day, orientation="landscape", fit="cover")
    plan = service.composition(db, owner.id, settings)
    work = service.create_work(db, owner.id, FilmCreate(**settings.model_dump(), fingerprint=plan["fingerprint"]))
    service.save(db, owner.id, day, FrameSelection(photo_id=photo.id, version=1, caption="后来的文字"))
    render.render_work(work.id, work.generation, work.task_id)
    db.expire_all()
    assert work.status == "ready" and work.processed_items == 1
    assert work.snapshot["frames"][0]["caption"] == "原来的文字"
    assert service.serialize_work(db, work)["calendar_changed"]
    output = Path(work.output_path)
    info = json.loads(subprocess.check_output([render.ffprobe_path(), "-v", "error", "-show_streams", "-of", "json", str(output)], **render.process_options()))
    assert len(info["streams"]) == 1
    assert (info["streams"][0]["width"], info["streams"][0]["height"]) == (1920, 1080)
    assert int(info["streams"][0]["nb_frames"]) == 30
    service.stop_work(db, owner.id, work.id, delete=True)
    assert not output.exists() and Path(photo.file_path).exists()
    assert service.frame(db, owner.id, day)["available"]
    with pytest.raises(render.RenderCancelled):
        render.render_work(work.id, work.generation, work.task_id)


@pytest.mark.parametrize("migration", ["alembic/versions/d1f139000001_add_daily_frames.py", "alembic_sqlite/versions/sqlite_0017_add_daily_frames.py"])
def test_both_migrations_upgrade_downgrade_and_postgres_sql(tmp_path, migration):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import create_engine, inspect
    import app.db.models
    from app.db.base import Base
    spec = importlib.util.spec_from_file_location("daily_frame_migration", Path(__file__).parents[2] / migration)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    names = {"daily_frames", "daily_frame_works", "daily_frame_calendars"}
    engine = create_engine(f"sqlite:///{(tmp_path / 'migration.sqlite').as_posix()}")
    try:
        Base.metadata.create_all(engine, tables=[table for table in Base.metadata.sorted_tables if table.name not in names])
        with engine.begin() as connection:
            with Operations.context(MigrationContext.configure(connection)):
                module.upgrade()
                assert names <= set(inspect(connection).get_table_names())
                assert inspect(connection).get_unique_constraints("daily_frames")[0]["column_names"] == ["owner_id", "day"]
                module.downgrade()
                assert not names.intersection(inspect(connection).get_table_names())
        buffer = StringIO()
        with Operations.context(MigrationContext.configure(dialect_name="postgresql", opts={"as_sql": True, "output_buffer": buffer})):
            module.upgrade()
        assert "BOOLEAN DEFAULT false" in buffer.getvalue()
        assert "ON DELETE SET NULL" in buffer.getvalue()
    finally:
        engine.dispose()
