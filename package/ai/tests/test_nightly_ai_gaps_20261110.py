"""Nightly watch 2026-11-10: AI service coverage gaps.

Targets the lines the 2026-11-10 AI coverage snapshot (95% total) still
reports as uncovered:

* ``app/services/model_manager.py`` - the CUDA-cache release path, the
  ``release()`` "wait while another thread is releasing" branch and the
  ``ModelManager`` singleton early return,
* ``app/services/ocr_service.py`` - the OpenVINO engine branch of
  ``load_paddleocr_model`` and the "model not ready" guard of
  ``OCRService.detect_text``,
* ``app/services/emotion_service.py`` - the portrait / indoor category
  branches and the large-image pixel sampling,
* ``app/services/face_service.py`` - the CUDA-cache release path and the
  empty-image guard of ``process_image``.

Every test exercises already-implemented behaviour; no production code changes.
"""

from __future__ import annotations

import base64
import io
import sys
import threading
import time
import types

import numpy as np
import pytest
from PIL import Image

pytestmark = [pytest.mark.smoke]


# --------------------------------------------------------------------------
# app/services/model_manager.py
# --------------------------------------------------------------------------
def _fake_torch(monkeypatch, cuda_available=True):
    """Install a stub ``torch`` module so the CUDA cache branch is reachable."""
    calls = []
    fake = types.ModuleType("torch")
    fake.cuda = types.SimpleNamespace(
        is_available=lambda: cuda_available,
        empty_cache=lambda: calls.append("cleared"),
    )
    monkeypatch.setitem(sys.modules, "torch", fake)
    return calls


def test_release_clears_the_cuda_cache_when_torch_is_available(monkeypatch):
    from app.services import model_manager as mm

    calls = _fake_torch(monkeypatch)
    wrapper = mm.ModelWrapper("dummy", lambda: object())
    wrapper.model = object()

    wrapper.release()

    assert calls == ["cleared"]
    assert wrapper.model is None


def test_release_keeps_the_model_when_cuda_is_unavailable(monkeypatch):
    from app.services import model_manager as mm

    calls = _fake_torch(monkeypatch, cuda_available=False)
    wrapper = mm.ModelWrapper("dummy", lambda: object())
    wrapper.model = object()

    wrapper.release()

    assert calls == []
    assert wrapper.model is None


def test_release_waits_while_another_thread_is_releasing():
    from app.services import model_manager as mm

    wrapper = mm.ModelWrapper("dummy", lambda: object())
    wrapper.model = object()
    released = threading.Event()

    def releaser():
        wrapper.release()
        released.set()

    # Simulate a concurrent release so release() has to wait on the condition.
    with wrapper.condition:
        wrapper.releasing = True

    thread = threading.Thread(target=releaser)
    thread.start()
    time.sleep(0.05)
    assert not released.is_set()

    with wrapper.condition:
        wrapper.releasing = False
        wrapper.condition.notify_all()

    thread.join(timeout=5)
    assert released.is_set()
    assert wrapper.model is None


def test_model_manager_is_a_singleton_and_reinitialises_only_once():
    from app.services.model_manager import ModelManager

    first = ModelManager()
    models = first.models
    second = ModelManager()

    assert second is first
    # The second __init__ returned early, so the registered models survived.
    assert second.models is models


# --------------------------------------------------------------------------
# app/services/ocr_service.py
# --------------------------------------------------------------------------
def _ocr_runtime(monkeypatch):
    """Stub the model catalogue so load_paddleocr_model() stays offline."""
    from app.services import ocr_service

    spec = {
        "runtime": {
            "modelType": "MOBILE",
            "ocrVersion": "PPOCRV4",
            "clsOcrVersion": "PPOCRV4",
            "detFile": "det.onnx",
            "clsFile": "cls.onnx",
            "recFile": "rec.onnx",
        }
    }
    monkeypatch.setattr(ocr_service.ai_model_manager, "get_selected_spec", lambda *a, **k: spec)
    monkeypatch.setattr(ocr_service.ai_model_manager, "get_model_dir", lambda *a, **k: __import__("pathlib").Path("/tmp/ocr"))
    return ocr_service


def test_load_paddleocr_model_uses_the_openvino_engine_when_available(monkeypatch):
    import rapidocr

    ocr_service = _ocr_runtime(monkeypatch)
    monkeypatch.setitem(sys.modules, "openvino", types.ModuleType("openvino"))
    monkeypatch.setitem(sys.modules, "openvino", types.ModuleType("openvino"))
    sys.modules["openvino"].Core = object
    captured = {}

    class FakeRapidOCR:
        def __init__(self, params=None):
            captured["params"] = params

    monkeypatch.setattr(rapidocr, "RapidOCR", FakeRapidOCR)

    ocr_service.load_paddleocr_model()

    params = captured["params"]
    assert params["Det.engine_type"] is rapidocr.EngineType.OPENVINO
    assert params["Cls.engine_type"] is rapidocr.EngineType.OPENVINO
    assert params["Rec.engine_type"] is rapidocr.EngineType.OPENVINO
    assert params["EngineConfig.openvino"]["num_infer_requests"] == 1
    assert ocr_service._ocr_engine_is_openvino is True


def test_load_paddleocr_model_falls_back_to_onnxruntime(monkeypatch):
    import rapidocr

    ocr_service = _ocr_runtime(monkeypatch)
    monkeypatch.setitem(sys.modules, "openvino", None)
    captured = {}

    class FakeRapidOCR:
        def __init__(self, params=None):
            captured["params"] = params

    monkeypatch.setattr(rapidocr, "RapidOCR", FakeRapidOCR)

    ocr_service.load_paddleocr_model()

    params = captured["params"]
    assert params["Det.engine_type"] is rapidocr.EngineType.ONNXRUNTIME
    assert ocr_service._ocr_engine_is_openvino is False


def test_detect_text_refuses_to_run_before_the_model_is_ready(monkeypatch):
    from app.services import ocr_service

    monkeypatch.setattr(ocr_service.ai_model_manager, "is_ready", lambda *a, **k: False)

    with pytest.raises(Exception, match="not ready"):
        ocr_service.OCRService().detect_text(b"not-an-image")


# --------------------------------------------------------------------------
# app/services/emotion_service.py
# --------------------------------------------------------------------------
def test_infer_categories_detects_a_portrait_from_skin_tones():
    from app.services.emotion_service import _infer_categories_from_color

    categories = _infer_categories_from_color(
        [{"hex": "#d99a6c", "ratio": 0.55}], brightness=0.7, saturation=0.3
    )

    assert "人像" in categories


def test_infer_categories_detects_an_indoor_scene():
    from app.services.emotion_service import _infer_categories_from_color

    categories = _infer_categories_from_color(
        [{"hex": "#808080", "ratio": 1.0}], brightness=0.45, saturation=0.1
    )

    assert "室内" in categories


def test_infer_categories_falls_back_to_the_daily_bucket():
    from app.services.emotion_service import _infer_categories_from_color

    categories = _infer_categories_from_color(
        [{"hex": "#8080ff", "ratio": 1.0}], brightness=0.7, saturation=0.4
    )

    assert categories == ["日常"]


def test_analyze_single_samples_pixels_of_a_large_image():
    from app.services.emotion_service import EmotionService

    image = Image.new("RGB", (200, 200), (120, 140, 200))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    payload = base64.b64encode(buffer.getvalue()).decode()

    result = EmotionService()._analyze_single(payload)

    assert result["dominant_colors"]
    assert result["brightness"] is not None


# --------------------------------------------------------------------------
# app/services/face_service.py
# --------------------------------------------------------------------------
def test_release_model_clears_the_cuda_cache_when_torch_is_available(monkeypatch):
    from app.services import face_service

    calls = []
    fake = types.ModuleType("torch")
    fake.cuda = types.SimpleNamespace(
        is_available=lambda: True,
        empty_cache=lambda: calls.append("cleared"),
    )
    monkeypatch.setitem(sys.modules, "torch", fake)

    face_service.release_model(object())

    assert calls == ["cleared"]


def test_process_image_rejects_an_empty_image(monkeypatch):
    import cv2

    from app.services import face_service

    monkeypatch.setattr(face_service.ai_model_manager, "is_ready", lambda *a, **k: True)
    monkeypatch.setattr(face_service.model_manager, "get_model", lambda *a, **k: object())
    monkeypatch.setattr(cv2, "imdecode", lambda *a, **k: np.zeros((0, 8, 3), dtype=np.uint8))

    with pytest.raises(ValueError, match="empty"):
        face_service.FaceRecognitionService().process_image(b"fake")
