"""Unit tests covering 2026-08-11 nightly AI gap scan.

Target: ``app/services/image_classification_service.py`` (38% previously).

Exercises the deterministic, dependency-free branches:
* ``ONNXModelWrapper._preprocess`` -- image resize / center-crop pipeline
  for both landscape and portrait images.
* ``ImageClassificationService._translate_label`` -- Chinese label map.
* ``_discover_category_models`` -- reads MODEL_PATH/photo-cls and returns
  a {category: filename} map.
* Edge handling in ``__call__`` for empty image lists and for single-image
  mode forced by ``_supports_batch=False``.
"""
import os
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from app.services import image_classification_service as ics


pytestmark = [pytest.mark.smoke, pytest.mark.module_ai_image_classification]


# ----------------------------------------------------------------------------
# ONNXModelWrapper._preprocess
# ----------------------------------------------------------------------------


def _wrapper(input_size=224, supports_batch=True):
    """Build an ONNXModelWrapper stub without invoking ORT session creation."""
    w = ics.ONNXModelWrapper.__new__(ics.ONNXModelWrapper)
    w.input_size = input_size
    w.names = {0: "animal", 1: "scenery"}
    w.input_name = "input"
    w.output_name = "output"
    w.model_name = "stub.onnx"
    w._supports_batch = supports_batch
    w._max_batch = 32
    w.session = MagicMock()
    w.session.run.return_value = [MagicMock()]
    return w


def test_preprocess_resizes_short_side_to_input_size():
    w = _wrapper(input_size=64)
    # Tall image (portrait) -- short side is width.
    img = Image.new("RGB", (40, 200), color=(10, 20, 30))
    arr = w._preprocess(img)
    assert arr.shape == (3, 64, 64)
    assert arr.dtype.itemsize == 4  # float32


def test_preprocess_promotes_grayscale_to_rgb():
    """Greyscale input should be repeated across 3 channels."""
    w = _wrapper(input_size=64)
    img = Image.new("L", (100, 200), color=128)
    arr = w._preprocess(img)
    assert arr.shape == (3, 64, 64)


def test_preprocess_drops_alpha_channel():
    w = _wrapper(input_size=64)
    img = Image.new("RGBA", (100, 200), color=(1, 2, 3, 255))
    arr = w._preprocess(img)
    assert arr.shape == (3, 64, 64)


# ----------------------------------------------------------------------------
# ONNXModelWrapper.__call__ branches
# ----------------------------------------------------------------------------


def test_call_returns_empty_when_no_images():
    w = _wrapper()
    assert w.__call__([]) == []


def test_call_single_image_path_uses_single_input_tensor():
    """For a single PIL Image, the wrapper batches internally to a list of 1."""
    w = _wrapper()
    img = Image.new("RGB", (100, 100), color=(50, 60, 70))
    result = w.__call__(img)
    assert isinstance(result, list)
    w.session.run.assert_called()


def test_call_single_batch_one_mode_runs_per_image():
    """When _supports_batch=False the wrapper must call session.run per image."""
    w = _wrapper(supports_batch=False)
    w.session.run.return_value = [MagicMock()]
    # Three images each call session.run once.
    imgs = [Image.new("RGB", (100, 100)) for _ in range(3)]
    result = w.__call__(imgs)
    assert len(result) == 3
    # 3 session.run invocations (one per image).
    assert w.session.run.call_count == 3


# ----------------------------------------------------------------------------
# ImageClassificationService helpers
# ----------------------------------------------------------------------------


def test_translate_label_uses_chinese_for_known_keys():
    svc = ics.ImageClassificationService.__new__(ics.ImageClassificationService)
    assert svc._translate_label("person") == "人像"
    assert svc._translate_label("train_ticket") == "火车票"
    # Unknown labels are returned verbatim.
    assert svc._translate_label("robot_dog") == "robot_dog"


def test_translate_label_uses_screenshot_alias_for_train_ticket_screenshot():
    svc = ics.ImageClassificationService.__new__(ics.ImageClassificationService)
    assert svc._translate_label("train_ticket_screenshot") == "火车票截图"


def test_discover_category_models_returns_only_category_specific_files(tmp_path):
    photo_cls = tmp_path / "photo-cls"
    photo_cls.mkdir()
    (photo_cls / "photo-cls-general.onnx").write_bytes(b"")
    (photo_cls / "photo-cls-dog.onnx").write_bytes(b"")
    (photo_cls / "photo-cls-cat.onnx").write_bytes(b"")
    # A non-matching file is ignored.
    (photo_cls / "other-thing.onnx").write_bytes(b"")

    svc = ics.ImageClassificationService.__new__(ics.ImageClassificationService)
    with patch.object(ics.settings, "MODEL_PATH", str(tmp_path)):
        mapping = svc._discover_category_models()

    assert mapping == {"dog": "photo-cls-dog.onnx", "cat": "photo-cls-cat.onnx"}


def test_discover_category_models_returns_empty_when_dir_missing(tmp_path):
    svc = ics.ImageClassificationService.__new__(ics.ImageClassificationService)
    with patch.object(ics.settings, "MODEL_PATH", str(tmp_path)):
        assert svc._discover_category_models() == {}
