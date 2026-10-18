"""Coverage for daily-frame API endpoints left under-tested by previous nightly passes."""
from datetime import date, datetime
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from app.api.daily_frame import router
from app.api.deps import get_current_user
from app.db.models.photo import FileType, Photo
from app.db.models.user import User
from app.dependencies import get_db
from app.schemas.daily_frame import (
    BatchSelection,
    CalendarSettings,
    FilmSettings,
    FrameSelection,
)
from app.service import daily_frame as service

pytestmark = [pytest.mark.smoke, pytest.mark.module_album]


def _build_client(db, owner):
    app = FastAPI(root_path="/api")
    app.include_router(router, prefix="/daily-frame")
    app.dependency_overrides[get_current_user] = lambda: owner
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def _seed_owner_and_photo(db, tmp_path, *, day=date(2026, 1, 2)):
    owner = User(id=uuid4(), username="daily-api-" + uuid4().hex[:6], hashed_password="x", is_active=True)
    db.add(owner)
    db.commit()
    service.initialize(db, owner.id, CalendarSettings(timezone="Asia/Shanghai"))
    image_path = tmp_path / ("daily_" + owner.id.hex + ".jpg")
    Image.new("RGB", (160, 100), "red").save(image_path)
    photo = Photo(
        id=uuid4(),
        owner_id=owner.id,
        filename=image_path.name,
        file_path=str(image_path),
        file_type=FileType.image,
        photo_time=datetime.combine(day, datetime.min.time()),
        upload_time=datetime.combine(day, datetime.min.time()),
        size=image_path.stat().st_size,
        is_deleted=False,
    )
    db.add(photo)
    db.commit()
    return owner, photo


def test_settings_payload_after_initialize(face_sqlite_session, tmp_path):
    db = face_sqlite_session
    owner, _ = _seed_owner_and_photo(db, tmp_path)
    client = _build_client(db, owner)
    response = client.get("/daily-frame/settings")
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["initialized"] is True
    assert body["timezone"] == "Asia/Shanghai"
    assert body["export"]["available"] in (True, False)


def test_confirm_fill_skips_already_saved_day(face_sqlite_session, tmp_path):
    db = face_sqlite_session
    owner, photo = _seed_owner_and_photo(db, tmp_path)
    client = _build_client(db, owner)
    day = date(2026, 1, 2)
    payload = BatchSelection(day=day, photo_id=photo.id, caption="daily")
    body = {"items": [{**payload.model_dump(mode="json"), "photo_id": str(photo.id)}]}
    first = client.post("/daily-frame/fill", json=body)
    assert first.status_code == 200
    first_items = first.json()["data"]["items"]
    assert first_items[0]["status"] == "saved"
    assert first_items[0]["frame"]["version"] == 1
    second = client.post("/daily-frame/fill", json=body)
    second_items = second.json()["data"]["items"]
    assert second_items[0]["status"] == "skipped"


def test_asset_metadata_unknown_returns_404_and_known_returns_shape(face_sqlite_session, tmp_path):
    db = face_sqlite_session
    owner, photo = _seed_owner_and_photo(db, tmp_path)
    client = _build_client(db, owner)
    missing = client.get("/daily-frame/assets/" + str(uuid4()))
    assert missing.status_code == 404 and missing.json()["code"] == 404
    detail = client.get("/daily-frame/assets/" + str(photo.id))
    assert detail.status_code == 200
    data = detail.json()["data"]
    assert data["id"] == str(photo.id)
    assert data["day"] == "2026-01-02"
    assert data["available"] is True


def test_works_list_isolated_and_crud_returns_404(face_sqlite_session, tmp_path):
    db = face_sqlite_session
    owner, _ = _seed_owner_and_photo(db, tmp_path)
    client = _build_client(db, owner)
    listing = client.get("/daily-frame/works")
    assert listing.status_code == 200
    payload = listing.json()["data"]
    assert payload["total"] == 0 and payload["items"] == []
    missing = client.get("/daily-frame/works/" + str(uuid4()))
    assert missing.status_code == 404
    create = client.post("/daily-frame/works", json={"start_date": "2026-01-02",
                                                      "end_date": "2026-01-02",
                                                      "fingerprint": "x" * 64})
    assert create.status_code == 503
    cancel = client.post("/daily-frame/works/" + str(uuid4()) + "/cancel")
    assert cancel.status_code == 404
    delete = client.delete("/daily-frame/works/" + str(uuid4()))
    assert delete.status_code == 404


def test_composition_returns_snapshot_fingerprint_and_counts(face_sqlite_session, tmp_path, monkeypatch):
    from app.service import daily_frame_render as render
    from app.service.task_manager import TaskManager

    monkeypatch.setattr(TaskManager, "start_worker_if_needed", lambda self: None)
    monkeypatch.setattr(render, "capabilities", lambda: {"available": False, "reason": "test stub"})
    db = face_sqlite_session
    owner, photo = _seed_owner_and_photo(db, tmp_path)
    day = date(2026, 1, 2)
    service.save(db, owner.id, day, FrameSelection(photo_id=photo.id))
    client = _build_client(db, owner)
    settings = FilmSettings(start_date=day, end_date=day, title="daily")
    response = client.post("/daily-frame/composition", json=settings.model_dump(mode="json"))
    assert response.status_code == 200
    data = response.json()["data"]
    snapshot = data["snapshot"]
    assert "frames" in snapshot and "settings" in snapshot
    assert isinstance(data["fingerprint"], str) and len(data["fingerprint"]) == 64
    assert isinstance(data["duration"], int)
    assert data["invalid"] == []
