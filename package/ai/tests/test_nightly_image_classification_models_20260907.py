"""Nightly gap coverage for image-classification model registration and batches."""

import base64
import io
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PIL import Image

from app.services import image_classification_service as module
from app.services.image_classification_service import ImageClassificationService

pytestmark = pytest.mark.smoke


def _png_base64():
    image = Image.new("RGB", (8, 8), color=(12, 34, 56))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode()


def _bare_service(category_map=None):
    service = ImageClassificationService.__new__(ImageClassificationService)
    service._category_model_map = category_map or {}
    return service


def test_service_init_registers_general_and_discovered_category_models():
    model_manager = MagicMock()
    model_manager.models = {}
    ai_manager = MagicMock()

    with patch.object(module, "model_manager", model_manager), \
         patch.object(module, "ai_model_manager", ai_manager), \
         patch.object(ImageClassificationService, "_discover_category_models", return_value={"animal": "photo-cls-animal.onnx"}):
        service = ImageClassificationService()

    registered = [call.args[0] for call in model_manager.register_model.call_args_list]
    assert registered == ["yolo_photo_cls_general", "yolo_photo_cls_animal"]
    assert service._category_model_map == {"animal": "photo-cls-animal.onnx"}
    assert service.version == "v0.3.10.1"


def test_discover_category_models_filters_general_and_non_onnx_files(tmp_path):
    service = _bare_service()
    for name in ("photo-cls-animal.onnx", "photo-cls-general.onnx", "notes.txt"):
        (tmp_path / name).write_bytes(b"x")

    with patch.object(module, "ai_model_manager") as manager:
        manager.get_model_dir.return_value = tmp_path
        result = service._discover_category_models()

    assert result == {"animal": "photo-cls-animal.onnx"}


def test_discover_category_models_returns_empty_when_model_dir_missing(tmp_path):
    service = _bare_service()
    with patch.object(module, "ai_model_manager") as manager:
        manager.get_model_dir.return_value = tmp_path / "missing"
        assert service._discover_category_models() == {}


def test_load_category_model_handles_missing_mapping_and_missing_file(tmp_path):
    service = _bare_service({"animal": "photo-cls-animal.onnx"})
    with patch.object(module, "ai_model_manager") as manager:
        manager.get_model_dir.return_value = tmp_path
        assert service._load_category_model("document") is None
        assert service._load_category_model("animal") is None

        model_path = tmp_path / "photo-cls-animal.onnx"
        model_path.write_bytes(b"model")
        sentinel = object()
        with patch.object(module, "ONNXModelWrapper", return_value=sentinel):
            assert service._load_category_model("animal") is sentinel


def test_release_model_removes_session_and_collects_gc():
    service = _bare_service()
    wrapper = MagicMock()
    wrapper.model_name = "photo-cls-animal.onnx"
    wrapper.session = object()

    with patch("gc.collect") as collect:
        service._release_model(wrapper)

    assert not hasattr(wrapper, "session")
    collect.assert_called_once()


def test_classify_yolo_uses_category_model_when_available():
    service = _bare_service({"animal": "photo-cls-animal.onnx"})
    general = MagicMock()
    general.names = {0: "animal", 1: "document"}
    general.return_value = [np.array([0.9, 0.1]), np.array([0.8, 0.2])]
    small = MagicMock()
    small.names = {0: "cat", 1: "dog"}
    small.return_value = [np.array([0.99, 0.01]), np.array([0.02, 0.98])]

    with patch.object(service, "_register_available_category_models"), \
         patch.object(module, "ai_model_manager") as ai_manager, \
         patch.object(module, "model_manager") as model_manager:
        ai_manager.is_ready.return_value = True
        model_manager.get_model.side_effect = [general, small]
        results = service.classify_yolo([_png_base64(), _png_base64()])

    assert [item["status"] for item in results] == ["success", "success"]
    assert [item["predictions"][0]["label"] for item in results] == ["\u732b", "\u72d7"]
    assert [item["predictions"][0]["confidence"] for item in results] == [0.99, 0.98]


def test_classify_yolo_falls_back_to_general_translation_without_category_model():
    service = _bare_service({})
    general = MagicMock()
    general.names = {0: "animal", 1: "scenery"}
    general.return_value = [np.array([0.9, 0.1]), np.array([0.1, 0.9])]

    with patch.object(module, "ai_model_manager") as ai_manager, \
         patch.object(module, "model_manager") as model_manager:
        ai_manager.is_ready.return_value = True
        model_manager.get_model.return_value = general
        results = service.classify_yolo([_png_base64(), _png_base64()])

    assert [item["predictions"][0]["label"] for item in results] == ["\u52a8\u7269", "\u98ce\u666f"]
    assert [item["predictions"][0]["confidence"] for item in results] == [0.9, 0.9]
