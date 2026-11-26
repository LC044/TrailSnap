"""Nightly watch 2026-11-26 · app/service/daily_frame.py 的盲区。

「一日一帧」是最近新增的整套业务（service + api 共 800+ 行），此前**没有任何
单元测试**引用过 ``app.service.daily_frame``（定向覆盖扫描里它是 service 层
唯一零引用的模块）。本文件覆盖其中的规则与状态机：

- 时区解析 / 今天的日期 / 日期范围校验
- 素材所属日期判定、素材可用性（静态 / 动态）与序列化
- 日历初始化、锁定与冲突（409）
- 候选素材筛选（still / motion）与分页
- 选帧 → 删除 → 撤销 的版本状态机

数据库部分用真实 SQLite 会话执行，不使用 MagicMock。
"""

from datetime import date, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models.photo import FileType, Photo
from app.schemas.daily_frame import CalendarSettings, FrameSelection
from app.service import daily_frame as service


@pytest.fixture
def frame_db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db
    engine.dispose()


@pytest.fixture(autouse=True)
def stub_capabilities(monkeypatch):
    """影片能力探测会调用 ffmpeg/字体，测试里固定成不可用。"""
    import app.service.daily_frame_render as render

    monkeypatch.setattr(render, "capabilities", lambda: {"available": False, "reason": "stub"})


def add_photo(db, owner, *, day, file_path, file_type=FileType.image, photo_id=None, deleted=False):
    photo_id = photo_id or uuid4()
    db.add(Photo(
        id=photo_id, owner_id=owner, filename="frame.jpg", file_path=file_path,
        file_type=file_type, size=10, is_deleted=deleted,
        photo_time=datetime(day.year, day.month, day.day, 10, 0, 0),
    ))
    return photo_id


def calendar_row(owner, tz="Asia/Shanghai", locked=False):
    from app.db.models.daily_frame import DailyFrameCalendar

    return DailyFrameCalendar(owner_id=owner, timezone=tz, locked=locked, revision=0)


# --- 时区与日期 ------------------------------------------------------


def test_timezone_accepts_iana_names_and_rejects_the_rest():
    assert str(service.timezone("Asia/Shanghai")) == "Asia/Shanghai"

    with pytest.raises(HTTPException) as error:
        service.timezone("Not/AZone")
    assert error.value.status_code == 400
    assert "IANA" in error.value.detail


def test_today_uses_the_calendar_timezone():
    owner = uuid4()
    row = calendar_row(owner)

    assert isinstance(service.today(row), date)


def test_check_range_rejects_invalid_and_future_ranges():
    owner = uuid4()
    row = calendar_row(owner)
    yesterday = date.today() - timedelta(days=1)

    with pytest.raises(HTTPException) as error:
        service.check_range(yesterday, yesterday - timedelta(days=1), row)
    assert error.value.status_code == 400

    with pytest.raises(HTTPException) as error:
        service.check_range(date(1900, 1, 1), date(2201, 1, 1), row)
    assert error.value.status_code == 400

    with pytest.raises(HTTPException) as error:
        service.check_range(date(2024, 1, 1), date(2024, 1, 1) + timedelta(days=366), row)
    assert error.value.status_code == 400

    with pytest.raises(HTTPException) as error:
        service.check_range(date.today() + timedelta(days=2), date.today() + timedelta(days=2), row)
    assert error.value.status_code == 400
    assert "未来" in error.value.detail

    # 允许未来时同样的区间不再报错
    service.check_range(date.today() + timedelta(days=2), date.today() + timedelta(days=2),
                        row, allow_future=True)


# --- 素材规则 --------------------------------------------------------


def test_photo_day_falls_back_to_the_stored_local_date():
    owner = uuid4()
    row = calendar_row(owner)
    photo = Photo(photo_time=datetime(2024, 3, 4, 23, 30, 0))

    assert service.photo_day(photo, row) == date(2024, 3, 4)
    assert service.photo_day(Photo(photo_time=None), row) is None


def test_source_path_reports_why_a_photo_cannot_be_used(tmp_path):
    missing = Photo(id=uuid4(), file_path=str(tmp_path / "missing.jpg"), file_type=FileType.image)

    path, reason = service.source_path(None, "still")
    assert path is None and reason

    path, reason = service.source_path(missing, "still")
    assert path is None and "不可读取" in reason

    real = tmp_path / "real.jpg"
    real.write_bytes(b"x")
    still = Photo(id=uuid4(), file_path=str(real), file_type=FileType.image)
    assert service.source_path(still, "still") == (str(real), None)

    video = Photo(id=uuid4(), file_path=str(real), file_type=FileType.video)
    path, reason = service.source_path(video, "still")
    assert path is None and "动态片段" in reason

    path, reason = service.source_path(still, "motion")
    assert path is None and "没有动态片段" in reason


def test_serialize_photo_reports_the_availability(tmp_path):
    real = tmp_path / "real.jpg"
    real.write_bytes(b"x")
    photo = Photo(id=uuid4(), owner_id=uuid4(), file_path=str(real), file_type=FileType.image,
                  photo_time=datetime(2024, 3, 4, 10, 0), duration=None)

    payload = service.serialize_photo(photo)

    assert payload["available"] is True
    assert payload["reason"] is None
    assert payload["has_motion"] is False
    assert payload["photo_time"].startswith("2024-03-04")


def test_fingerprint_is_stable_and_order_independent():
    first = service.fingerprint({"b": 1, "a": 2})
    second = service.fingerprint({"a": 2, "b": 1})

    assert first == second
    assert len(first) == 64


# --- 日历生命周期 ----------------------------------------------------


def test_profile_requires_an_initialized_calendar(frame_db):
    owner = uuid4()

    with pytest.raises(HTTPException) as error:
        service.profile(frame_db, owner)
    assert error.value.status_code == 409


def test_settings_reports_the_uninitialized_state(frame_db):
    owner = uuid4()

    payload = service.settings(frame_db, owner)

    assert payload["initialized"] is False
    assert payload["timezone"] is None
    assert payload["today"] is None


def test_initialize_creates_the_calendar_and_lock_calendar_bumps_the_revision(frame_db):
    owner = uuid4()

    payload = service.initialize(frame_db, owner, CalendarSettings(timezone="Asia/Shanghai"))
    assert payload["initialized"] is True
    assert payload["timezone"] == "Asia/Shanghai"

    again = service.initialize(frame_db, owner, CalendarSettings(timezone="Asia/Shanghai"))
    assert again["initialized"] is True
    assert again["revision"] >= 1


def test_initialize_refuses_a_new_timezone_once_a_frame_is_selected(frame_db):
    owner = uuid4()
    frame_db.add(calendar_row(owner, locked=True))
    frame_db.commit()

    with pytest.raises(HTTPException) as error:
        service.initialize(frame_db, owner, CalendarSettings(timezone="Europe/Berlin"))
    assert error.value.status_code == 409


def test_lock_calendar_requires_an_existing_calendar(frame_db):
    with pytest.raises(HTTPException) as error:
        service.lock_calendar(frame_db, uuid4())
    assert error.value.status_code == 409


def test_frame_returns_a_placeholder_when_the_day_is_empty(frame_db):
    owner = uuid4()
    frame_db.add(calendar_row(owner))
    frame_db.commit()

    payload = service.frame(frame_db, owner, date(2024, 3, 4))

    assert payload == {"day": "2024-03-04", "version": 0, "removed": True}


# --- 候选与状态机 ----------------------------------------------------


def test_candidates_filter_by_kind(frame_db, tmp_path):
    owner = uuid4()
    frame_db.add(calendar_row(owner))
    real = tmp_path / "real.jpg"
    real.write_bytes(b"x")
    day = date.today() - timedelta(days=3)
    add_photo(frame_db, owner, day=day, file_path=str(real))
    add_photo(frame_db, owner, day=day, file_path=str(real), file_type=FileType.video)
    add_photo(frame_db, owner, day=day, file_path=str(real), deleted=True)
    frame_db.commit()

    every = service.candidates(frame_db, owner, day, 0, 10)
    assert every["total"] == 2

    still = service.candidates(frame_db, owner, day, 0, 10, kind="still")
    assert still["total"] == 1

    motion = service.candidates(frame_db, owner, day, 0, 10, kind="motion")
    assert motion["total"] == 1


def test_save_remove_and_undo_round_trip(frame_db, tmp_path):
    owner = uuid4()
    frame_db.add(calendar_row(owner))
    real = tmp_path / "real.jpg"
    real.write_bytes(b"x")
    day = date.today() - timedelta(days=2)
    photo_id = add_photo(frame_db, owner, day=day, file_path=str(real))
    frame_db.commit()

    saved = service.save(
        frame_db, owner, day,
        FrameSelection(photo_id=photo_id, mode="still", caption="  一句  备注 ", version=0),
    )
    assert saved["photo_id"] == str(photo_id)
    assert saved["version"] == 1
    assert saved["caption"] == "一句 备注"
    assert saved["available"] is True

    removed = service.remove(frame_db, owner, day, 1)
    assert removed["removed"] is True
    assert removed["version"] == 2

    restored = service.undo_remove(frame_db, owner, day, 2)
    assert restored["removed"] is False
    assert restored["version"] == 3


def test_save_rejects_a_stale_version(frame_db, tmp_path):
    owner = uuid4()
    frame_db.add(calendar_row(owner))
    real = tmp_path / "real.jpg"
    real.write_bytes(b"x")
    day = date.today() - timedelta(days=2)
    photo_id = add_photo(frame_db, owner, day=day, file_path=str(real))
    frame_db.commit()

    service.save(frame_db, owner, day, FrameSelection(photo_id=photo_id, version=0))

    with pytest.raises(HTTPException) as error:
        service.save(frame_db, owner, day, FrameSelection(photo_id=photo_id, version=0))
    assert error.value.status_code == 409


def test_save_rejects_a_photo_taken_on_another_day(frame_db, tmp_path):
    owner = uuid4()
    frame_db.add(calendar_row(owner))
    real = tmp_path / "real.jpg"
    real.write_bytes(b"x")
    day = date.today() - timedelta(days=2)
    photo_id = add_photo(frame_db, owner, day=day - timedelta(days=3), file_path=str(real))
    frame_db.commit()

    with pytest.raises(HTTPException) as error:
        service.save(frame_db, owner, day, FrameSelection(photo_id=photo_id, version=0))
    assert error.value.status_code == 400


def test_save_rejects_a_photo_of_another_owner(frame_db, tmp_path):
    owner, other = uuid4(), uuid4()
    frame_db.add(calendar_row(owner))
    real = tmp_path / "real.jpg"
    real.write_bytes(b"x")
    day = date.today() - timedelta(days=2)
    photo_id = add_photo(frame_db, other, day=day, file_path=str(real))
    frame_db.commit()

    with pytest.raises(HTTPException) as error:
        service.save(frame_db, owner, day, FrameSelection(photo_id=photo_id, version=0))
    assert error.value.status_code == 404
