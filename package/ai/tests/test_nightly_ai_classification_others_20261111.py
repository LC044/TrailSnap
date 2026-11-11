"""Nightly gap coverage (2026-11-11) — image classification "others" fallback.

The 2026-11-11 AI coverage scan reported
``app/services/image_classification_service.py`` at 95.8% with these lines
still uncovered:

* 159-166 — the ``make_check`` closure built inside
  ``_register_available_category_models``.  It is **dead code**: the closure is
  never handed to ``model_manager.register_model`` (which only accepts
  ``(name, load_func, release_func)``), so the ``check`` callable can never be
  invoked.  The closure was removed as part of this nightly run and the
  registration behaviour is pinned by the tests below.
* 279 — the ``others`` branch of the batch ``classify_yolo`` path, taken when
  the general model's top confidence is below ``min_conf``.

All models are mocked; no ONNX model file is required.
"""

import base64
import io
import os
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PIL import Image

from app.services import image_classification_service as module
from app.services.image_classification_service import ImageClassificationService

pytestmark = pytest.mark.smoke


def _bare_service(category_map):
    """Build a service instance without touching the real model registry."""
    service = ImageClassificationService.__new__(ImageClassificationService)
    service._category_model_map = dict(category_map)
    service.version = "v0.3.10.1"
    return service


def _png_payload():
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), (1, 2, 3)).save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode()


# --------------------------------------------------------------------------- #
# 279 — batch path falls back to "others" when confidence is too low
# --------------------------------------------------------------------------- #

def test_classify_yolo_batch_uses_others_when_confidence_below_threshold():
    """A general model whose top probability is < 0.5 yields an "others" label."""
    service = _bare_service({})

    general_model = MagicMock()
    general_model.names = {0: "animal"}
    general_model.return_value = [np.array([0.3, 0.2], dtype=np.float32)]

    manager = MagicMock()
    manager.is_ready.return_value = True
    manager.get_model.side_effect = lambda key: general_model

    with patch.object(module, "ai_model_manager", manager), \
         patch.object(module, "model_manager", manager), \
         patch.object(ImageClassificationService, "_register_available_category_models", lambda self: None):
        results = service.classify_yolo([_png_payload()])

    assert results[0]["status"] == "success"
    assert results[0]["predictions"][0]["label"] == "others"
    assert results[0]["predictions"][0]["confidence"] == pytest.approx(0.3, rel=1e-6)


def test_classify_yolo_batch_marks_others_without_touching_small_models():
    """The "others" branch must not look up or call any category sub-model."""
    service = _bare_service({"animal": "photo-cls-animal.onnx"})

    general_model = MagicMock()
    general_model.names = {0: "animal"}
    general_model.return_value = [np.array([0.2, 0.2], dtype=np.float32)]

    manager = MagicMock()
    manager.is_ready.return_value = True

    def _get_model(key):
        if key == "yolo_photo_cls_general":
            return general_model
        raise AssertionError(f"unexpected model lookup: {key}")

    manager.get_model.side_effect = _get_model

    with patch.object(module, "ai_model_manager", manager), \
         patch.object(module, "model_manager", manager), \
         patch.object(ImageClassificationService, "_register_available_category_models", lambda self: None):
        results = service.classify_yolo([_png_payload()])

    assert results[0]["predictions"][0]["label"] == "others"
    assert "yolo_photo_cls_animal" not in [call.args[0] for call in manager.get_model.call_args_list]


# --------------------------------------------------------------------------- #
# _normalize_label boundaries feeding the "others" fallback
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("label,confidence,expected", [
    (None, 0.9, "others"),
    ("animal", 0.49, "others"),
    ("animal", 0.5, "animal"),
])
def test_normalize_label_falls_back_to_others(label, confidence, expected):
    service = _bare_service({})
    assert service._normalize_label(label, confidence) == expected


# --------------------------------------------------------------------------- #
# 159-166 — dead ``make_check`` closure removed from the registration path
# --------------------------------------------------------------------------- #

def test_register_available_category_models_registers_loader_and_release(tmp_path):
    """Category models are registered with (name, loader, releaser) only."""
    (tmp_path / "photo-cls-animal.onnx").write_bytes(b"x")
    (tmp_path / "photo-cls-general.onnx").write_bytes(b"x")

    service = _bare_service({})

    manager = MagicMock()
    manager.models = {}

    with patch.object(module, "ai_model_manager") as ai_manager, \
         patch.object(module, "model_manager", manager):
        ai_manager.get_model_dir.return_value = str(tmp_path)
        service._register_available_category_models()

    assert service._category_model_map == {"animal": "photo-cls-animal.onnx"}
    assert manager.register_model.call_count == 1
    name, loader, releaser = manager.register_model.call_args.args
    assert name == "yolo_photo_cls_animal"
    assert callable(loader) and callable(releaser)
    # The removed dead closure passed a 4th argument; registration must stay
    # on the documented 3-argument signature.
    assert len(manager.register_model.call_args.args) == 3
    assert not manager.register_model.call_args.kwargs


def test_register_available_category_models_keeps_existing_registration(tmp_path):
    """An already registered category model is not registered a second time."""
    (tmp_path / "photo-cls-animal.onnx").write_bytes(b"x")

    service = _bare_service({})

    manager = MagicMock()
    manager.models = {"yolo_photo_cls_animal": object()}

    with patch.object(module, "ai_model_manager") as ai_manager, \
         patch.object(module, "model_manager", manager):
        ai_manager.get_model_dir.return_value = str(tmp_path)
        service._register_available_category_models()

    manager.register_model.assert_not_called()


def test_discover_category_models_ignores_general_and_non_onnx(tmp_path):
    """Only ``photo-cls-<category>.onnx`` files become category routes."""
    (tmp_path / "photo-cls-general.onnx").write_bytes(b"x")
    (tmp_path / "photo-cls-animal.onnx").write_bytes(b"x")
    (tmp_path / "photo-cls-dog.txt").write_bytes(b"x")
    (tmp_path / "unrelated.onnx").write_bytes(b"x")

    service = _bare_service({})

    with patch.object(module, "ai_model_manager") as ai_manager:
        ai_manager.get_model_dir.return_value = str(tmp_path)
        discovered = service._discover_category_models()

    assert discovered == {"animal": "photo-cls-animal.onnx"}
    assert os.path.exists(str(tmp_path / "photo-cls-animal.onnx"))
