from __future__ import annotations
import json
"""Unit tests covering 2026-08-18 nightly coverage gap scan.

Module exercised:
* app/service/tasks/basic.py -- BasicTaskStrategy.process_batch and
  BasicTaskStrategy.handle_completion (large uncovered surface reported
  by the scan, particularly the filter / photo_create_data / pre_created
  paths in handle_completion).
""
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest


pytestmark = [pytest.mark.smoke]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _task(**kw):
    base = {
        "id": uuid4(),
        "type": None,
        "owner_id": uuid4(),
        "payload": {},
    }
    base.update(kw)
    return SimpleNamespace(**base)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _strategy():
    from app.service.tasks.basic import BasicTaskStrategy
    return BasicTaskStrategy()


def _patch_run_in_executor():
    """Make loop.run_in_executor await the cpu-batch stub directly.

    `loop.run_in_executor(executor, func, *args)` calls
    `executor.submit(func, *args)` and awaits the returned Future. Our
    MagicMock thread_pool returns a non-Future, which crashes asyncio. We
    patch the call site so that awaiting just runs the stub synchronously.
    """

    async def _run_in_executor(_executor, func, *args, **kwargs):
        return func(*args, **kwargs)

    return patch(
        "asyncio.get_running_loop",
        return_value=SimpleNamespace(run_in_executor=_run_in_executor),
    )


def _ok_res(file_path="x.jpg", width=100, height=100):
    return {
        "success": True,
        "thumb_path": "/tmp/thumb",
        "meta": {"photo_time": None, "exif_info": "{}"},
        "size": 1024,
        "width": width,
        "height": height,
        "duration": None,
        "file_name": file_path.rsplit("/", 1)[-1],
        "photo_create_data": None,
        "is_motion_photo": False,
        "md5_hash": "deadbeef",
        "color_info": None,
    }


def _fail_res(error="boom"):
    return {"success": False, "error": error}


def _photo_create_data(photo_id, user_id, is_pre_created=False, color_info=None, exif_info=None):
    from app.db.models.photo import FileType
    from app.schemas.metadata import PhotoMetadataCreate
    from app.schemas.photo import PhotoCreate
    return {
        "photo": PhotoCreate(
            file_type=FileType.image, size=1024, width=100, height=100, duration=None,
            filename="p.jpg", photo_time=None, md5="x",
        ),
        "metadata": PhotoMetadataCreate(exif_info=exif_info),
        "photo_id": photo_id,
        "file_path": "/tmp/p.jpg",
        "user_id": user_id,
        "color_info": color_info,
        "is_pre_created": is_pre_created,
    }


def _config(filter_enable=False, min_width=0, min_height=0):
    return patch(
        "app.service.tasks.basic.config_manager.get_user_config",
        return_value=SimpleNamespace(
            filter=SimpleNamespace(enable=filter_enable, min_width=min_width, min_height=min_height),
        ),
    )


# ===========================================================================
# BasicTaskStrategy.process_batch
# ===========================================================================


def test_process_batch_skips_task_with_missing_file(tmp_path):
    strategy = _strategy()
    db = MagicMock()
    worker = MagicMock()
    worker.thread_pool = MagicMock()
    worker.scan_status = {"added": 0, "processed_files": 0}

    task = _task(payload={"file_path": "/no/such/file.jpg", "user_id": str(uuid4())})

    with patch("app.service.tasks.basic.process_basic_cpu_batch_job") as cpu_job:
        results = _run(strategy.process_batch(worker, [task], db))
    assert results[0]["status"] == "completed"
    assert results[0]["result"]["reason"] == "file not found"
    cpu_job.assert_not_called()


def test_process_batch_empty_after_skips_returns_only_results(tmp_path):
    strategy = _strategy()
    db = MagicMock()
    worker = MagicMock()
    worker.thread_pool = MagicMock()
    worker.scan_status = {"added": 0, "processed_files": 0}

    bad = _task(payload={"file_path": "/no/such/file.jpg", "user_id": str(uuid4())})

    with patch("app.service.tasks.basic.process_basic_cpu_batch_job") as cpu_job:
        results = _run(strategy.process_batch(worker, [bad], db))

    cpu_job.assert_not_called()
    assert len(results) == 1


def test_process_batch_happy_path_emits_photo_create_data(tmp_path):
    strategy = _strategy()
    db = MagicMock()
    worker = MagicMock()
    worker.thread_pool = MagicMock()
    worker.scan_status = {"added": 0, "processed_files": 0}
    file_path = str(tmp_path / "real.jpg")
    open(file_path, "wb").close()

    user_id = uuid4()
    task = _task(owner_id=user_id, payload={"file_path": file_path, "user_id": str(user_id)})

    with _patch_run_in_executor(), \
            patch("app.service.tasks.basic.process_basic_cpu_batch_job",
                  lambda jobs: [_ok_res(file_path=file_path)]), \
            _config():
        results = _run(strategy.process_batch(worker, [task], db))

    assert len(results) == 1
    assert results[0]["status"] == "completed"
    payload = results[0]["result"]["photo_create_data"]
    assert payload["file_path"] == file_path
    assert payload["user_id"] == str(user_id)
    assert payload["photo"].width == 100


def test_process_batch_failure_passes_error_through(tmp_path):
    strategy = _strategy()
    db = MagicMock()
    worker = MagicMock()
    worker.thread_pool = MagicMock()
    worker.scan_status = {"added": 0, "processed_files": 0}
    file_path = str(tmp_path / "real.jpg")
    open(file_path, "wb").close()

    user_id = uuid4()
    task = _task(owner_id=user_id, payload={"file_path": file_path, "user_id": str(user_id)})

    with _patch_run_in_executor(), \
            patch("app.service.tasks.basic.process_basic_cpu_batch_job",
                  lambda jobs: [_fail_res(error="decode failed")]), \
            _config():
        results = _run(strategy.process_batch(worker, [task], db))

    assert results[0]["status"] == "failed"
    assert results[0]["error"] == "decode failed"


def test_process_batch_filter_disabled_unknown_dimensions_does_not_skip(tmp_path):
    strategy = _strategy()
    db = MagicMock()
    worker = MagicMock()
    worker.thread_pool = MagicMock()
    worker.scan_status = {"added": 0, "processed_files": 0}
    file_path = str(tmp_path / "real.jpg")
    open(file_path, "wb").close()

    task = _task(owner_id=uuid4(), payload={"file_path": file_path, "user_id": str(uuid4())})

    with _patch_run_in_executor(), \
            patch("app.service.tasks.basic.process_basic_cpu_batch_job",
                  lambda jobs: [_ok_res(file_path=file_path, width=None, height=None)]), \
            _config():
        results = _run(strategy.process_batch(worker, [task], db))

    assert results[0]["status"] == "completed"
    assert "photo_create_data" in results[0]["result"]


def test_process_batch_filter_enabled_skips_by_min_width(tmp_path):
    strategy = _strategy()
    db = MagicMock()
    worker = MagicMock()
    worker.thread_pool = MagicMock()
    worker.scan_status = {"added": 0, "processed_files": 0}
    file_path = str(tmp_path / "small.jpg")
    open(file_path, "wb").close()

    task = _task(owner_id=uuid4(), payload={"file_path": file_path, "user_id": str(uuid4())})

    with _patch_run_in_executor(), \
            patch("app.service.tasks.basic.process_basic_cpu_batch_job",
                  lambda jobs: [_ok_res(file_path=file_path, width=50, height=200)]), \
            _config(filter_enable=True, min_width=100):
        results = _run(strategy.process_batch(worker, [task], db))

    assert results[0]["result"]["status"] == "skipped"
    assert results[0]["result"]["reason"] == "filtered_by_width"


def test_process_batch_filter_enabled_skips_by_min_height(tmp_path):
    strategy = _strategy()
    db = MagicMock()
    worker = MagicMock()
    worker.thread_pool = MagicMock()
    worker.scan_status = {"added": 0, "processed_files": 0}
    file_path = str(tmp_path / "small.jpg")
    open(file_path, "wb").close()

    task = _task(owner_id=uuid4(), payload={"file_path": file_path, "user_id": str(uuid4())})

    with _patch_run_in_executor(), \
            patch("app.service.tasks.basic.process_basic_cpu_batch_job",
                  lambda jobs: [_ok_res(file_path=file_path, width=200, height=50)]), \
            _config(filter_enable=True, min_height=100):
        results = _run(strategy.process_batch(worker, [task], db))

    assert results[0]["result"]["reason"] == "filtered_by_height"


def test_process_batch_filter_enabled_unknown_dimensions_does_not_skip(tmp_path):
    """Filter enabled but dimensions are None -- do not raise TypeError."""
    strategy = _strategy()
    db = MagicMock()
    worker = MagicMock()
    worker.thread_pool = MagicMock()
    worker.scan_status = {"added": 0, "processed_files": 0}
    file_path = str(tmp_path / "real.jpg")
    open(file_path, "wb").close()

    task = _task(owner_id=uuid4(), payload={"file_path": file_path, "user_id": str(uuid4())})

    with _patch_run_in_executor(), \
            patch("app.service.tasks.basic.process_basic_cpu_batch_job",
                  lambda jobs: [_ok_res(file_path=file_path, width=None, height=None)]), \
            _config(filter_enable=True, min_width=100, min_height=100):
        results = _run(strategy.process_batch(worker, [task], db))

    assert "photo_create_data" in results[0]["result"]


def test_process_batch_video_ext_uses_video_file_type(tmp_path):
    strategy = _strategy()
    db = MagicMock()
    worker = MagicMock()
    worker.thread_pool = MagicMock()
    worker.scan_status = {"added": 0, "processed_files": 0}
    file_path = str(tmp_path / "clip.mp4")
    open(file_path, "wb").close()

    task = _task(owner_id=uuid4(), payload={"file_path": file_path, "user_id": str(uuid4())})

    with _patch_run_in_executor(), \
            patch("app.service.tasks.basic.process_basic_cpu_batch_job",
                  lambda jobs: [_ok_res(file_path=file_path)]), \
            _config():
        from app.db.models.photo import FileType
        results = _run(strategy.process_batch(worker, [task], db))

    assert results[0]["result"]["photo_create_data"]["photo"].file_type == FileType.video


def test_process_batch_motion_photo_flag_overrides_ext(tmp_path):
    strategy = _strategy()
    db = MagicMock()
    worker = MagicMock()
    worker.thread_pool = MagicMock()
    worker.scan_status = {"added": 0, "processed_files": 0}
    file_path = str(tmp_path / "pic.jpg")
    open(file_path, "wb").close()

    task = _task(owner_id=uuid4(), payload={"file_path": file_path, "user_id": str(uuid4())})

    def _res_with_motion(jobs):
        res = _ok_res(file_path=file_path)
        res["is_motion_photo"] = True
        return [res]

    with _patch_run_in_executor(), \
            patch("app.service.tasks.basic.process_basic_cpu_batch_job", _res_with_motion), \
            _config():
        from app.db.models.photo import FileType
        results = _run(strategy.process_batch(worker, [task], db))

    assert results[0]["result"]["photo_create_data"]["photo"].file_type == FileType.live_photo


def test_process_batch_payload_photo_id_is_reused(tmp_path):
    strategy = _strategy()
    db = MagicMock()
    worker = MagicMock()
    worker.thread_pool = MagicMock()
    worker.scan_status = {"added": 0, "processed_files": 0}
    file_path = str(tmp_path / "p.jpg")
    open(file_path, "wb").close()
    pre_id = uuid4()

    task = _task(
        owner_id=uuid4(),
        payload={"file_path": file_path, "user_id": str(uuid4()), "photo_id": str(pre_id)},
    )

    with _patch_run_in_executor(), \
            patch("app.service.tasks.basic.process_basic_cpu_batch_job",
                  lambda jobs: [_ok_res(file_path=file_path)]), \
            _config():
        results = _run(strategy.process_batch(worker, [task], db))

    payload = results[0]["result"]["photo_create_data"]
    assert str(payload["photo_id"]) == str(pre_id)
    assert payload["is_pre_created"] is True


def test_process_batch_invalid_payload_photo_id_falls_back(tmp_path):
    strategy = _strategy()
    db = MagicMock()
    # Ensure no pre-existing photo is found by DB lookup.
    db.query.return_value.filter.return_value.first.return_value = None
    worker = MagicMock()
    worker.thread_pool = MagicMock()
    worker.scan_status = {"added": 0, "processed_files": 0}
    file_path = str(tmp_path / "p.jpg")
    open(file_path, "wb").close()

    task = _task(
        owner_id=uuid4(),
        payload={"file_path": file_path, "user_id": str(uuid4()), "photo_id": "not-a-uuid"},
    )

    with _patch_run_in_executor(), \
            patch("app.service.tasks.basic.process_basic_cpu_batch_job",
                  lambda jobs: [_ok_res(file_path=file_path)]), \
            _config():
        results = _run(strategy.process_batch(worker, [task], db))

    payload = results[0]["result"]["photo_create_data"]
    assert payload["is_pre_created"] is False


def test_process_batch_existing_photo_reuses_id_when_payload_missing(tmp_path):
    strategy = _strategy()
    db = MagicMock()
    worker = MagicMock()
    worker.thread_pool = MagicMock()
    worker.scan_status = {"added": 0, "processed_files": 0}
    file_path = str(tmp_path / "p.jpg")
    open(file_path, "wb").close()

    existing_id = uuid4()
    chain = db.query.return_value
    chain.filter.return_value.first.return_value = (existing_id,)

    task = _task(
        owner_id=uuid4(),
        payload={"file_path": file_path, "user_id": str(uuid4())},
    )

    with _patch_run_in_executor(), \
            patch("app.service.tasks.basic.process_basic_cpu_batch_job",
                  lambda jobs: [_ok_res(file_path=file_path)]), \
            _config():
        results = _run(strategy.process_batch(worker, [task], db))

    payload = results[0]["result"]["photo_create_data"]
    assert str(payload["photo_id"]) == str(existing_id)
    assert payload["is_pre_created"] is True


# ===========================================================================
# BasicTaskStrategy.handle_completion
# ===========================================================================


def test_handle_completion_inserts_new_photos_and_logs(monkeypatch):
    strategy = _strategy()
    db = MagicMock()
    worker = MagicMock()
    worker.scan_status = {"added": 0, "processed_files": 0}

    photo_id = uuid4()
    user_id = str(uuid4())
    item = {
        "status": "completed",
        "task_id": uuid4(),
        "result": {
            "photo_create_data": _photo_create_data(photo_id, user_id),
        },
    }

    inserted = {str(photo_id)}
    monkeypatch.setattr(
        "app.crud.photo.batch_create_photos",
        lambda *a, **kw: inserted,
    )
    monkeypatch.setattr(
        "app.service.tasks.basic.config_manager.get_user_config",
        lambda *a, **kw: SimpleNamespace(filter=SimpleNamespace(enable=False, min_width=0, min_height=0)),
    )

    _run(strategy.handle_completion(worker, [item], db))
    db.add_all.assert_called_once()
    assert worker.scan_status["added"] == 1


def test_handle_completion_pre_created_inserts_photo_metadata(monkeypatch):
    strategy = _strategy()
    db = MagicMock()
    chain = db.query.return_value
    chain.filter.return_value.first.return_value = None
    worker = MagicMock()
    worker.scan_status = {"added": 0, "processed_files": 0}

    photo_id = uuid4()
    user_id = str(uuid4())
    item = {
        "status": "completed",
        "task_id": uuid4(),
        "result": {
            "photo_create_data": _photo_create_data(
                photo_id, user_id, is_pre_created=True, exif_info=json.dumps({"Make": "Canon"}),
            ),
        },
    }

    added_calls = []

    def _add(obj):
        added_calls.append(obj)

    db.add.side_effect = _add

    _run(strategy.handle_completion(worker, [item], db))

    added = [c for c in added_calls if type(c).__name__ == "PhotoMetadata"]
    assert len(added) == 1
    assert added[0].photo_id == photo_id
    assert worker.scan_status["added"] == 0


def test_handle_completion_skips_metadata_when_no_metadata_schema():
    strategy = _strategy()
    db = MagicMock()
    worker = MagicMock()
    worker.scan_status = {"added": 0, "processed_files": 0}

    photo_id = uuid4()
    user_id = str(uuid4())
    data = _photo_create_data(photo_id, user_id, is_pre_created=True)
    data["metadata"] = None

    item = {
        "status": "completed",
        "task_id": uuid4(),
        "result": {"photo_create_data": data},
    }

    added_types = []
    db.add.side_effect = lambda obj: added_types.append(type(obj).__name__)

    _run(strategy.handle_completion(worker, [item], db))
    # No PhotoMetadata insert but downstream Task rows are still dispatched.
    assert "PhotoMetadata" not in added_types
    assert "Task" in added_types


def test_handle_completion_pre_existing_metadata_with_exif_is_not_overwritten(monkeypatch):
    strategy = _strategy()
    db = MagicMock()
    chain = db.query.return_value
    chain.filter.return_value.first.return_value = SimpleNamespace(exif_info=json.dumps({"existing": True}))
    worker = MagicMock()
    worker.scan_status = {"added": 0, "processed_files": 0}

    photo_id = uuid4()
    user_id = str(uuid4())
    item = {
        "status": "completed",
        "task_id": uuid4(),
        "result": {
            "photo_create_data": _photo_create_data(
                photo_id, user_id, is_pre_created=True, exif_info=json.dumps({"new": True}),
            ),
        },
    }

    added_types = []
    db.add.side_effect = lambda obj: added_types.append(type(obj).__name__)

    _run(strategy.handle_completion(worker, [item], db))
    # No PhotoMetadata insert -- existing one already has exif_info.
    # Downstream Task rows are still dispatched.
    assert "PhotoMetadata" not in added_types
    assert "Task" in added_types


def test_handle_completion_color_info_persisted_only_once(monkeypatch):
    strategy = _strategy()
    db = MagicMock()
    color_filter = MagicMock()
    # existing PhotoColor record found -> existing_color must be truthy so the
    # handler skips creating a new one. SimpleNamespace(id=1) is truthy.
    color_filter.first.return_value = SimpleNamespace(id=1)
    db.query.return_value.filter.return_value = color_filter
    worker = MagicMock()
    worker.scan_status = {"added": 0, "processed_files": 0}

    photo_id = uuid4()
    user_id = str(uuid4())
    item = {
        "status": "completed",
        "task_id": uuid4(),
        "result": {
            "photo_create_data": _photo_create_data(
                photo_id, user_id,
                color_info={"dominant_colors": ["#fff"], "brightness": 100, "saturation": 0.5, "emotion_hint": "calm"},
            ),
        },
    }

    inserted = {str(photo_id)}
    monkeypatch.setattr(
        "app.crud.photo.batch_create_photos",
        lambda *a, **kw: inserted,
    )

    added_types = []
    db.add.side_effect = lambda obj: added_types.append(type(obj).__name__)

    _run(strategy.handle_completion(worker, [item], db))
    # No PhotoColor added because existing record was found.
    assert "PhotoColor" not in added_types


def test_handle_completion_color_info_inserted_for_new_color(monkeypatch):
    strategy = _strategy()
    db = MagicMock()
    color_filter = MagicMock()
    # No existing color record found -> existing_color is None so the handler
    # proceeds to create a new PhotoColor row.
    color_filter.first.return_value = None
    db.query.return_value.filter.return_value = color_filter
    worker = MagicMock()
    worker.scan_status = {"added": 0, "processed_files": 0}

    photo_id = uuid4()
    user_id = str(uuid4())
    item = {
        "status": "completed",
        "task_id": uuid4(),
        "result": {
            "photo_create_data": _photo_create_data(
                photo_id, user_id,
                color_info={"dominant_colors": ["#fff"], "brightness": 100, "saturation": 0.5, "emotion_hint": "calm"},
            ),
        },
    }

    inserted = {str(photo_id)}
    monkeypatch.setattr(
        "app.crud.photo.batch_create_photos",
        lambda *a, **kw: inserted,
    )

    added_types = []
    db.add.side_effect = lambda obj: added_types.append(type(obj).__name__)

    _run(strategy.handle_completion(worker, [item], db))
    assert "PhotoColor" in added_types


def test_handle_completion_dispatches_downstream_tasks(monkeypatch):
    strategy = _strategy()
    db = MagicMock()
    worker = MagicMock()
    worker.scan_status = {"added": 0, "processed_files": 0}

    photo_id = uuid4()
    user_id = str(uuid4())
    item = {
        "status": "completed",
        "task_id": uuid4(),
        "result": {
            "photo_create_data": _photo_create_data(photo_id, user_id),
        },
    }

    inserted = {str(photo_id)}
    monkeypatch.setattr(
        "app.crud.photo.batch_create_photos",
        lambda *a, **kw: inserted,
    )

    added_types = []
    db.add.side_effect = lambda obj: added_types.append(type(obj).__name__)

    _run(strategy.handle_completion(worker, [item], db))

    task_calls = [t for t in added_types if t == "Task"]
    # METADATA + FACE + OCR + CLASSIFY + VISUAL_DESCRIPTION + IMAGE_EMBEDDING = 6
    assert len(task_calls) == 6


def test_handle_completion_no_eligible_photos_returns_early():
    strategy = _strategy()
    db = MagicMock()
    worker = MagicMock()
    worker.scan_status = {"added": 0, "processed_files": 0}

    item = {"status": "completed", "task_id": uuid4(), "result": {}}

    _run(strategy.handle_completion(worker, [item], db))
    db.add.assert_not_called()


def test_handle_completion_status_not_completed_is_ignored():
    strategy = _strategy()
    db = MagicMock()
    worker = MagicMock()
    worker.scan_status = {"added": 0, "processed_files": 0}

    item = {"status": "FAILED", "task_id": uuid4(), "result": {}}

    _run(strategy.handle_completion(worker, [item], db))
    db.add.assert_not_called()
