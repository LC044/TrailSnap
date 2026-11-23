"""Nightly watch 2026-11-23 · app/api/daily_frame.py 的批量填充 / 素材读取盲区。

覆盖：
- confirm_fill 逐日保存选帧并返回 saved 状态（happy）
- confirm_fill 把 409 冲突记为 skipped（edge）
- confirm_fill 把其它错误记为 failed（error）
- source_access 在素材缺失时返回 404（error）
- source_access 为可用素材签发播放凭证（happy）
- source_file 的 still 分支返回 JPEG 预览（happy）
- source_file 的 motion 分支返回原文件（happy）
- work_access 在作品未就绪时返回 409（error）
- work_access 为已就绪作品签发播放凭证（happy）
"""

from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api import daily_frame as frame_api

pytestmark = [pytest.mark.smoke]


def _user():
    return SimpleNamespace(id=uuid4())


def _request(path="/api/daily-frame/works/x/access"):
    from starlette.requests import Request

    scope = {"type": "http", "method": "GET", "path": path, "headers": [],
             "query_string": b"", "scheme": "http", "server": ("testserver", 80),
             "client": ("testclient", 1234), "root_path": ""}
    return Request(scope)


def _selection(day: date):
    from app.schemas.daily_frame import BatchSelection

    return BatchSelection(day=day, photo_id=uuid4(), mode="still")


def test_confirm_fill_saves_every_selected_day(face_sqlite_session, monkeypatch):
    from app.service import daily_frame as service
    from app.schemas.daily_frame import BatchFill

    seen = []

    def fake_save(db, owner_id, day, selection, only_empty=False):
        seen.append((day, selection.mode, only_empty))
        return {"photo_id": str(selection.photo_id)}

    monkeypatch.setattr(service, "save", fake_save)
    days = [date(2024, 5, 1), date(2024, 5, 2)]
    payload = BatchFill(items=[_selection(day) for day in days])

    result = frame_api.confirm_fill(payload, _user(), face_sqlite_session)

    assert result.code == 0
    assert [item["status"] for item in result.data["items"]] == ["saved", "saved"]
    assert [item["day"] for item in result.data["items"]] == ["2024-05-01", "2024-05-02"]
    assert all(only_empty is True for _, _, only_empty in seen)


def test_confirm_fill_records_a_conflict_as_skipped(face_sqlite_session, monkeypatch):
    from app.service import daily_frame as service
    from app.schemas.daily_frame import BatchFill

    def fake_save(db, owner_id, day, selection, only_empty=False):
        raise HTTPException(409, "该日已有选帧")

    monkeypatch.setattr(service, "save", fake_save)
    payload = BatchFill(items=[_selection(date(2024, 5, 1))])

    result = frame_api.confirm_fill(payload, _user(), face_sqlite_session)

    assert result.data["items"][0]["status"] == "skipped"
    assert result.data["items"][0]["reason"] == "该日已有选帧"


def test_confirm_fill_records_other_failures_as_failed(face_sqlite_session, monkeypatch):
    from app.service import daily_frame as service
    from app.schemas.daily_frame import BatchFill

    def fake_save(db, owner_id, day, selection, only_empty=False):
        raise HTTPException(400, "素材不可用")

    monkeypatch.setattr(service, "save", fake_save)
    payload = BatchFill(items=[_selection(date(2024, 5, 1))])

    result = frame_api.confirm_fill(payload, _user(), face_sqlite_session)

    assert result.data["items"][0]["status"] == "failed"
    assert result.data["items"][0]["reason"] == "素材不可用"


def test_source_access_reports_a_missing_source(face_sqlite_session, monkeypatch):
    from app.service import daily_frame as service

    monkeypatch.setattr(service, "owned_photo", lambda db, owner_id, photo_id: object())
    monkeypatch.setattr(service, "source_path", lambda photo, mode: (None, "素材不存在"))

    with pytest.raises(HTTPException) as failure:
        frame_api.source_access(uuid4(), _request("/api/daily-frame/assets/1/access"),
                                "motion", _user(), face_sqlite_session)
    assert failure.value.status_code == 404


def test_source_access_signs_a_media_ticket(face_sqlite_session, monkeypatch):
    from app.service import daily_frame as service

    seen = {}

    def fake_media_ticket(user, request, mode="still"):
        seen["mode"] = mode
        seen["user"] = user
        return {"token": "ticket-1"}

    monkeypatch.setattr(service, "owned_photo", lambda db, owner_id, photo_id: object())
    monkeypatch.setattr(service, "source_path", lambda photo, mode: ("/tmp/source.mp4", None))
    monkeypatch.setattr(frame_api, "media_ticket", fake_media_ticket)
    user = _user()

    result = frame_api.source_access(uuid4(), _request("/api/daily-frame/assets/1/access"),
                                     "motion", user, face_sqlite_session)

    assert result.code == 0
    assert result.data["token"] == "ticket-1"
    assert seen["mode"] == "motion"
    assert seen["user"] is user


def test_source_file_returns_a_jpeg_preview_for_still_mode(face_sqlite_session, monkeypatch, tmp_path):
    from PIL import Image

    from app.service import daily_frame as service

    source = tmp_path / "still.jpg"
    Image.new("RGB", (64, 48), (10, 20, 30)).save(source)

    monkeypatch.setattr(service, "owned_photo", lambda db, owner_id, photo_id: object())
    monkeypatch.setattr(service, "source_path", lambda photo, mode: (str(source), None))

    response = frame_api.source_file(uuid4(), "still", _user(), face_sqlite_session)

    assert response.media_type == "image/jpeg"
    assert response.body[:2] == b"\xff\xd8"


def test_source_file_streams_the_original_for_motion_mode(face_sqlite_session, monkeypatch, tmp_path):
    from app.service import daily_frame as service

    source = tmp_path / "motion.mp4"
    source.write_bytes(b"video-bytes")

    monkeypatch.setattr(service, "owned_photo", lambda db, owner_id, photo_id: object())
    monkeypatch.setattr(service, "source_path", lambda photo, mode: (str(source), None))

    response = frame_api.source_file(uuid4(), "motion", _user(), face_sqlite_session)

    assert str(source) == response.path


def test_source_file_reports_a_missing_source(face_sqlite_session, monkeypatch):
    from app.service import daily_frame as service

    monkeypatch.setattr(service, "owned_photo", lambda db, owner_id, photo_id: object())
    monkeypatch.setattr(service, "source_path", lambda photo, mode: (None, "素材不存在"))

    with pytest.raises(HTTPException) as failure:
        frame_api.source_file(uuid4(), "still", _user(), face_sqlite_session)
    assert failure.value.status_code == 404


def test_work_access_rejects_a_work_that_is_not_ready(face_sqlite_session, monkeypatch):
    from app.service import daily_frame as service

    monkeypatch.setattr(service, "owned_work",
                        lambda db, owner_id, work_id: SimpleNamespace(status="rendering"))

    with pytest.raises(HTTPException) as failure:
        frame_api.work_access(uuid4(), _request(), _user(), face_sqlite_session)
    assert failure.value.status_code == 409


def test_work_access_signs_a_ticket_for_a_ready_work(face_sqlite_session, monkeypatch):
    from app.service import daily_frame as service

    monkeypatch.setattr(service, "owned_work",
                        lambda db, owner_id, work_id: SimpleNamespace(status="ready"))
    monkeypatch.setattr(frame_api, "media_ticket",
                        lambda user, request, mode="still": {"token": "work-ticket"})

    result = frame_api.work_access(uuid4(), _request(), _user(), face_sqlite_session)

    assert result.code == 0
    assert result.data["token"] == "work-ticket"
