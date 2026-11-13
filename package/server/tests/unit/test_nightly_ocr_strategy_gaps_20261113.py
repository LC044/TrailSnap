"""Nightly watch 2026-11-13 (round 2): OCR task strategy gaps.

Targets the branches the 2026-11-13 coverage snapshot still reports as
uncovered in ``app/service/tasks/ocr.py``:

* ``OcrStrategy.process`` - a failing generator run is logged and re-raised.
* ``OcrStrategy.process_single_photo`` - a non-200 AI response is reported as
  a failure, and an unexpected error marks the photo as not processed before
  it is re-raised.

Every test exercises already-implemented behaviour; no production change.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

pytestmark = [pytest.mark.smoke]


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _task(**kw):
    base = {"id": uuid4(), "type": None, "owner_id": uuid4(), "payload": {}}
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


class _FakeResp:
    def __init__(self, status=500, payload=None):
        self.status = status
        self._payload = payload or {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False

    async def json(self):
        return self._payload


class _FakeSession:
    def __init__(self, resp):
        self._resp = resp

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False

    def post(self, *_args, **_kwargs):
        return self._resp


def test_ocr_process_reraises_a_failing_generator_run():
    from app.service.tasks.ocr import OcrStrategy

    db = MagicMock()
    strategy = OcrStrategy()
    task = _task(payload={})

    with patch("app.service.tasks.ocr.ci_remaining_budget", return_value=None), \
            patch("app.service.tasks.ocr.generate_photo_tasks",
                  side_effect=RuntimeError("generator boom")):
        with pytest.raises(RuntimeError):
            _run(strategy.process(MagicMock(), task, db))


def test_ocr_single_photo_reports_a_failed_ai_response(tmp_path):
    from PIL import Image

    from app.service.tasks.ocr import OcrStrategy

    image_path = tmp_path / "photo.png"
    Image.new("RGB", (4, 4)).save(image_path)

    photo = _photo(file_path=str(image_path))
    db = MagicMock()
    strategy = OcrStrategy()

    user_config = SimpleNamespace(ai=SimpleNamespace(ai_api_url="http://ai"))

    with patch("app.service.storage.get_available_photo_path", return_value=str(image_path)), \
            patch("app.service.tasks.ocr.config_manager.get_user_config", return_value=user_config), \
            patch("aiohttp.ClientSession", lambda *a, **k: _FakeSession(_FakeResp(500))), \
            patch("app.service.tasks.ocr.ai_response_error",
                  new=AsyncMockFactory(lambda resp: "ai unavailable")):
        result = _run(strategy.process_single_photo(MagicMock(), photo, db))

    assert result["status"] == "failed"
    assert result["error"] == "ai unavailable"


def test_ocr_single_photo_marks_the_photo_as_failed_and_reraises(tmp_path):
    from app.service.tasks.ocr import OcrStrategy

    image_path = tmp_path / "photo.png"
    image_path.write_bytes(b"not-an-image")

    photo = _photo(file_path=str(image_path))
    db = MagicMock()
    strategy = OcrStrategy()

    with patch("app.service.storage.get_available_photo_path", return_value=str(image_path)), \
            patch("app.service.tasks.ocr.Image.open", side_effect=OSError("broken image")):
        with pytest.raises(OSError):
            _run(strategy.process_single_photo(MagicMock(), photo, db))

    assert photo.processed_tasks["ocr"] is False
    db.add.assert_called_with(photo)
    db.commit.assert_called()


def AsyncMockFactory(factory):
    """Build an awaitable mock returning ``factory(awaitable)``."""
    from unittest.mock import AsyncMock

    async def _call(*args, **kwargs):
        return factory(*args, **kwargs)

    return _call
