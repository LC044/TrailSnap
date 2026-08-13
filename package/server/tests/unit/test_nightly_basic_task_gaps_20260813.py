"""Unit tests covering 2026-08-13 nightly coverage gap scan (round 3).

Modules exercised:
* app/service/tasks/basic.py -- BasicTaskStrategy.process_batch
  (file-not-found, pre-created photo UUID, existing photo by file_path,
   width / height filter rejection, motion photo, video ext, CPU failure),
  handle_completion (pre-created photo metadata upsert, new photo insert,
   color info write, downstream task scheduling).
"""
import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4, UUID

import pytest

from app.db.models.photo import FileType
from app.db.models.task import TaskType, TaskStatus
from app.service.tasks import basic as basic_task
from app.service.tasks.basic import BasicTaskStrategy


pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


def _task(**kw):
    base = {
        "id": uuid4(),
        "type": TaskType.PROCESS_BASIC,
        "owner_id": uuid4(),
        "payload": {"file_path": "/tmp/x.jpg", "user_id": str(uuid4())},
    }
    base.update(kw)
    return SimpleNamespace(**base)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _cpu_ok(width=1920, height=1080, filename="x.jpg", size=1024, duration=0.0,
            md5_hash="abc", is_motion_photo=False, photo_time=None):
    return {
        "success": True,
        "thumb_path": f"/thumbs/{filename}",
        "meta": {"photo_time": photo_time or datetime(2025, 8, 1, 12, 0), "exif_info": "{}"},
        "size": size,
        "width": width,
        "height": height,
        "duration": duration,
        "file_name": filename,
        "photo_create_data": None,
        "is_motion_photo": is_motion_photo,
        "md5_hash": md5_hash,
        "color_info": None,
    }


def _make_user_config(min_width=0, min_height=0, enable=False, ai_url="http://ai:8001"):
    cfg = MagicMock()
    cfg.filter.enable = enable
    cfg.filter.min_width = min_width
    cfg.filter.min_height = min_height
    cfg.ai.ai_api_url = ai_url
    return cfg


def _make_worker():
    w = MagicMock()
    w.thread_pool = ThreadPoolExecutor(max_workers=1)
    return w


# ===========================================================================
# Basic metadata
# ===========================================================================


def test_basic_strategy_task_category_is_cpu():
    s = BasicTaskStrategy()
    assert s.task_category == "CPU"


def test_basic_strategy_process_is_noop():
    """The single-task ``process`` is a no-op stub; only ``process_batch`` is
    wired in the worker for this strategy."""
    res = _run(BasicTaskStrategy().process(MagicMock(), MagicMock(), MagicMock()))
    assert res is None


def test_release_resources_is_noop():
    assert basic_task.release_resources() is None


# ===========================================================================
# process_batch()
# ===========================================================================


def test_process_batch_empty_returns_empty():
    strategy = BasicTaskStrategy()
    worker = _make_worker()
    db = MagicMock()
    res = _run(strategy.process_batch(worker, [], db))
    assert res == []


def test_process_batch_skips_missing_file(tmp_path):
    """When ``file_path`` does not exist on disk, the task result must be a
    ``completed: skipped`` entry rather than raising."""
    db = MagicMock()
    strategy = BasicTaskStrategy()
    worker = _make_worker()
    worker.thread_pool = None  # run_in_executor will use default

    task = _task(payload={"file_path": "/no/such/path.jpg", "user_id": str(uuid4())})
    with patch("app.service.tasks.basic.os.path.exists", return_value=False):
        res = _run(strategy.process_batch(worker, [task], db))
    assert len(res) == 1
    assert res[0]["status"] == "completed"
    assert res[0]["result"]["status"] == "skipped"
    assert res[0]["result"]["reason"] == "file not found"


def test_process_batch_existing_photo_marks_pre_created(tmp_path, monkeypatch):
    """When DB has a photo with the same file_path, ``is_pre_created`` must
    be set on the batch job payload so the upsert branch runs later."""
    db = MagicMock()
    strategy = BasicTaskStrategy()
    worker = _make_worker()
    existing_id = uuid4()

    photo_file = tmp_path / "x.jpg"
    photo_file.write_bytes(b"x")

    def _check_existing(*a, **kw):
        return (existing_id,)

    chain = MagicMock()
    chain.filter.return_value = chain
    chain.first.side_effect = _check_existing

    def _query(model):
        chain._called_with = model
        return chain

    db.query.side_effect = _query

    user_id = str(uuid4())
    task = _task(payload={"file_path": str(photo_file), "user_id": user_id})
    fake = _cpu_ok(filename="x.jpg")

    monkeypatch.setattr("app.service.tasks.basic.os.path.exists", lambda p: True)
    monkeypatch.setattr(
        "app.service.tasks.basic.config_manager.get_user_config",
        lambda *a, **kw: _make_user_config(),
    )

    async def _fake_run_in_executor(_pool, fn, jobs):
        return [fn(j) for j in jobs]

    fake_executor = MagicMock(side_effect=_fake_run_in_executor)
    monkeypatch.setattr(asyncio.AbstractEventLoop, "run_in_executor", fake_executor)
    monkeypatch.setattr("app.service.tasks.basic.process_basic_cpu_batch_job", lambda jobs: [_cpu_ok() for _ in jobs])

    res = _run(strategy.process_batch(worker, [task], db))
    assert res[0]["status"] == "completed"
    assert res[0]["result"]["photo_create_data"]["is_pre_created"] is True
    assert res[0]["result"]["photo_create_data"]["photo_id"] == existing_id


def test_process_batch_payload_photo_id_pre_created(tmp_path, monkeypatch):
    db = MagicMock()
    strategy = BasicTaskStrategy()
    worker = _make_worker()

    photo_file = tmp_path / "x.jpg"
    photo_file.write_bytes(b"x")
    pre_created_id = uuid4()

    db.query.return_value.filter.return_value.first.return_value = None

    monkeypatch.setattr("app.service.tasks.basic.os.path.exists", lambda p: True)
    monkeypatch.setattr(
        "app.service.tasks.basic.config_manager.get_user_config",
        lambda *a, **kw: _make_user_config(),
    )
    monkeypatch.setattr(
        "app.service.tasks.basic.process_basic_cpu_batch_job",
        lambda jobs: [_cpu_ok() for _ in jobs],
    )

    task = _task(payload={"file_path": str(photo_file), "user_id": str(uuid4()), "photo_id": str(pre_created_id)})
    res = _run(strategy.process_batch(worker, [task], db))
    assert res[0]["status"] == "completed"
    assert res[0]["result"]["photo_create_data"]["is_pre_created"] is True
    assert res[0]["result"]["photo_create_data"]["photo_id"] == pre_created_id


def test_process_batch_filters_by_min_width(tmp_path, monkeypatch):
    db = MagicMock()
    strategy = BasicTaskStrategy()
    worker = _make_worker()

    photo_file = tmp_path / "x.jpg"
    photo_file.write_bytes(b"x")

    db.query.return_value.filter.return_value.first.return_value = None

    monkeypatch.setattr("app.service.tasks.basic.os.path.exists", lambda p: True)
    monkeypatch.setattr(
        "app.service.tasks.basic.config_manager.get_user_config",
        lambda *a, **kw: _make_user_config(min_width=4000, enable=True),
    )
    monkeypatch.setattr(
        "app.service.tasks.basic.process_basic_cpu_batch_job",
        lambda jobs: [_cpu_ok(width=800, height=600) for _ in jobs],
    )

    task = _task(payload={"file_path": str(photo_file), "user_id": str(uuid4())})
    res = _run(strategy.process_batch(worker, [task], db))
    assert res[0]["status"] == "completed"
    assert res[0]["result"]["status"] == "skipped"
    assert res[0]["result"]["reason"] == "filtered_by_width"


def test_process_batch_filters_by_min_height(tmp_path, monkeypatch):
    db = MagicMock()
    strategy = BasicTaskStrategy()
    worker = _make_worker()

    photo_file = tmp_path / "x.jpg"
    photo_file.write_bytes(b"x")

    db.query.return_value.filter.return_value.first.return_value = None

    monkeypatch.setattr("app.service.tasks.basic.os.path.exists", lambda p: True)
    monkeypatch.setattr(
        "app.service.tasks.basic.config_manager.get_user_config",
        lambda *a, **kw: _make_user_config(min_height=4000, enable=True),
    )
    monkeypatch.setattr(
        "app.service.tasks.basic.process_basic_cpu_batch_job",
        lambda jobs: [_cpu_ok(width=1920, height=600) for _ in jobs],
    )

    task = _task(payload={"file_path": str(photo_file), "user_id": str(uuid4())})
    res = _run(strategy.process_batch(worker, [task], db))
    assert res[0]["result"]["status"] == "skipped"
    assert res[0]["result"]["reason"] == "filtered_by_height"


def test_process_batch_marks_motion_photo_as_live(tmp_path, monkeypatch):
    db = MagicMock()
    strategy = BasicTaskStrategy()
    worker = _make_worker()

    photo_file = tmp_path / "x.jpg"
    photo_file.write_bytes(b"x")

    db.query.return_value.filter.return_value.first.return_value = None

    monkeypatch.setattr("app.service.tasks.basic.os.path.exists", lambda p: True)
    monkeypatch.setattr(
        "app.service.tasks.basic.config_manager.get_user_config",
        lambda *a, **kw: _make_user_config(),
    )
    monkeypatch.setattr(
        "app.service.tasks.basic.process_basic_cpu_batch_job",
        lambda jobs: [_cpu_ok(is_motion_photo=True) for _ in jobs],
    )

    task = _task(payload={"file_path": str(photo_file), "user_id": str(uuid4())})
    res = _run(strategy.process_batch(worker, [task], db))
    photo = res[0]["result"]["photo_create_data"]["photo"]
    assert photo.file_type == FileType.live_photo


def test_process_batch_marks_video_extension(tmp_path, monkeypatch):
    db = MagicMock()
    strategy = BasicTaskStrategy()
    worker = _make_worker()

    photo_file = tmp_path / "x.mp4"
    photo_file.write_bytes(b"x")

    db.query.return_value.filter.return_value.first.return_value = None

    monkeypatch.setattr("app.service.tasks.basic.os.path.exists", lambda p: True)
    monkeypatch.setattr(
        "app.service.tasks.basic.config_manager.get_user_config",
        lambda *a, **kw: _make_user_config(),
    )
    monkeypatch.setattr(
        "app.service.tasks.basic.process_basic_cpu_batch_job",
        lambda jobs: [_cpu_ok(filename="x.mp4") for _ in jobs],
    )

    task = _task(payload={"file_path": str(photo_file), "user_id": str(uuid4())})
    res = _run(strategy.process_batch(worker, [task], db))
    photo = res[0]["result"]["photo_create_data"]["photo"]
    assert photo.file_type == FileType.video


def test_process_batch_cpu_failure_reported(tmp_path, monkeypatch):
    db = MagicMock()
    strategy = BasicTaskStrategy()
    worker = _make_worker()

    photo_file = tmp_path / "x.jpg"
    photo_file.write_bytes(b"x")

    db.query.return_value.filter.return_value.first.return_value = None

    monkeypatch.setattr("app.service.tasks.basic.os.path.exists", lambda p: True)
    monkeypatch.setattr(
        "app.service.tasks.basic.config_manager.get_user_config",
        lambda *a, **kw: _make_user_config(),
    )
    monkeypatch.setattr(
        "app.service.tasks.basic.process_basic_cpu_batch_job",
        lambda jobs: [{"success": False, "error": "boom"} for _ in jobs],
    )

    task = _task(payload={"file_path": str(photo_file), "user_id": str(uuid4())})
    res = _run(strategy.process_batch(worker, [task], db))
    assert res[0]["status"] == "failed"
    assert res[0]["error"] == "boom"


def test_process_batch_payload_live_photo_flag_overrides(tmp_path, monkeypatch):
    """When ``is_live_photo`` is set in the payload, the produced PhotoCreate
    must use FileType.live_photo regardless of motion-photo detection."""
    db = MagicMock()
    strategy = BasicTaskStrategy()
    worker = _make_worker()

    photo_file = tmp_path / "x.jpg"
    photo_file.write_bytes(b"x")

    db.query.return_value.filter.return_value.first.return_value = None

    monkeypatch.setattr("app.service.tasks.basic.os.path.exists", lambda p: True)
    monkeypatch.setattr(
        "app.service.tasks.basic.config_manager.get_user_config",
        lambda *a, **kw: _make_user_config(),
    )
    monkeypatch.setattr(
        "app.service.tasks.basic.process_basic_cpu_batch_job",
        lambda jobs: [_cpu_ok() for _ in jobs],
    )

    task = _task(payload={
        "file_path": str(photo_file),
        "user_id": str(uuid4()),
        "is_live_photo": True,
    })
    res = _run(strategy.process_batch(worker, [task], db))
    photo = res[0]["result"]["photo_create_data"]["photo"]
    assert photo.file_type == FileType.live_photo


# ===========================================================================
# handle_completion()
# ===========================================================================


def _complete_item(photo_id, user_id, file_path, is_pre_created=False, color_info=None, metadata=None):
    photo_create = SimpleNamespace(
        file_type=FileType.image,
        size=100,
        width=100,
        height=100,
        duration=0,
        filename="x.jpg",
        photo_time=datetime(2025, 8, 1),
        md5="abc",
    )
    metadata_create = SimpleNamespace(exif_info="{}")
    return {
        "task_id": uuid4(),
        "status": TaskStatus.COMPLETED,
        "result": {
            "photo_create_data": {
                "photo": photo_create,
                "metadata": metadata_create,
                "photo_id": photo_id,
                "file_path": file_path,
                "user_id": user_id,
                "color_info": color_info,
                "is_pre_created": is_pre_created,
            }
        },
    }


def test_handle_completion_empty_returns_immediately():
    strategy = BasicTaskStrategy()
    db = MagicMock()
    _run(strategy.handle_completion(MagicMock(), [], db))
    db.add_all.assert_not_called()


def test_handle_completion_new_photos_branch_calls_batch_create(monkeypatch):
    strategy = BasicTaskStrategy()
    worker = _make_worker()
    worker.scan_status = {"added": 0, "processed_files": 0}
    db = MagicMock()

    photo_id = uuid4()
    user_id = uuid4()
    item = _complete_item(photo_id, user_id, "/tmp/x.jpg", is_pre_created=False)

    monkeypatch.setattr(
        "app.service.tasks.basic.app.crud.photo.batch_create_photos",
        lambda db, photos, user_id=None: [photo_id],
    )

    _run(strategy.handle_completion(worker, [item], db))
    db.add_all.assert_called_once()  # IndexLogs added in bulk
    assert worker.scan_status["added"] == 1
    assert worker.scan_status["processed_files"] == 1


def test_handle_completion_pre_created_upserts_metadata(monkeypatch):
    strategy = BasicTaskStrategy()
    worker = _make_worker()
    db = MagicMock()

    photo_id = uuid4()
    user_id = uuid4()

    # No existing PhotoMetadata row -> create path
    db.query.return_value.filter.return_value.first.return_value = None

    item = _complete_item(photo_id, user_id, "/tmp/x.jpg", is_pre_created=True)
    _run(strategy.handle_completion(worker, [item], db))
    db.add.assert_called()  # at least PhotoMetadata + Task entities


def test_handle_completion_color_info_writes_photocolor(monkeypatch):
    strategy = BasicTaskStrategy()
    worker = _make_worker()
    db = MagicMock()

    photo_id = uuid4()
    user_id = uuid4()

    color_info = {
        "dominant_colors": ["#ff0000", "#00ff00"],
        "brightness": 0.5,
        "saturation": 0.6,
        "emotion_hint": "warm",
    }

    # No existing PhotoMetadata row
    db.query.return_value.filter.return_value.first.return_value = None

    item = _complete_item(photo_id, user_id, "/tmp/x.jpg", is_pre_created=False, color_info=color_info)
    monkeypatch.setattr(
        "app.service.tasks.basic.app.crud.photo.batch_create_photos",
        lambda db, photos, user_id=None: [photo_id],
    )
    _run(strategy.handle_completion(worker, [item], db))
    # Multiple db.add calls: IndexLog, PhotoColor, downstream Tasks
    assert db.add.call_count >= 5


def test_handle_completion_skips_color_when_dominant_colors_missing(monkeypatch):
    strategy = BasicTaskStrategy()
    worker = _make_worker()
    db = MagicMock()

    photo_id = uuid4()
    user_id = uuid4()

    color_info = {"brightness": 0.5}  # no dominant_colors

    db.query.return_value.filter.return_value.first.return_value = None
    monkeypatch.setattr(
        "app.service.tasks.basic.app.crud.photo.batch_create_photos",
        lambda db, photos, user_id=None: [photo_id],
    )

    item = _complete_item(photo_id, user_id, "/tmp/x.jpg", color_info=color_info)
    _run(strategy.handle_completion(worker, [item], db))
    # PhotoColor not added when dominant_colors absent -- still adds downstream tasks
    add_calls = [c.args[0] for c in db.add.call_args_list]
    from app.db.models.photo_color import PhotoColor
    assert not any(isinstance(c, PhotoColor) for c in add_calls)
