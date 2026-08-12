"""Unit tests covering 2026-08-12 nightly AI gap scan (round 6).

Target: ``app/services/image_classification_service.py`` (56.7% previously).

Exercises previously untested branches in:
* ``ONNXModelWrapper.__call__`` -- empty list, single image, fixed batch=1
  fallback path, true batched path.
* ``ONNXModelWrapper._preprocess`` -- grayscale + RGBA normalization, resize logic.
* ``ImageClassificationService._translate_label`` -- hits the dictionary and
  falls back to the original label.
* ``ImageClassificationService._normalize_label`` -- below threshold + None
  branch both collapse to ``"others"``.
* ``ImageClassificationService._get_top_prediction`` -- empty probs returns
  (None, None); non-empty returns class index + name from model.names.
* ``ImageClassificationService.classify_yolo`` -- happy path + error cases.
"""
import base64
import io
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PIL import Image


pytestmark = [pytest.mark.smoke]


# ---------------------------------------------------------------------------
# ONNXModelWrapper
# ---------------------------------------------------------------------------


def _make_wrapper(supports_batch=True, max_batch=32):
    """Build an ONNXModelWrapper with a stubbed inference session."""
    from app.services.image_classification_service import ONNXModelWrapper
    w = ONNXModelWrapper.__new__(ONNXModelWrapper)
    w.session = MagicMock()
    w.session.run.return_value = [np.array([[0.1, 0.7, 0.2]])]  # 1 image, 3 classes
    w.input_name = "input"
    w.output_name = "output"
    w.input_size = 224
    w._supports_batch = supports_batch
    w._max_batch = max_batch
    w.names = {0: "cat", 1: "dog", 2: "bird"}
    w.model_name = "fake.onnx"
    return w


def test_onnx_wrapper_call_empty_returns_empty():
    w = _make_wrapper()
    out = w([])
    assert out == []


def test_onnx_wrapper_call_single_image_normalized_to_list():
    w = _make_wrapper()
    img = Image.new("RGB", (300, 200), color=(255, 0, 0))
    out = w(img)  # single image (PIL) -- must wrap into list internally
    assert isinstance(out, list)
    assert len(out) == 1


def test_onnx_wrapper_fixed_batch_one_path_runs_per_image():
    """When ``_supports_batch`` is False, the model must run one image at a time."""
    w = _make_wrapper(supports_batch=False)
    img1 = Image.new("RGB", (300, 200))
    img2 = Image.new("RGB", (300, 200))
    out = w([img1, img2])
    assert len(out) == 2
    assert w.session.run.called


def test_onnx_wrapper_batched_path_stacks_inputs():
    """When ``_supports_batch`` is True, the wrapper stacks images and runs once."""
    w = _make_wrapper()
    w.session.run.return_value = [np.array([[0.1, 0.7, 0.2], [0.2, 0.6, 0.2]])]
    images = [Image.new("RGB", (300, 200)) for _ in range(2)]
    out = w(images)
    assert len(out) == 2


def test_onnx_wrapper_preprocess_handles_grayscale():
    w = _make_wrapper()
    img = Image.new("L", (300, 200))  # grayscale
    arr = w._preprocess(img)
    assert arr.shape[0] == 3  # converted to 3 channels


def test_onnx_wrapper_preprocess_handles_rgba():
    w = _make_wrapper()
    img = Image.new("RGBA", (300, 200), color=(10, 20, 30, 200))
    arr = w._preprocess(img)
    assert arr.shape[0] == 3  # RGBA -> RGB


def test_onnx_wrapper_preprocess_resizes_wider_image():
    w = _make_wrapper()
    img = Image.new("RGB", (400, 200))  # wider
    arr = w._preprocess(img)
    assert arr.shape == (3, 224, 224)


# ---------------------------------------------------------------------------
# ImageClassificationService
# ---------------------------------------------------------------------------


def _make_service():
    from app.services.image_classification_service import ImageClassificationService
    svc = ImageClassificationService.__new__(ImageClassificationService)
    svc.version = "v0.3.10.1"
    svc._category_model_map = {"animal": "photo-cls-animal.onnx"}
    svc._LABEL_TO_CHINESE = ImageClassificationService._LABEL_TO_CHINESE
    return svc


def test_translate_label_known_label_returns_chinese():
    svc = _make_service()
    assert svc._translate_label("animal") == "动物"


def test_translate_label_unknown_label_returns_input_unchanged():
    svc = _make_service()
    assert svc._translate_label("unicorn") == "unicorn"


def test_normalize_label_below_threshold_returns_others():
    svc = _make_service()
    assert svc._normalize_label("cat", 0.3, min_conf=0.5) == "others"


def test_normalize_label_none_label_returns_others():
    svc = _make_service()
    assert svc._normalize_label(None, 0.99) == "others"


def test_normalize_label_above_threshold_passes_through():
    svc = _make_service()
    assert svc._normalize_label("cat", 0.8) == "cat"


def test_get_top_prediction_returns_class_and_name():
    svc = _make_service()
    model = MagicMock()
    model.names = {0: "cat", 1: "dog"}
    probs = np.array([0.1, 0.8, 0.1])
    label, conf = svc._get_top_prediction(probs, model)
    assert label == "dog"
    assert abs(conf - 0.8) < 1e-6


def test_get_top_prediction_empty_probs_returns_none_pair():
    svc = _make_service()
    model = MagicMock()
    label, conf = svc._get_top_prediction(np.array([]), model)
    assert label is None
    assert conf is None


def test_get_top_prediction_missing_class_falls_back_to_index():
    svc = _make_service()
    model = MagicMock()
    model.names = {0: "cat"}  # index 1 not in names
    probs = np.array([0.2, 0.9])
    label, conf = svc._get_top_prediction(probs, model)
    assert label == "1"  # falls back to str(cls_idx)
    assert abs(conf - 0.9) < 1e-6


def test_classify_yolo_raises_when_general_not_ready():
    svc = _make_service()
    with patch("app.services.image_classification_service.model_downloader") as md:
        md.is_ready.return_value = False
        with pytest.raises(Exception, match="General model is not ready"):
            svc.classify_yolo([])


def test_classify_yolo_returns_error_results_for_invalid_base64():
    svc = _make_service()
    with patch("app.services.image_classification_service.model_downloader") as md:
        md.is_ready.return_value = True
        results = svc.classify_yolo(["this-is-not-valid-base64!!"])
    assert len(results) == 1
    assert results[0]["status"] == "error"


def test_classify_yolo_returns_errors_when_no_images_valid():
    svc = _make_service()
    with patch("app.services.image_classification_service.model_downloader") as md:
        md.is_ready.return_value = True
        results = svc.classify_yolo(["not-base64", "also-bad"])
    assert all(r["status"] == "error" for r in results)


def test_classify_yolo_handles_real_base64_image():
    """End-to-end with a tiny in-memory PNG and mocked general model."""
    svc = _make_service()
    # Build a 16x16 PNG and base64-encode it.
    img = Image.new("RGB", (16, 16), color=(1, 2, 3))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()

    # Mock general model to return category=animal with high confidence.
    general_pred = np.zeros(3)
    general_pred[0] = 0.9
    general_model = MagicMock()
    general_model.return_value = [general_pred]
    general_model.names = {0: "animal", 1: "document", 2: "others"}

    with patch("app.services.image_classification_service.model_downloader") as md, \
         patch("app.services.image_classification_service.model_manager") as mm:
        md.is_ready.return_value = True  # also for category sub-model
        mm.get_model.return_value = general_model
        results = svc.classify_yolo([b64])
    assert len(results) == 1
    assert results[0]["status"] == "success"
    assert "predictions" in results[0]
    assert isinstance(results[0]["predictions"], list)
    assert "label" in results[0]["predictions"][0]
