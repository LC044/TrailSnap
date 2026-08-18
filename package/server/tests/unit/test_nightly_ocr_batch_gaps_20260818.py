"""Unit tests covering 2026-08-18 nightly coverage gap scan.

Module exercised:
* app/service/tasks/ocr.py -- OcrStrategy.process_batch and
  OcrStrategy.process_single_photo (both largely uncovered in the
  171-line gap reported by the scan).
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest


pytestmark = [pytest.mark.smoke]


def _task(**kw):
    base = {
        "id": uuid4(),
        "type": None,
        "owner_id": uuid4(),
        "payload": {},
    }
    base.update(kw)
    return SimpleNamespace(**base)


def _photo(**kw):
    base = {
        "id": uuid4(),
        "owner_id": uuid4(),
        "file_type": 0,
        "file_path": "/tmp/p.jpg",
        "processed_tasks": {},
    }
    base.update(kw)
    return SimpleNamespace(**base)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@contextmanager
def _patch_ai_response(payload):
    resp = MagicMock()
    resp.status = payload.get("status", 200)

    async def _json():
        return payload.get("json", {"results": []})

    resp.json = _json

    @asynccontextmanager
    async def _post(url, json=None, timeout=None):
        yield resp

    fake_session = MagicMock()
    fake_session.post = _post

    @asynccontextmanager
    async def _session_factory():
        yield fake_session

    with patch("aiohttp.ClientSession", _session_factory):
        yield resp


@contextmanager
def _patch_image_open(width=200, height=100):
    """Patch both PIL.Image.open (size probe) and built-in open (file read).

    The OCR code does:
        with Image.open(target_path) as img: width, height = img.size
        with open(target_path, "rb") as f_img: b64_data = ...
    so both need to be mocked for the success path to avoid FileNotFoundError
    on the synthetic `/tmp/p.jpg` target.
    """
    image_stub = MagicMock()
    image_stub.size = (width, height)
    image_stub.__enter__.return_value = image_stub
    image_stub.__exit__.return_value = False

    def _image_open(path):
        return image_stub

    file_handle = MagicMock()
    file_handle.__enter__.return_value = file_handle
    file_handle.__exit__.return_value = False
    file_handle.read.return_value = b"\x89PNG_FAKE"

    def _builtin_open(path, mode="r", *args, **kwargs):
        return file_handle

    with patch("app.service.tasks.ocr.Image.open", side_effect=_image_open), \
            patch("app.service.tasks.ocr.open", side_effect=_builtin_open, create=True):
        yield image_stub


@contextmanager
def _patch_ocr_crud():
    created = {"count": 0, "items": []}

    def _create(db, payload):
        created["count"] += 1
        created["items"].append(payload)
        return MagicMock()

    def _delete(db, photo_id):
        return 0

    with patch("app.service.tasks.ocr.crud_ocr.create_ocr", side_effect=_create), \
            patch("app.service.tasks.ocr.crud_ocr.delete_ocr_by_photo_id", side_effect=_delete):
        yield created


def _import_strategy():
    from app.service.tasks.ocr import OcrStrategy
    return OcrStrategy()


def _wire_db_for_photo_lookup(db, photos):
    chain = db.query.return_value
    chain.filter.return_value.all.return_value = photos
    return chain


def test_process_batch_generator_task_success_is_completed():
    from app.service.tasks.ocr import OcrStrategy

    strategy = OcrStrategy()
    gen_task = _task(payload={})

    async def _fake_process(self, worker, task, db):
        return {"status": "success", "generated_tasks": 3}

    with patch.object(OcrStrategy, "process", new=_fake_process):
        results = _run(strategy.process_batch(MagicMock(), [gen_task], MagicMock()))
    assert len(results) == 1
    assert results[0]["status"] == "completed"
    assert results[0]["result"]["generated_tasks"] == 3
    assert results[0]["error"] is None


def test_process_batch_generator_task_failure_marks_failed():
    from app.service.tasks.ocr import OcrStrategy

    strategy = OcrStrategy()
    gen_task = _task(payload={})

    async def _fake_process(self, worker, task, db):
        return {"status": "failed", "error": "boom"}

    with patch.object(OcrStrategy, "process", new=_fake_process):
        results = _run(strategy.process_batch(MagicMock(), [gen_task], MagicMock()))
    assert results[0]["status"] == "failed"
    assert results[0]["error"] == "boom"


def test_process_batch_generator_exception_is_caught():
    from app.service.tasks.ocr import OcrStrategy

    strategy = OcrStrategy()
    gen_task = _task(payload={})

    async def _fake_process(self, worker, task, db):
        raise RuntimeError("explode")

    with patch.object(OcrStrategy, "process", new=_fake_process):
        results = _run(strategy.process_batch(MagicMock(), [gen_task], MagicMock()))
    assert results[0]["status"] == "failed"
    assert "explode" in results[0]["error"]


def test_process_batch_no_photo_tasks_returns_generator_results():
    from app.service.tasks.ocr import OcrStrategy

    strategy = OcrStrategy()

    async def _fake_process(self, worker, task, db):
        return {"status": "success", "generated_tasks": 0}

    with patch.object(OcrStrategy, "process", new=_fake_process):
        results = _run(strategy.process_batch(
            MagicMock(),
            [_task(payload={})],
            MagicMock(),
        ))
    assert len(results) == 1
    assert all("photo" not in r for r in results)


def test_process_batch_photo_not_found_skips_task():
    strategy = _import_strategy()
    db = MagicMock()
    _wire_db_for_photo_lookup(db, [])
    owner = uuid4()
    task = _task(owner_id=owner, payload={"photo_id": str(uuid4())})

    with patch("app.service.tasks.ocr.ci_task_limit_reached", return_value=False), \
            patch("app.service.tasks.ocr.crud_ocr.create_ocr") as _create, \
            patch("app.service.tasks.ocr.crud_ocr.delete_ocr_by_photo_id"):
        results = _run(strategy.process_batch(MagicMock(), [task], db))

    assert len(results) == 1
    assert results[0]["status"] == "completed"
    assert results[0]["result"]["status"] == "skipped"
    assert results[0]["result"]["reason"] == "photo not found"
    _create.assert_not_called()


def test_process_batch_already_processed_skipped_without_force(monkeypatch):
    strategy = _import_strategy()
    db = MagicMock()
    photo = _photo(processed_tasks={"ocr": True})
    _wire_db_for_photo_lookup(db, [photo])
    monkeypatch.setattr("app.service.tasks.ocr.ci_task_limit_reached", lambda db, model: False)

    task = _task(owner_id=photo.owner_id, payload={"photo_id": str(photo.id)})
    results = _run(strategy.process_batch(MagicMock(), [task], db))
    assert results[0]["result"]["reason"] == "already processed"


def test_process_batch_ci_limit_reached_skips_without_calling_ai(monkeypatch):
    strategy = _import_strategy()
    db = MagicMock()
    photo = _photo()
    _wire_db_for_photo_lookup(db, [photo])
    monkeypatch.setattr("app.service.tasks.ocr.ci_task_limit_reached", lambda db, model: True)

    task = _task(owner_id=photo.owner_id, payload={"photo_id": str(photo.id), "force": True})
    results = _run(strategy.process_batch(MagicMock(), [task], db))
    assert "CI ocr limit" in results[0]["result"]["reason"]


def test_process_batch_file_not_found_marks_failed(monkeypatch):
    strategy = _import_strategy()
    db = MagicMock()
    photo = _photo(file_path="/nope.jpg")
    _wire_db_for_photo_lookup(db, [photo])
    monkeypatch.setattr("app.service.tasks.ocr.ci_task_limit_reached", lambda db, model: False)
    monkeypatch.setattr(
        "app.service.storage.get_available_photo_path",
        lambda *a, **kw: None,
    )

    task = _task(owner_id=photo.owner_id, payload={"photo_id": str(photo.id), "force": True})
    results = _run(strategy.process_batch(MagicMock(), [task], db))
    assert results[0]["status"] == "failed"
    assert results[0]["error"] == "file not found"


def test_process_batch_image_read_error_marks_failed(monkeypatch, tmp_path):
    strategy = _import_strategy()
    db = MagicMock()
    photo = _photo(file_path=str(tmp_path / "broken.jpg"))
    _wire_db_for_photo_lookup(db, [photo])
    monkeypatch.setattr("app.service.tasks.ocr.ci_task_limit_reached", lambda db, model: False)
    monkeypatch.setattr(
        "app.service.storage.get_available_photo_path",
        lambda *a, **kw: str(tmp_path / "broken.jpg"),
    )

    def _boom(_):
        raise OSError("disk gone")

    with patch("app.service.tasks.ocr.Image.open", side_effect=_boom):
        task = _task(owner_id=photo.owner_id, payload={"photo_id": str(photo.id), "force": True})
        results = _run(strategy.process_batch(MagicMock(), [task], db))

    assert results[0]["status"] == "failed"
    assert "read file error" in results[0]["error"]

def test_process_batch_success_normalizes_polygons_and_persists(monkeypatch):
    strategy = _import_strategy()
    db = MagicMock()
    photo = _photo()
    _wire_db_for_photo_lookup(db, [photo])
    monkeypatch.setattr("app.service.tasks.ocr.ci_task_limit_reached", lambda db, model: False)
    monkeypatch.setattr(
        "app.service.storage.get_available_photo_path",
        lambda *a, **kw: "/tmp/p.jpg",
    )

    ai_payload = {
        "results": [
            {
                "ocrResults": [
                    {
                        "prunedResult": {
                            "rec_texts": ["hello", "world"],
                            "rec_scores": [0.9, 0.8],
                            "rec_polys": [
                                [[10.0, 20.0], [110.0, 20.0], [110.0, 60.0], [10.0, 60.0]],
                                [[0.0, 0.0], [200.0, 0.0], [200.0, 50.0], [0.0, 50.0]],
                            ],
                        }
                    }
                ],
            }
        ]
    }

    with _patch_image_open(width=200, height=100), _patch_ai_response({"json": ai_payload}), _patch_ocr_crud() as created:
        task = _task(owner_id=photo.owner_id, payload={"photo_id": str(photo.id), "force": True})
        results = _run(strategy.process_batch(MagicMock(), [task], db))

    assert results[0]["status"] == "completed"
    assert results[0]["result"]["texts_found"] == 2
    assert created["count"] == 2
    first = created["items"][0].polygon
    assert abs(first[0][0] - 10 / 200) < 1e-6
    assert abs(first[0][1] - 20 / 100) < 1e-6
    assert photo.processed_tasks["ocr"] is True


def test_process_batch_per_image_error_reported_as_failed(monkeypatch):
    strategy = _import_strategy()
    db = MagicMock()
    photo = _photo()
    _wire_db_for_photo_lookup(db, [photo])
    monkeypatch.setattr("app.service.tasks.ocr.ci_task_limit_reached", lambda db, model: False)
    monkeypatch.setattr(
        "app.service.storage.get_available_photo_path",
        lambda *a, **kw: "/tmp/p.jpg",
    )

    ai_payload = {"results": [{"error": "OCR model timeout"}]}

    with _patch_image_open(), _patch_ai_response({"json": ai_payload}), _patch_ocr_crud():
        task = _task(owner_id=photo.owner_id, payload={"photo_id": str(photo.id), "force": True})
        results = _run(strategy.process_batch(MagicMock(), [task], db))

    assert results[0]["status"] == "failed"
    assert "OCR model timeout" in results[0]["error"]


def test_process_batch_ai_non_200_marks_all_failed(monkeypatch):
    strategy = _import_strategy()
    db = MagicMock()
    photos = [_photo(), _photo()]
    _wire_db_for_photo_lookup(db, photos)
    monkeypatch.setattr("app.service.tasks.ocr.ci_task_limit_reached", lambda db, model: False)
    monkeypatch.setattr(
        "app.service.storage.get_available_photo_path",
        lambda *a, **kw: "/tmp/p.jpg",
    )

    with _patch_image_open(), _patch_ai_response({"status": 503, "json": {}}), _patch_ocr_crud():
        tasks = [
            _task(owner_id=p.owner_id, payload={"photo_id": str(p.id), "force": True})
            for p in photos
        ]
        results = _run(strategy.process_batch(MagicMock(), tasks, db))

    failed = [r for r in results if r["status"] == "failed"]
    assert len(failed) == 2
    for entry in failed:
        assert "AI Service error" in entry["error"]
        assert "503" in entry["error"]


def test_process_batch_owner_exception_fills_failed(monkeypatch):
    strategy = _import_strategy()
    db = MagicMock()
    photo = _photo()
    _wire_db_for_photo_lookup(db, [photo])
    monkeypatch.setattr("app.service.tasks.ocr.ci_task_limit_reached", lambda db, model: False)
    monkeypatch.setattr(
        "app.service.storage.get_available_photo_path",
        lambda *a, **kw: "/tmp/p.jpg",
    )

    @asynccontextmanager
    async def _boom_session():
        raise RuntimeError("session down")
        yield  # pragma: no cover - never executed

    with _patch_image_open(), patch("aiohttp.ClientSession", _boom_session):
        task = _task(owner_id=photo.owner_id, payload={"photo_id": str(photo.id), "force": True})
        results = _run(strategy.process_batch(MagicMock(), [task], db))

    assert len(results) == 1
    assert results[0]["status"] == "failed"
    assert "session down" in results[0]["error"]


def test_process_single_photo_returns_failed_when_file_missing(monkeypatch):
    strategy = _import_strategy()
    monkeypatch.setattr(
        "app.service.storage.get_available_photo_path",
        lambda *a, **kw: None,
    )
    photo = _photo()
    res = _run(strategy.process_single_photo(MagicMock(), photo, MagicMock()))
    assert res == {"status": "failed", "error": "file not found"}


def test_process_single_photo_ai_error_returned_verbatim(monkeypatch):
    strategy = _import_strategy()
    monkeypatch.setattr(
        "app.service.storage.get_available_photo_path",
        lambda *a, **kw: "/tmp/p.jpg",
    )
    monkeypatch.setattr(
        "app.service.tasks.ocr.config_manager.get_user_config",
        lambda *a, **kw: SimpleNamespace(ai=SimpleNamespace(ai_api_url="http://ai")),
    )

    ai_payload = {"results": [{"error": "model crashed"}]}

    with _patch_image_open(), _patch_ai_response({"json": ai_payload}), _patch_ocr_crud():
        photo = _photo()
        res = _run(strategy.process_single_photo(MagicMock(), photo, MagicMock()))

    assert res["status"] == "failed"
    assert res["error"] == "model crashed"


def test_process_single_photo_success_writes_each_text_row(monkeypatch):
    strategy = _import_strategy()
    monkeypatch.setattr(
        "app.service.storage.get_available_photo_path",
        lambda *a, **kw: "/tmp/p.jpg",
    )
    monkeypatch.setattr(
        "app.service.tasks.ocr.config_manager.get_user_config",
        lambda *a, **kw: SimpleNamespace(ai=SimpleNamespace(ai_api_url="http://ai")),
    )

    ai_payload = {
        "results": [
            {
                "ocrResults": [
                    {
                        "prunedResult": {
                            "rec_texts": ["one", "two", "three"],
                            "rec_scores": [0.91, 0.92],
                            "rec_polys": [[[0, 0], [1, 0], [1, 1], [0, 1]]],
                        }
                    }
                ]
            }
        ]
    }

    with _patch_image_open(width=100, height=50), _patch_ai_response({"json": ai_payload}), _patch_ocr_crud() as created:
        photo = _photo()
        res = _run(strategy.process_single_photo(MagicMock(), photo, MagicMock()))

    assert res == {"status": "success", "texts_found": 3}
    assert created["count"] == 3
    third = created["items"][2]
    assert third.text_score == 0.0
    assert third.polygon == []


def test_process_single_photo_missing_dimensions_keeps_absolute_poly(monkeypatch):
    strategy = _import_strategy()
    monkeypatch.setattr(
        "app.service.storage.get_available_photo_path",
        lambda *a, **kw: "/tmp/p.jpg",
    )
    monkeypatch.setattr(
        "app.service.tasks.ocr.config_manager.get_user_config",
        lambda *a, **kw: SimpleNamespace(ai=SimpleNamespace(ai_api_url="http://ai")),
    )

    ai_payload = {
        "results": [
            {
                "ocrResults": [
                    {
                        "prunedResult": {
                            "rec_texts": ["x"],
                            "rec_scores": [0.5],
                            "rec_polys": [[[5, 6], [7, 6], [7, 8], [5, 8]]],
                        }
                    }
                ]
            }
        ]
    }

    with _patch_image_open(width=0, height=0), _patch_ai_response({"json": ai_payload}), _patch_ocr_crud() as created:
        photo = _photo()
        _run(strategy.process_single_photo(MagicMock(), photo, MagicMock()))

    assert created["items"][0].polygon == [[5, 6], [7, 6], [7, 8], [5, 8]]


def test_process_single_photo_empty_rec_texts_returns_zero(monkeypatch):
    strategy = _import_strategy()
    monkeypatch.setattr(
        "app.service.storage.get_available_photo_path",
        lambda *a, **kw: "/tmp/p.jpg",
    )
    monkeypatch.setattr(
        "app.service.tasks.ocr.config_manager.get_user_config",
        lambda *a, **kw: SimpleNamespace(ai=SimpleNamespace(ai_api_url="http://ai")),
    )

    empty_payload = {
        "results": [
            {
                "ocrResults": [
                    {
                        "prunedResult": {
                            "rec_texts": [],
                            "rec_scores": [],
                            "rec_polys": [],
                        }
                    }
                ]
            }
        ]
    }

    with _patch_image_open(), _patch_ai_response({"json": empty_payload}), _patch_ocr_crud() as created:
        photo = _photo()
        res = _run(strategy.process_single_photo(MagicMock(), photo, MagicMock()))

    assert res == {"status": "success", "texts_found": 0}
    assert created["count"] == 0
