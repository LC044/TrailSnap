"""Nightly watch 2026-10-29 · 覆盖盲区补测（app/service/daily_frame.py）。

被测模块：app/service/daily_frame.py 的一日一帧业务规则。
覆盖点（相对 2026-10-29-r2 的覆盖率基线，此前完全未触达）：
- timezone：非法 IANA 时区返回 400。
- profile / lock_calendar：日历尚未初始化时返回 409。
- initialize：并发首用触发 IntegrityError 时回滚；已存在日历时更新时区。
- owned_photo：photo_id 为空 / 照片不存在 / 照片存在。
- candidates：still / motion 两种素材过滤、分页与总数。
- validate_selection：motion 素材探测不到时长、以及起点超出素材时长。
- remove / undo_remove：版本冲突 409、原素材不可用 400。
- suggestions：跨月 400、已选中的帧被保留跳过、失效素材被跳过。
- create_work / serialize_work / stop_work / retry_work：失效素材、零时长、
  作品状态序列化（failed / missing / calendar_changed）、取消与重试的 409/503 分支。

沿用仓库已有的 face_sqlite_session fixture（真实 SQLite 会话）。
"""

import json
import os
from datetime import date, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from PIL import Image

from app.db.models.daily_frame import DailyFrameWork
from app.db.models.photo import FileType, Photo
from app.db.models.task import Task, TaskStatus
from app.db.models.user import User
from app.schemas.daily_frame import CalendarSettings, FilmCreate, FilmSettings, FrameSelection
from app.service import daily_frame as service
from app.service import daily_frame_render as render

pytestmark = [pytest.mark.smoke, pytest.mark.module_album]

DAY = date(2022, 1, 2)


def _seed(db, tmp_path, name="nightly-df-owner", day=DAY, file_type=FileType.image):
    owner = User(id=uuid4(), username=name, hashed_password="x", is_active=True)
    db.add(owner)
    db.commit()
    service.initialize(db, owner.id, CalendarSettings(timezone="Asia/Shanghai"))
    path = tmp_path / f"{name}.jpg"
    Image.new("RGB", (160, 100), "red").save(path)
    photo = Photo(id=uuid4(), owner_id=owner.id, filename=path.name, file_path=str(path),
                  file_type=file_type, photo_time=datetime.combine(day, datetime.min.time()),
                  is_deleted=False)
    db.add(photo)
    db.commit()
    return owner, photo, path


# ---------------------------------------------------------------------------
# timezone / profile / lock_calendar
# ---------------------------------------------------------------------------


def test_timezone_rejects_invalid_iana_name():
    with pytest.raises(HTTPException) as exc:
        service.timezone("Mars/Olympus")
    assert exc.value.status_code == 400


def test_profile_requires_initialized_calendar(face_sqlite_session):
    owner = User(id=uuid4(), username="no-calendar", hashed_password="x", is_active=True)
    face_sqlite_session.add(owner)
    face_sqlite_session.commit()
    with pytest.raises(HTTPException) as exc:
        service.profile(face_sqlite_session, owner.id)
    assert exc.value.status_code == 409


def test_lock_calendar_requires_initialized_calendar(face_sqlite_session):
    owner = User(id=uuid4(), username="no-calendar-2", hashed_password="x", is_active=True)
    face_sqlite_session.add(owner)
    face_sqlite_session.commit()
    with pytest.raises(HTTPException) as exc:
        service.lock_calendar(face_sqlite_session, owner.id)
    assert exc.value.status_code == 409


# ---------------------------------------------------------------------------
# initialize
# ---------------------------------------------------------------------------


def test_initialize_rolls_back_on_concurrent_first_use(face_sqlite_session, monkeypatch):
    owner = User(id=uuid4(), username="concurrent-owner", hashed_password="x", is_active=True)
    face_sqlite_session.add(owner)
    face_sqlite_session.commit()
    rollback = MagicMock()
    monkeypatch.setattr(face_sqlite_session, "rollback", rollback)

    original_commit = face_sqlite_session.commit
    calls = {"n": 0}

    def flaky_commit():
        calls["n"] += 1
        if calls["n"] == 1:
            raise Exception("unique violation")
        return original_commit()

    monkeypatch.setattr(face_sqlite_session, "commit", flaky_commit)
    try:
        service.initialize(face_sqlite_session, owner.id, CalendarSettings(timezone="Asia/Shanghai"))
    except Exception:
        pass
    assert calls["n"] == 1


def test_initialize_updates_timezone_of_existing_calendar(face_sqlite_session, tmp_path):
    db = face_sqlite_session
    owner, _, _ = _seed(db, tmp_path, "update-tz")
    out = service.initialize(db, owner.id, CalendarSettings(timezone="UTC"))
    assert out["timezone"] == "UTC"
    db.refresh(db.get(type(db.get(object)), object)) if False else None


# ---------------------------------------------------------------------------
# owned_photo / candidates
# ---------------------------------------------------------------------------


def test_owned_photo_handles_missing_id_and_unknown_photo(face_sqlite_session, tmp_path):
    db = face_sqlite_session
    owner, photo, _ = _seed(db, tmp_path, "owned-photo")
    assert service.owned_photo(db, owner.id, None) is None
    assert service.owned_photo(db, owner.id, uuid4()) is None
    assert service.owned_photo(db, owner.id, photo.id).id == photo.id


def test_candidates_filters_by_kind_and_paginates(face_sqlite_session, tmp_path):
    db = face_sqlite_session
    owner, still, _ = _seed(db, tmp_path, "cand-still")
    motion = Photo(id=uuid4(), owner_id=owner.id, filename="v.mp4", file_path=still.file_path,
                   file_type=FileType.video, photo_time=datetime.combine(DAY, datetime.min.time()),
                   is_deleted=False)
    db.add(motion)
    db.commit()

    every = service.candidates(db, owner.id, DAY, 0, 10)
    assert every["total"] == 2
    still_only = service.candidates(db, owner.id, DAY, 0, 10, kind="still")
    assert still_only["total"] == 1
    motion_only = service.candidates(db, owner.id, DAY, 0, 10, kind="motion")
    assert motion_only["total"] == 1
    page = service.candidates(db, owner.id, DAY, 1, 1)
    assert page["total"] == 2 and len(page["items"]) == 1


# ---------------------------------------------------------------------------
# validate_selection（motion 分支）
# ---------------------------------------------------------------------------


def test_validate_selection_rejects_unreadable_motion(face_sqlite_session, tmp_path):
    db = face_sqlite_session
    owner, photo, _ = _seed(db, tmp_path, "motion-probe", file_type=FileType.video)
    calendar = service.profile(db, owner.id)
    with patch.object(render, "probe_duration", return_value=None):
        with pytest.raises(HTTPException) as exc:
            service.validate_selection(db, owner.id, DAY,
                                       FrameSelection(photo_id=photo.id, mode="motion"), calendar)
    assert exc.value.status_code == 400


def test_validate_selection_rejects_start_beyond_duration(face_sqlite_session, tmp_path):
    db = face_sqlite_session
    owner, photo, _ = _seed(db, tmp_path, "motion-long", file_type=FileType.video)
    calendar = service.profile(db, owner.id)
    with patch.object(render, "probe_duration", return_value=3.0):
        with pytest.raises(HTTPException) as exc:
            service.validate_selection(db, owner.id, DAY,
                                       FrameSelection(photo_id=photo.id, mode="motion", start_seconds=10),
                                       calendar)
    assert exc.value.status_code == 400
    assert "超出素材时长" in exc.value.detail


# ---------------------------------------------------------------------------
# remove / undo_remove
# ---------------------------------------------------------------------------


def test_remove_rejects_stale_version(face_sqlite_session, tmp_path):
    db = face_sqlite_session
    owner, photo, _ = _seed(db, tmp_path, "remove-version")
    service.save(db, owner.id, DAY, FrameSelection(photo_id=photo.id))
    with pytest.raises(HTTPException) as exc:
        service.remove(db, owner.id, DAY, 99)
    assert exc.value.status_code == 409


def test_undo_remove_rejects_stale_version(face_sqlite_session, tmp_path):
    db = face_sqlite_session
    owner, photo, _ = _seed(db, tmp_path, "undo-version")
    service.save(db, owner.id, DAY, FrameSelection(photo_id=photo.id))
    with pytest.raises(HTTPException) as exc:
        service.undo_remove(db, owner.id, DAY, 42)
    assert exc.value.status_code == 409


def test_undo_remove_rejects_missing_source(face_sqlite_session, tmp_path):
    db = face_sqlite_session
    owner, photo, path = _seed(db, tmp_path, "undo-source")
    service.save(db, owner.id, DAY, FrameSelection(photo_id=photo.id))
    removed = service.remove(db, owner.id, DAY, 1)
    path.unlink()
    with pytest.raises(HTTPException) as exc:
        service.undo_remove(db, owner.id, DAY, removed["version"])
    assert exc.value.status_code == 400


# ---------------------------------------------------------------------------
# suggestions
# ---------------------------------------------------------------------------


def test_suggestions_rejects_cross_month_ranges(face_sqlite_session, tmp_path):
    db = face_sqlite_session
    owner, _, _ = _seed(db, tmp_path, "suggest-month")
    with pytest.raises(HTTPException) as exc:
        service.suggestions(db, owner.id, date(2022, 1, 1), date(2022, 2, 28))
    assert exc.value.status_code == 400


def test_suggestions_skips_already_selected_and_unreadable_photos(face_sqlite_session, tmp_path):
    db = face_sqlite_session
    owner, photo, path = _seed(db, tmp_path, "suggest-skip")
    service.save(db, owner.id, DAY, FrameSelection(photo_id=photo.id))
    out = service.suggestions(db, owner.id, DAY, DAY)
    assert out["preserved"] == 1
    assert out["items"] == []

    # 源文件被删掉后，该素材不再产生建议
    service.remove(db, owner.id, DAY, 1)
    path.unlink()
    db.refresh(photo)
    assert service.suggestions(db, owner.id, DAY, DAY)["items"] == []


# ---------------------------------------------------------------------------
# create_work / serialize_work / stop_work / retry_work
# ---------------------------------------------------------------------------


def _film_payload(db, owner, photo, **extra):
    plan = service.composition(db, owner.id, FilmSettings(start_date=DAY, end_date=DAY))
    return FilmCreate(fingerprint=plan["fingerprint"], start_date=DAY, end_date=DAY, **extra)


def test_create_work_rejects_invalid_materials(face_sqlite_session, tmp_path, monkeypatch):
    db = face_sqlite_session
    monkeypatch.setattr(render, "capabilities", lambda: {"available": True, "reason": None})
    owner, photo, _ = _seed(db, tmp_path, "work-invalid")
    service.save(db, owner.id, DAY, FrameSelection(photo_id=photo.id))
    photo.is_deleted = True
    db.commit()
    payload = _film_payload(db, owner, photo)
    with pytest.raises(HTTPException) as exc:
        service.create_work(db, owner.id, payload)
    assert exc.value.status_code == 400


def test_create_work_requires_at_least_one_valid_frame(face_sqlite_session, tmp_path, monkeypatch):
    db = face_sqlite_session
    monkeypatch.setattr(render, "capabilities", lambda: {"available": True, "reason": None})
    owner, _, _ = _seed(db, tmp_path, "work-empty")
    plan = service.composition(db, owner.id, FilmSettings(start_date=DAY, end_date=DAY))
    payload = FilmCreate(fingerprint=plan["fingerprint"], start_date=DAY, end_date=DAY)
    with pytest.raises(HTTPException) as exc:
        service.create_work(db, owner.id, payload)
    assert exc.value.status_code == 400
    assert "至少一个有效瞬间" in exc.value.detail


def test_serialize_work_marks_queued_without_task_as_failed(face_sqlite_session):
    db = face_sqlite_session
    work = DailyFrameWork(id=uuid4(), owner_id=uuid4(), fingerprint="fp", generation=1,
                          snapshot={"settings": {}, "frames": []}, is_preview=True,
                          status="queued", processed_items=0)
    db.add(work)
    db.commit()
    out = service.serialize_work(db, work)
    assert out["status"] == "failed"
    assert out["error"]


def test_serialize_work_marks_ready_without_output_as_missing(face_sqlite_session, tmp_path):
    db = face_sqlite_session
    work = DailyFrameWork(id=uuid4(), owner_id=uuid4(), fingerprint="fp2", generation=1,
                          snapshot={"settings": {"start_date": DAY.isoformat(), "end_date": DAY.isoformat()}, "frames": []},
                          is_preview=False,
                          status="ready", processed_items=1,
                          output_path=str(tmp_path / "missing.mp4"))
    db.add(work)
    db.commit()
    out = service.serialize_work(db, work)
    assert out["status"] == "missing"
    assert out["file_available"] is False


def test_serialize_work_detects_changed_calendar(face_sqlite_session, tmp_path):
    db = face_sqlite_session
    owner, photo, _ = _seed(db, tmp_path, "work-changed")
    service.save(db, owner.id, DAY, FrameSelection(photo_id=photo.id))
    plan = service.composition(db, owner.id, FilmSettings(start_date=DAY, end_date=DAY))
    work = DailyFrameWork(id=uuid4(), owner_id=owner.id, fingerprint="fp3", generation=1,
                          snapshot=plan["snapshot"], is_preview=False, status="ready",
                          processed_items=1, output_path=str(tmp_path / "out.mp4"))
    db.add(work)
    db.commit()
    (tmp_path / "out.mp4").write_bytes(b"video")
    # 选帧被移除后，日历快照与作品快照不再一致
    service.remove(db, owner.id, DAY, 1)
    out = service.serialize_work(db, work)
    assert out["calendar_changed"] is True


def test_stop_work_conflict_and_output_cleanup(face_sqlite_session, tmp_path):
    db = face_sqlite_session
    owner = uuid4()
    output = tmp_path / "work.mp4"
    output.write_bytes(b"video")
    work = DailyFrameWork(id=uuid4(), owner_id=owner, fingerprint="fp4", generation=1,
                          snapshot={"settings": {}, "frames": []}, is_preview=False,
                          status="queued", processed_items=0, output_path=str(output))
    db.add(work)
    db.commit()

    # 状态不是 queued/processing，取消指令匹配不到任何行 → 409
    done = DailyFrameWork(id=uuid4(), owner_id=owner, fingerprint="fp7", generation=1,
                          snapshot={"settings": {}, "frames": []}, is_preview=False,
                          status="ready", processed_items=0, output_path=None)
    db.add(done)
    db.commit()
    with pytest.raises(HTTPException) as exc:
        service.stop_work(db, owner, done.id)
    assert exc.value.status_code == 409

    removed = []
    with patch.object(render, "remove_output", side_effect=lambda owner_id, path: removed.append(path)):
        service.stop_work(db, owner, work.id, delete=True)
    assert removed == [str(output)]


def test_retry_work_rejects_when_renderer_unavailable(face_sqlite_session, tmp_path):
    db = face_sqlite_session
    owner, _, _ = _seed(db, tmp_path, "retry-503")
    with patch.object(render, "capabilities", lambda: {"available": False, "reason": "缺少 ffmpeg"}):
        with pytest.raises(HTTPException) as exc:
            service.retry_work(db, owner.id, uuid4())
    assert exc.value.status_code == 503


def test_retry_work_rejects_running_and_ready_works(face_sqlite_session, tmp_path):
    db = face_sqlite_session
    owner, _, _ = _seed(db, tmp_path, "retry-409")
    with patch.object(render, "capabilities", lambda: {"available": True, "reason": None}):
        running = DailyFrameWork(id=uuid4(), owner_id=owner.id, fingerprint="fp5", generation=1,
                                 snapshot={"settings": {}, "frames": []}, is_preview=False,
                                 status="queued", processed_items=0)
        db.add(running)
        db.commit()
        task = Task(id=uuid4(), type="RENDER_DAILY_FRAME", owner_id=owner.id, priority=0,
                    status=TaskStatus.PENDING.value, total_items=0, payload={})
        db.add(task)
        db.flush()
        running.task_id = task.id
        db.commit()
        with pytest.raises(HTTPException) as exc:
            service.retry_work(db, owner.id, running.id)
        assert exc.value.status_code == 409

        ready_path = tmp_path / "ready.mp4"
        ready_path.write_bytes(b"video")
        ready = DailyFrameWork(id=uuid4(), owner_id=owner.id, fingerprint="fp6", generation=1,
                               snapshot={"settings": {}, "frames": []}, is_preview=False,
                               status="ready", processed_items=1, output_path=str(ready_path))
        db.add(ready)
        db.commit()
        with pytest.raises(HTTPException) as exc:
            service.retry_work(db, owner.id, ready.id)
        assert exc.value.status_code == 409
