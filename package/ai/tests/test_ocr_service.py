"""Unit tests for OCRService (app/services/ocr_service.py).

OCRService.detect_text calls a RapidOCR instance via model_manager.get_model.
The module-level openvino_infer_lock() must serialize inference when the engine
is OpenVINO and be a no-op otherwise. We patch both to assert that.
"""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

pytestmark = [pytest.mark.smoke]


@pytest.fixture
def fake_ocr_result():
    """Build a MagicMock that quacks like a RapidOCR result (txts / scores / boxes)."""
    result = MagicMock()
    result.txts = ["hello", "world"]
    result.scores = [0.99, 0.42]
    boxes = np.array([[[0, 0], [10, 0], [10, 10], [0, 10]], [[20, 5], [40, 5], [40, 25], [20, 25]]], dtype=float)
    result.boxes = boxes
    return result


def test_openvino_infer_lock_is_noop_when_engine_is_not_openvino(monkeypatch):
    """If _ocr_engine_is_openvino is False, the lock must yield without acquiring."""
    from app.services import ocr_service
    monkeypatch.setattr(ocr_service, "_ocr_engine_is_openvino", False)

    acquired = {"count": 0}

    class FakeLock:
        def __enter__(self):
            acquired["count"] += 1
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(ocr_service, "_ocr_infer_lock", FakeLock())

    with ocr_service.openvino_infer_lock():
        pass
    assert acquired["count"] == 0


def test_openvino_infer_lock_acquires_when_engine_is_openvino(monkeypatch):
    """If _ocr_engine_is_openvino is True, the context must enter _ocr_infer_lock."""
    from app.services import ocr_service
    monkeypatch.setattr(ocr_service, "_ocr_engine_is_openvino", True)

    acquired = {"count": 0}

    class FakeLock:
        def __enter__(self):
            acquired["count"] += 1
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(ocr_service, "_ocr_infer_lock", FakeLock())

    with ocr_service.openvino_infer_lock():
        pass
    assert acquired["count"] == 1


def test_detect_text_parses_result_into_pruned_structure(monkeypatch, fake_ocr_result):
    """OCRService.detect_text should turn a RapidOCR result into the API contract."""
    from app.services import ocr_service

    fake_ocr = MagicMock(return_value=fake_ocr_result)
    fake_manager = MagicMock(get_model=MagicMock(return_value=fake_ocr))
    monkeypatch.setattr(ocr_service, "model_manager", fake_manager)
    monkeypatch.setattr(ocr_service.ai_model_manager, "is_ready", MagicMock(return_value=True))
    monkeypatch.setattr(ocr_service, "_ocr_engine_is_openvino", False)

    service = ocr_service.OCRService()
    parsed = service.detect_text(b"some-image-bytes")

    assert isinstance(parsed, list)
    assert len(parsed) == 1
    pruned = parsed[0]["prunedResult"]
    assert pruned["rec_texts"] == ["hello", "world"]
    assert pruned["rec_scores"] == [0.99, 0.42]
    assert pruned["rec_polys"] == fake_ocr_result.boxes.tolist()
    fake_ocr.assert_called_once()


def test_detect_text_handles_none_txts(monkeypatch):
    """When RapidOCR returns None for txts/scores/boxes, detect_text must coerce."""
    from app.services import ocr_service

    fake_ocr_result = MagicMock()
    fake_ocr_result.txts = None
    fake_ocr_result.scores = None
    fake_ocr_result.boxes = None
    fake_ocr = MagicMock(return_value=fake_ocr_result)
    fake_manager = MagicMock(get_model=MagicMock(return_value=fake_ocr))
    monkeypatch.setattr(ocr_service, "model_manager", fake_manager)
    monkeypatch.setattr(ocr_service.ai_model_manager, "is_ready", MagicMock(return_value=True))
    monkeypatch.setattr(ocr_service, "_ocr_engine_is_openvino", False)

    service = ocr_service.OCRService()
    parsed = service.detect_text(b"image")
    pruned = parsed[0]["prunedResult"]
    assert pruned["rec_texts"] == []
    assert pruned["rec_scores"] == []
    assert pruned["rec_polys"] == []


def test_detect_text_uses_openvino_lock_when_engine_is_openvino(monkeypatch, fake_ocr_result):
    """When the engine is OpenVINO, detect_text must take the serializing lock."""
    from app.services import ocr_service

    fake_ocr = MagicMock(return_value=fake_ocr_result)
    fake_manager = MagicMock(get_model=MagicMock(return_value=fake_ocr))
    monkeypatch.setattr(ocr_service, "model_manager", fake_manager)
    monkeypatch.setattr(ocr_service.ai_model_manager, "is_ready", MagicMock(return_value=True))
    monkeypatch.setattr(ocr_service, "_ocr_engine_is_openvino", True)

    acquired = {"count": 0}

    class FakeLock:
        def __enter__(self):
            acquired["count"] += 1
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(ocr_service, "_ocr_infer_lock", FakeLock())

    service = ocr_service.OCRService()
    service.detect_text(b"image")
    assert acquired["count"] == 1
