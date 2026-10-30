"""Nightly watch 2026-10-30 (r3) · app/api/daily_frame.py 路由层盲区。

被测模块：app/api/daily_frame.py（此前覆盖率 84.5%，29 行未触达）。
本文件只补**路由处理器本身**的分支，业务规则仍由 app/service/daily_frame.py 覆盖：

- PUT /settings 重新初始化日历时区。
- GET /calendar 按天返回候选数与已选帧。
- GET /days/{day} 返回空日占位与已选帧。
- GET /days/{day}/candidates 的 still/motion 过滤与非法 kind 的 422。
- POST /days/{day}/remove 与 /undo-remove 的成功与版本冲突 409。
- GET /fill 批量填充建议（跨月 400）。
- GET /assets/{id} 对动态素材返回 duration（has_motion 分支）。
- GET /assets/{id}/access 签发播放凭证，素材缺失时 404。
- GET /assets/{id}/file 的静态预览（JPEG 重编码）、无法解码 400、运动片段缺失 404。
- POST /works 成功创建、GET /works/{id}/poster 的三处 404、
  /works/{id}/cancel、/retry、DELETE /works/{id}、
  GET /works/{id}/file 的 404 守卫、GET /works/{id}/access 的 409/签发。
- media_user：Bearer 头、播放凭证、凭证与路径/模式不匹配、失效用户。
"""

from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from PIL import Image

from app.api import daily_frame as api
from app.api.daily_frame import media_user, router
from app.api.deps import get_current_user
from app.db.models.daily_frame import DailyFrameWork
from app.db.models.photo import FileType, Photo
from app.db.models.user import User
from app.dependencies import get_db
from app.schemas.daily_frame import CalendarSettings, FilmSettings, FrameSelection
from app.service import daily_frame as service


def _algorithm():
    from app.core.system_config import system_config
    return system_config.config.security.algorithm

pytestmark = [pytest.mark.smoke, pytest.mark.module_album]

DAY = date(2026, 1, 2)


def _build_client(db, owner):
    app = FastAPI(root_path="/api")
    app.include_router(router, prefix="/daily-frame")
    app.dependency_overrides[get_current_user] = lambda: owner
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def _seed(db, tmp_path, *, name="nightly-df-api", day=DAY, file_type=FileType.image):
    owner = User(id=uuid4(), username=name + "-" + uuid4().hex[:6], hashed_password="x", is_active=True)
    db.add(owner)
    db.commit()
    service.initialize(db, owner.id, CalendarSettings(timezone="Asia/Shanghai"))
    path = tmp_path / (name + "-" + uuid4().hex[:6] + ".jpg")
    Image.new("RGB", (160, 100), "red").save(path)
    photo = Photo(id=uuid4(), owner_id=owner.id, filename=path.name, file_path=str(path),
                  file_type=file_type, photo_time=datetime.combine(day, datetime.min.time()),
                  upload_time=datetime.combine(day, datetime.min.time()),
                  size=path.stat().st_size, is_deleted=False)
    db.add(photo)
    db.commit()
    return owner, photo, path


# ---------------------------------------------------------------------------
# 日历 / 日 / 候选
# ---------------------------------------------------------------------------


def test_initialize_updates_the_calendar_timezone(face_sqlite_session, tmp_path):
    db = face_sqlite_session
    owner, _, _ = _seed(db, tmp_path)
    client = _build_client(db, owner)
    response = client.put("/daily-frame/settings", json={"timezone": "UTC"})
    assert response.status_code == 200
    assert response.json()["data"]["timezone"] == "UTC"


def test_calendar_lists_every_day_with_candidate_counts(face_sqlite_session, tmp_path):
    db = face_sqlite_session
    owner, photo, _ = _seed(db, tmp_path)
    client = _build_client(db, owner)
    response = client.get("/daily-frame/calendar", params={"start": "2026-01-01", "end": "2026-01-03"})
    assert response.status_code == 200
    data = response.json()["data"]
    days = {item["day"]: item for item in data["days"]}
    assert set(days) == {"2026-01-01", "2026-01-02", "2026-01-03"}
    assert days["2026-01-02"]["candidate_count"] == 1
    assert days["2026-01-01"]["candidate_count"] == 0
    assert data["timezone"] == "Asia/Shanghai"


def test_day_frame_returns_a_placeholder_for_an_unselected_day(face_sqlite_session, tmp_path):
    db = face_sqlite_session
    owner, photo, _ = _seed(db, tmp_path)
    client = _build_client(db, owner)
    empty = client.get("/daily-frame/days/2026-01-03")
    assert empty.status_code == 200
    assert empty.json()["data"] == {"day": "2026-01-03", "version": 0, "removed": True}

    service.save(db, owner.id, DAY, FrameSelection(photo_id=photo.id))
    selected = client.get("/daily-frame/days/2026-01-02")
    assert selected.status_code == 200
    frame = selected.json()["data"]
    assert frame["version"] == 1
    assert frame["photo_id"] == str(photo.id)
    assert frame["available"] is True


def test_candidates_filters_by_kind_and_rejects_an_unknown_kind(face_sqlite_session, tmp_path):
    db = face_sqlite_session
    owner, _, _ = _seed(db, tmp_path)
    client = _build_client(db, owner)
    still = client.get("/daily-frame/days/2026-01-02/candidates", params={"kind": "still"})
    assert still.status_code == 200
    assert still.json()["data"]["total"] == 1

    motion = client.get("/daily-frame/days/2026-01-02/candidates", params={"kind": "motion"})
    assert motion.status_code == 200
    assert motion.json()["data"]["total"] == 0

    invalid = client.get("/daily-frame/days/2026-01-02/candidates", params={"kind": "bogus"})
    assert invalid.status_code == 422
    assert invalid.json()["code"] == 422


# ---------------------------------------------------------------------------
# 移除 / 撤销
# ---------------------------------------------------------------------------


def test_remove_then_undo_remove_round_trips(face_sqlite_session, tmp_path):
    db = face_sqlite_session
    owner, photo, _ = _seed(db, tmp_path)
    client = _build_client(db, owner)
    saved = service.save(db, owner.id, DAY, FrameSelection(photo_id=photo.id))
    version = saved["version"]

    removed = client.post("/daily-frame/days/2026-01-02/remove", json={"version": version})
    assert removed.status_code == 200
    assert removed.json()["data"]["removed"] is True
    assert removed.json()["data"]["version"] == version + 1

    undone = client.post("/daily-frame/days/2026-01-02/undo-remove", json={"version": version + 1})
    assert undone.status_code == 200
    assert undone.json()["data"]["removed"] is False
    assert undone.json()["data"]["version"] == version + 2


def test_remove_with_a_stale_version_conflicts(face_sqlite_session, tmp_path):
    db = face_sqlite_session
    owner, photo, _ = _seed(db, tmp_path)
    client = _build_client(db, owner)
    service.save(db, owner.id, DAY, FrameSelection(photo_id=photo.id))
    stale = client.post("/daily-frame/days/2026-01-02/remove", json={"version": 99})
    assert stale.status_code == 409
    assert stale.json()["code"] == 409


def test_undo_remove_on_an_untouched_day_conflicts(face_sqlite_session, tmp_path):
    db = face_sqlite_session
    owner, _, _ = _seed(db, tmp_path)
    client = _build_client(db, owner)
    response = client.post("/daily-frame/days/2026-01-02/undo-remove", json={"version": 1})
    assert response.status_code == 409


# ---------------------------------------------------------------------------
# 批量填充建议
# ---------------------------------------------------------------------------


def test_fill_suggests_a_photo_for_each_day(face_sqlite_session, tmp_path):
    db = face_sqlite_session
    owner, photo, _ = _seed(db, tmp_path)
    client = _build_client(db, owner)
    response = client.get("/daily-frame/fill", params={"start": "2026-01-01", "end": "2026-01-31"})
    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert [item["day"] for item in items] == ["2026-01-02"]
    assert items[0]["photo_id"] == str(photo.id)


def test_fill_rejects_a_range_spanning_two_months(face_sqlite_session, tmp_path):
    db = face_sqlite_session
    owner, _, _ = _seed(db, tmp_path)
    client = _build_client(db, owner)
    response = client.get("/daily-frame/fill", params={"start": "2026-01-01", "end": "2026-02-01"})
    assert response.status_code == 400
    assert response.json()["code"] == 400


# ---------------------------------------------------------------------------
# 素材读取 / 播放凭证
# ---------------------------------------------------------------------------


def test_asset_reports_the_duration_of_a_motion_photo(face_sqlite_session, tmp_path, monkeypatch):
    from app.service import daily_frame_render as render

    monkeypatch.setattr(render, "probe_duration", lambda path: 12.5)
    db = face_sqlite_session
    owner, _, _ = _seed(db, tmp_path, file_type=FileType.video)
    client = _build_client(db, owner)
    photo = db.query(Photo).filter(Photo.owner_id == owner.id).one()
    detail = client.get("/daily-frame/assets/" + str(photo.id))
    assert detail.status_code == 200
    data = detail.json()["data"]
    assert data["has_motion"] is True
    assert data["duration"] == 12.5


def test_source_access_issues_a_ticket_and_rejects_a_missing_source(face_sqlite_session, tmp_path):
    db = face_sqlite_session
    owner, photo, path = _seed(db, tmp_path)
    client = _build_client(db, owner)
    granted = client.get("/daily-frame/assets/" + str(photo.id) + "/access", params={"mode": "still"})
    assert granted.status_code == 200
    assert granted.json()["data"]["token"]

    path.unlink()
    denied = client.get("/daily-frame/assets/" + str(photo.id) + "/access", params={"mode": "still"})
    assert denied.status_code == 404
    assert denied.json()["code"] == 404


def test_source_file_returns_a_jpeg_preview_for_a_still(face_sqlite_session, tmp_path):
    db = face_sqlite_session
    owner, photo, _ = _seed(db, tmp_path)
    client = _build_client(db, owner)
    app = client.app
    app.dependency_overrides[media_user] = lambda: owner
    response = client.get("/daily-frame/assets/" + str(photo.id) + "/file", params={"mode": "still"})
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert response.content[:2] == b"\xff\xd8"


def test_source_file_rejects_an_undecodable_still(face_sqlite_session, tmp_path):
    db = face_sqlite_session
    owner, photo, path = _seed(db, tmp_path)
    path.write_text("this is not an image", encoding="utf-8")
    db.commit()
    client = _build_client(db, owner)
    client.app.dependency_overrides[media_user] = lambda: owner
    response = client.get("/daily-frame/assets/" + str(photo.id) + "/file", params={"mode": "still"})
    assert response.status_code == 400
    assert response.json()["code"] == 400


def test_source_file_rejects_a_motion_request_for_a_still_photo(face_sqlite_session, tmp_path):
    db = face_sqlite_session
    owner, photo, _ = _seed(db, tmp_path)
    client = _build_client(db, owner)
    client.app.dependency_overrides[media_user] = lambda: owner
    response = client.get("/daily-frame/assets/" + str(photo.id) + "/file", params={"mode": "motion"})
    assert response.status_code == 404
    assert response.json()["code"] == 404


# ---------------------------------------------------------------------------
# media_user / media_ticket
# ---------------------------------------------------------------------------


def _fake_request(path="/api/daily-frame/assets/1/file", mode="still"):
    return SimpleNamespace(url=SimpleNamespace(path=path), query_params={"mode": mode})


def test_media_user_accepts_a_bearer_header(face_sqlite_session, tmp_path, monkeypatch):
    db = face_sqlite_session
    owner, _, _ = _seed(db, tmp_path)
    sentinel = object()
    monkeypatch.setattr(api, "get_current_user", lambda request, session, token: sentinel)
    assert media_user(_fake_request(), None, "Bearer token-value", db) is sentinel


def test_media_user_accepts_a_scoped_ticket(face_sqlite_session, tmp_path):
    from datetime import datetime, timedelta, timezone as dt_timezone

    from jose import jwt

    db = face_sqlite_session
    owner, _, _ = _seed(db, tmp_path)
    path = "/api/daily-frame/assets/1/file"
    token = jwt.encode({"sub": str(owner.id), "purpose": "daily-frame-media", "path": path,
                        "mode": "still", "exp": datetime.now(dt_timezone.utc) + timedelta(minutes=5)},
                       api.media_secret(), algorithm=_algorithm())
    request = _fake_request(path)
    assert media_user(request, token, None, db).id == owner.id


def test_media_user_rejects_a_ticket_for_another_path_or_mode(face_sqlite_session, tmp_path):
    from datetime import datetime, timedelta, timezone as dt_timezone

    from jose import jwt

    db = face_sqlite_session
    owner, _, _ = _seed(db, tmp_path)
    path = "/api/daily-frame/assets/1/file"
    token = jwt.encode({"sub": str(owner.id), "purpose": "daily-frame-media", "path": path,
                        "mode": "still", "exp": datetime.now(dt_timezone.utc) + timedelta(minutes=5)},
                       api.media_secret(), algorithm=_algorithm())
    with pytest.raises(HTTPException) as wrong_path:
        media_user(_fake_request("/api/daily-frame/assets/2/file"), token, None, db)
    assert wrong_path.value.status_code == 401
    with pytest.raises(HTTPException) as wrong_mode:
        media_user(_fake_request(path, mode="motion"), token, None, db)
    assert wrong_mode.value.status_code == 401


def test_media_user_rejects_an_inactive_user(face_sqlite_session, tmp_path):
    from datetime import datetime, timedelta, timezone as dt_timezone

    from jose import jwt

    db = face_sqlite_session
    owner, _, _ = _seed(db, tmp_path)
    owner.is_active = False
    db.commit()
    path = "/api/daily-frame/assets/1/file"
    token = jwt.encode({"sub": str(owner.id), "purpose": "daily-frame-media", "path": path,
                        "mode": "still", "exp": datetime.now(dt_timezone.utc) + timedelta(minutes=5)},
                       api.media_secret(), algorithm=_algorithm())
    with pytest.raises(HTTPException) as inactive:
        media_user(_fake_request(path), token, None, db)
    assert inactive.value.status_code == 401


def test_media_user_rejects_a_garbage_token(face_sqlite_session, tmp_path):
    db = face_sqlite_session
    with pytest.raises(HTTPException) as garbage:
        media_user(_fake_request(), "not-a-jwt", None, db)
    assert garbage.value.status_code == 401


# ---------------------------------------------------------------------------
# 作品（works）
# ---------------------------------------------------------------------------


def _work_row(db, owner, *, status="queued", output_path=None, fingerprint="f" * 64, snapshot=None):
    snapshot = snapshot or {"settings": FilmSettings(start_date=DAY, end_date=DAY).model_dump(mode="json"),
                            "timezone": "Asia/Shanghai", "frames": []}
    work = DailyFrameWork(id=uuid4(), owner_id=owner.id, fingerprint=fingerprint, snapshot=snapshot,
                           status=status, generation=1, output_path=output_path)
    db.add(work)
    db.commit()
    return work


def test_create_work_returns_the_serialized_work(face_sqlite_session, tmp_path, monkeypatch):
    from app.service import daily_frame_render as render
    from app.service.task_manager import TaskManager

    monkeypatch.setattr(render, "capabilities", lambda: {"available": True, "reason": None})
    monkeypatch.setattr(TaskManager, "start_worker_if_needed", lambda self: None)
    db = face_sqlite_session
    owner, photo, _ = _seed(db, tmp_path)
    service.save(db, owner.id, DAY, FrameSelection(photo_id=photo.id))
    settings = FilmSettings(start_date=DAY, end_date=DAY, title="daily")
    plan = service.composition(db, owner.id, settings)
    client = _build_client(db, owner)
    response = client.post("/daily-frame/works", json={
        **settings.model_dump(mode="json"), "fingerprint": plan["fingerprint"]})
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "queued"
    assert data["duration"] == 1
    assert data["days"] == ["2026-01-02"]


def test_poster_is_unavailable_for_an_unfinished_work(face_sqlite_session, tmp_path):
    db = face_sqlite_session
    owner, _, _ = _seed(db, tmp_path)
    work = _work_row(db, owner, status="queued")
    client = _build_client(db, owner)
    response = client.get("/daily-frame/works/" + str(work.id) + "/poster")
    assert response.status_code == 404
    assert response.json()["code"] == 404


def test_poster_rejects_a_file_outside_the_owner_output_root(face_sqlite_session, tmp_path):
    db = face_sqlite_session
    owner, _, _ = _seed(db, tmp_path)
    stray = tmp_path / "stray.mp4"
    stray.write_bytes(b"video")
    work = _work_row(db, owner, status="ready", output_path=str(stray))
    client = _build_client(db, owner)
    response = client.get("/daily-frame/works/" + str(work.id) + "/poster")
    assert response.status_code == 404
    assert response.json()["code"] == 404


def test_poster_is_unavailable_when_the_thumbnail_is_missing(face_sqlite_session, tmp_path):
    from app.service.daily_frame_render import output_root

    db = face_sqlite_session
    owner, _, _ = _seed(db, tmp_path)
    root = output_root(owner.id)
    target = root / (str(uuid4()) + ".mp4")
    target.write_bytes(b"video")
    work = _work_row(db, owner, status="ready", output_path=str(target))
    client = _build_client(db, owner)
    response = client.get("/daily-frame/works/" + str(work.id) + "/poster")
    assert response.status_code == 404
    assert response.json()["code"] == 404


def test_cancel_and_delete_a_work(face_sqlite_session, tmp_path):
    db = face_sqlite_session
    owner, _, _ = _seed(db, tmp_path)
    work = _work_row(db, owner, status="queued")
    client = _build_client(db, owner)
    cancelled = client.post("/daily-frame/works/" + str(work.id) + "/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["data"] == {"cancelled": True}

    other = _work_row(db, owner, status="queued", fingerprint="e" * 64)
    deleted = client.delete("/daily-frame/works/" + str(other.id))
    assert deleted.status_code == 200
    assert deleted.json()["data"] == {"deleted": True}


def test_retry_a_failed_work(face_sqlite_session, tmp_path, monkeypatch):
    from app.service import daily_frame_render as render
    from app.service.task_manager import TaskManager

    monkeypatch.setattr(render, "capabilities", lambda: {"available": True, "reason": None})
    monkeypatch.setattr(TaskManager, "start_worker_if_needed", lambda self: None)
    db = face_sqlite_session
    owner, photo, _ = _seed(db, tmp_path)
    service.save(db, owner.id, DAY, FrameSelection(photo_id=photo.id))
    settings = FilmSettings(start_date=DAY, end_date=DAY, title="daily")
    plan = service.composition(db, owner.id, settings)
    work = _work_row(db, owner, status="failed", fingerprint=plan["fingerprint"], snapshot=plan["snapshot"])
    client = _build_client(db, owner)
    response = client.post("/daily-frame/works/" + str(work.id) + "/retry")
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "queued"


def test_work_file_is_unavailable_until_the_render_finished(face_sqlite_session, tmp_path):
    db = face_sqlite_session
    owner, _, _ = _seed(db, tmp_path)
    work = _work_row(db, owner, status="processing")
    client = _build_client(db, owner)
    client.app.dependency_overrides[media_user] = lambda: owner
    response = client.get("/daily-frame/works/" + str(work.id) + "/file")
    assert response.status_code == 404
    assert response.json()["code"] == 404


def test_work_file_rejects_a_file_outside_the_owner_output_root(face_sqlite_session, tmp_path):
    db = face_sqlite_session
    owner, _, _ = _seed(db, tmp_path)
    stray = tmp_path / "stray.mp4"
    stray.write_bytes(b"video")
    work = _work_row(db, owner, status="ready", output_path=str(stray))
    client = _build_client(db, owner)
    client.app.dependency_overrides[media_user] = lambda: owner
    response = client.get("/daily-frame/works/" + str(work.id) + "/file")
    assert response.status_code == 404
    assert response.json()["code"] == 404


def test_work_access_requires_a_ready_work(face_sqlite_session, tmp_path):
    db = face_sqlite_session
    owner, _, _ = _seed(db, tmp_path)
    work = _work_row(db, owner, status="queued")
    client = _build_client(db, owner)
    pending = client.get("/daily-frame/works/" + str(work.id) + "/access")
    assert pending.status_code == 409
    assert pending.json()["code"] == 409


def test_work_access_issues_a_ticket_for_a_ready_work(face_sqlite_session, tmp_path):
    from app.service.daily_frame_render import output_root

    db = face_sqlite_session
    owner, _, _ = _seed(db, tmp_path)
    root = output_root(owner.id)
    target = root / (str(uuid4()) + ".mp4")
    target.write_bytes(b"video")
    work = _work_row(db, owner, status="ready", output_path=str(target))
    client = _build_client(db, owner)
    response = client.get("/daily-frame/works/" + str(work.id) + "/access")
    assert response.status_code == 200
    assert response.json()["data"]["token"]
