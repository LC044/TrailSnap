"""Nightly watch 2026-11-26 · app/service/daily_frame.py 的「影片作品」生命周期盲区。

「一日一帧」的 service 层此前只覆盖了选帧状态机（保存 / 删除 / 撤销）与候选筛选，
而**影片作品**这条链路——``create_work`` / ``serialize_work`` / ``stop_work`` /
``retry_work``——的分支完全没有被断言过：

- 能力探测失败（未装 FFmpeg）时必须 503，而不是抛栈；
- 预览指纹过期必须 409，且失效素材需要显式选择跳过；
- 同一指纹的成品应当复用而不是重复排队；
- 作品状态要跟随任务状态映射，产物文件丢失时要标记为 missing；
- 停止作品要同时取消后台任务，删除要写 deleted_at；
- 重试要拒绝「正在生成 / 已有成品」，并且在源素材被删除时给出可读原因。

数据库用独立 SQLite，不触碰用户数据；FFmpeg 能力探测与任务调度都被打桩。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.db.models  # noqa: F401  注册全部 ORM 模型
from app.db.base import Base
from app.db.models.daily_frame import DailyFrame, DailyFrameCalendar, DailyFrameWork
from app.db.models.photo import FileType, Photo
from app.db.models.task import Task, TaskStatus, TaskType
from app.schemas.daily_frame import FilmCreate, FilmSettings
from app.service import daily_frame as service

pytestmark = [pytest.mark.smoke]


@pytest.fixture
def work_db(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'daily-frame-work.sqlite').as_posix()}")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        yield db
    engine.dispose()


@pytest.fixture
def owner(work_db):
    return uuid4()


@pytest.fixture
def calendar(work_db, owner):
    row = DailyFrameCalendar(owner_id=owner, timezone="Asia/Shanghai", locked=True, revision=1)
    work_db.add(row)
    work_db.commit()
    return row


@pytest.fixture(autouse=True)
def stub_render_and_worker(monkeypatch):
    """影片能力探测与后台任务调度都打桩，测试不依赖 FFmpeg 与 worker 进程。"""
    import app.service.daily_frame_render as render
    import app.service.task_manager as task_manager

    monkeypatch.setattr(render, "capabilities", lambda: {"available": True, "reason": ""})

    class _Worker:
        def start_worker_if_needed(self):  # pragma: no cover - 只验证被调用
            return None

    monkeypatch.setattr(task_manager.TaskManager, "get_instance", staticmethod(lambda: _Worker()))


def make_photo(db, owner, tmp_path, *, day, name="frame.jpg", deleted=False, mode="still"):
    path = tmp_path / name
    path.write_bytes(b"payload")
    photo = Photo(id=uuid4(), owner_id=owner, filename=name, file_path=str(path),
                  file_type=FileType.image, size=7, is_deleted=deleted,
                  photo_time=datetime(day.year, day.month, day.day, 10, 0, 0))
    db.add(photo)
    db.flush()
    frame = DailyFrame(id=uuid4(), owner_id=owner, day=day, photo_id=photo.id, mode=mode,
                       start_seconds=0, caption="", version=1, removed=False)
    db.add(frame)
    db.commit()
    return photo, frame


def film_payload(db, owner, day, **kwargs):
    """按当前选帧生成合法指纹的 FilmCreate。"""
    plan = service.composition(db, owner, FilmSettings(start_date=day, end_date=day))
    return FilmCreate(start_date=day, end_date=day, fingerprint=plan["fingerprint"], **kwargs)


# --- create_work -----------------------------------------------------


def test_create_work_refuses_when_the_renderer_is_unavailable(work_db, owner, calendar, monkeypatch):
    import app.service.daily_frame_render as render

    monkeypatch.setattr(render, "capabilities", lambda: {"available": False, "reason": "缺少 FFmpeg"})
    day = date.today() - timedelta(days=1)

    with pytest.raises(HTTPException) as error:
        service.create_work(work_db, owner, film_payload(work_db, owner, day))

    assert error.value.status_code == 503
    assert "FFmpeg" in error.value.detail


def test_create_work_rejects_a_stale_preview_fingerprint(work_db, owner, calendar, tmp_path):
    day = date.today() - timedelta(days=1)
    make_photo(work_db, owner, tmp_path, day=day)

    with pytest.raises(HTTPException) as error:
        service.create_work(work_db, owner, FilmCreate(start_date=day, end_date=day, fingerprint="0" * 64))

    assert error.value.status_code == 409
    assert "选帧已变化" in error.value.detail


def test_create_work_requires_an_explicit_skip_for_invalid_frames(work_db, owner, calendar, tmp_path):
    day = date.today() - timedelta(days=1)
    photo, _ = make_photo(work_db, owner, tmp_path, day=day)
    work_db.add(photo)
    work_db.query(DailyFrame).filter_by(owner_id=owner).update({"photo_id": photo.id})
    # 让源文件不可读 -> 该帧失效
    work_db.query(Photo).filter_by(id=photo.id).update({"is_deleted": True})
    work_db.commit()

    payload = film_payload(work_db, owner, day)
    with pytest.raises(HTTPException) as error:
        service.create_work(work_db, owner, payload)

    assert error.value.status_code == 400
    assert "失效素材" in error.value.detail


def test_create_work_queues_a_render_task(work_db, owner, calendar, tmp_path):
    day = date.today() - timedelta(days=1)
    make_photo(work_db, owner, tmp_path, day=day)

    work = service.create_work(work_db, owner, film_payload(work_db, owner, day))

    assert work.status == "queued"
    assert work.generation == 1
    assert work.task_id is not None
    task = work_db.get(Task, work.task_id)
    assert task.type == TaskType.RENDER_DAILY_FRAME.value
    assert task.status == TaskStatus.PENDING.value
    assert task.total_items == 1


def test_create_work_reuses_a_ready_work_with_an_existing_output(work_db, owner, calendar, tmp_path):
    day = date.today() - timedelta(days=1)
    make_photo(work_db, owner, tmp_path, day=day)
    work = service.create_work(work_db, owner, film_payload(work_db, owner, day))

    output = tmp_path / "out.mp4"
    output.write_bytes(b"video")
    work.status, work.output_path = "ready", str(output)
    work_db.commit()

    again = service.create_work(work_db, owner, film_payload(work_db, owner, day))

    assert again.id == work.id
    assert work_db.query(Task).count() == 1


# --- serialize_work --------------------------------------------------


def test_serialize_work_reports_missing_when_the_output_file_disappeared(work_db, owner, calendar, tmp_path):
    day = date.today() - timedelta(days=1)
    make_photo(work_db, owner, tmp_path, day=day)
    work = service.create_work(work_db, owner, film_payload(work_db, owner, day))
    work.status, work.output_path = "ready", str(tmp_path / "gone.mp4")
    work_db.commit()

    data = service.serialize_work(work_db, work)

    assert data["status"] == "missing"
    assert data["file_available"] is False


def test_serialize_work_follows_the_task_status(work_db, owner, calendar, tmp_path):
    day = date.today() - timedelta(days=1)
    make_photo(work_db, owner, tmp_path, day=day)
    work = service.create_work(work_db, owner, film_payload(work_db, owner, day))
    work_db.get(Task, work.task_id).status = TaskStatus.PROCESSING.value
    work_db.commit()

    assert service.serialize_work(work_db, work)["status"] == "processing"

    # 任务丢失时排队中的作品视为失败
    work.task_id = None
    work_db.commit()
    assert service.serialize_work(work_db, work)["status"] == "failed"


def test_serialize_work_detects_a_changed_calendar(work_db, owner, calendar, tmp_path):
    day = date.today() - timedelta(days=1)
    make_photo(work_db, owner, tmp_path, day=day)
    work = service.create_work(work_db, owner, film_payload(work_db, owner, day))
    output = tmp_path / "ready.mp4"
    output.write_bytes(b"video")
    work.status, work.output_path = "ready", str(output)
    work_db.commit()

    assert service.serialize_work(work_db, work)["calendar_changed"] is False

    work_db.query(DailyFrame).filter_by(owner_id=owner).update({"caption": "改过的说明"})
    work_db.commit()
    assert service.serialize_work(work_db, work)["calendar_changed"] is True


# --- stop_work -------------------------------------------------------


def test_stop_work_cancels_the_pending_task(work_db, owner, calendar, tmp_path):
    day = date.today() - timedelta(days=1)
    make_photo(work_db, owner, tmp_path, day=day)
    work = service.create_work(work_db, owner, film_payload(work_db, owner, day))

    service.stop_work(work_db, owner, work.id)
    work_db.refresh(work)

    assert work.status == "cancelled"
    assert work_db.get(Task, work.task_id).status == TaskStatus.CANCELLED.value


def test_stop_work_can_delete_a_work(work_db, owner, calendar, tmp_path):
    day = date.today() - timedelta(days=1)
    make_photo(work_db, owner, tmp_path, day=day)
    work = service.create_work(work_db, owner, film_payload(work_db, owner, day))

    service.stop_work(work_db, owner, work.id, delete=True)
    work_db.refresh(work)

    assert work.status == "deleted"
    assert work.deleted_at is not None

    with pytest.raises(HTTPException) as error:
        service.stop_work(work_db, owner, work.id)
    assert error.value.status_code == 404


# --- retry_work ------------------------------------------------------


def test_retry_work_refuses_while_the_work_is_still_running(work_db, owner, calendar, tmp_path):
    day = date.today() - timedelta(days=1)
    make_photo(work_db, owner, tmp_path, day=day)
    work = service.create_work(work_db, owner, film_payload(work_db, owner, day))

    with pytest.raises(HTTPException) as error:
        service.retry_work(work_db, owner, work.id)

    assert error.value.status_code == 409
    assert "正在生成" in error.value.detail


def test_retry_work_refuses_when_the_output_is_still_there(work_db, owner, calendar, tmp_path):
    day = date.today() - timedelta(days=1)
    make_photo(work_db, owner, tmp_path, day=day)
    work = service.create_work(work_db, owner, film_payload(work_db, owner, day))
    output = tmp_path / "done.mp4"
    output.write_bytes(b"video")
    work.status, work.output_path = "ready", str(output)
    work_db.commit()

    with pytest.raises(HTTPException) as error:
        service.retry_work(work_db, owner, work.id)

    assert error.value.status_code == 409
    assert "已经生成" in error.value.detail


def test_retry_work_reports_the_day_whose_source_disappeared(work_db, owner, calendar, tmp_path):
    day = date.today() - timedelta(days=1)
    photo, _ = make_photo(work_db, owner, tmp_path, day=day)
    work = service.create_work(work_db, owner, film_payload(work_db, owner, day))
    work.status = "failed"
    work_db.commit()
    work_db.query(Photo).filter_by(id=photo.id).update({"is_deleted": True})
    work_db.commit()

    with pytest.raises(HTTPException) as error:
        service.retry_work(work_db, owner, work.id)

    assert error.value.status_code == 400
    assert day.isoformat() in error.value.detail


def test_retry_work_queues_a_new_generation(work_db, owner, calendar, tmp_path):
    day = date.today() - timedelta(days=1)
    make_photo(work_db, owner, tmp_path, day=day)
    work = service.create_work(work_db, owner, film_payload(work_db, owner, day))
    work.status, work.error, work.processed_items = "failed", "boom", 0
    work_db.commit()
    first_task = work.task_id

    work = service.retry_work(work_db, owner, work.id)
    work_db.refresh(work)

    assert work.status == "queued"
    assert work.generation == 2
    assert work.error is None
    assert work.task_id != first_task
    assert work_db.query(Task).count() == 2

