"""Coverage for the ONNXCLIPTextWrapper / ONNXCLIPImageWrapper classes in
``app/services/embedding_service.py``.

The 2026-08-31 nightly cov scan flagged these wrappers as the largest uncovered
pocket (30 / 102 missed lines, ~70% coverage): the existing
``test_embedding_service.py`` suite deliberately stubs the wrappers themselves
to keep tests deterministic, so it never exercises the wrapper bodies:

* ``ONNXCLIPTextWrapper.__init__`` - auto-tokenizer + onnx text session
* ``ONNXCLIPTextWrapper.encode_text`` - tokenize -> onnx run -> L2-normalize
* ``ONNXCLIPImageWrapper.__init__`` - auto-processor + onnx vision session
* ``ONNXCLIPImageWrapper.encode_image`` - preprocess -> onnx run -> L2-normalize

This file mocks the heavy collaborators (``modelscope`` and
``create_inference_session``) at module level so the wrappers can run without
touching disk and without loading real ONNX sessions. Real numpy is used so the
``np.linalg.norm`` branch is exercised for real.

Naming follows the nightly gap convention: ``test_nightly_<topic>_gaps_<date>.py``.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock

import numpy as np
import pytest

from app.services.embedding_service import (
    ONNXCLIPImageWrapper,
    ONNXCLIPTextWrapper,
)


pytestmark = pytest.mark.smoke


def _patch_modelscope(monkeypatch):
    """Make ``from modelscope import AutoTokenizer`` / AutoImageProcessor return mocks."""

    fake_modelscope = MagicMock(name="modelscope")

    tokenize_result = {
        "input_ids": np.zeros((1, 4), dtype=np.int64),
        "attention_mask": np.ones((1, 4), dtype=np.int64),
    }
    fake_tokenizer = MagicMock(name="AutoTokenizer")
    fake_tokenizer.return_value = tokenize_result
    fake_modelscope.AutoTokenizer.from_pretrained = MagicMock(return_value=fake_tokenizer)

    process_result = {"pixel_values": np.zeros((1, 3, 224, 224), dtype=np.float32)}
    fake_processor = MagicMock(name="AutoImageProcessor")
    fake_processor.return_value = process_result
    fake_modelscope.AutoImageProcessor.from_pretrained = MagicMock(return_value=fake_processor)

    monkeypatch.setitem(sys.modules, "modelscope", fake_modelscope)
    return fake_tokenizer, fake_processor


def _patch_inference_session(monkeypatch, embedding_dim=4):
    """Stub ``create_inference_session`` to return a MagicMock that yields controlled outputs."""

    sessions = {}

    def fake_session(path):
        s = MagicMock(name=f"ort_session[{path}]")

        if path.endswith("textual.onnx"):
            inputs = [
                MagicMock(name="input_ids"),
                MagicMock(name="attention_mask"),
            ]
            values = np.ones((1, embedding_dim), dtype=np.float32)
        else:
            inputs = [MagicMock(name="pixel_values")]
            values = np.full((1, embedding_dim), 0.5, dtype=np.float32)

        s.get_inputs = MagicMock(return_value=inputs)
        s.run = MagicMock(return_value=[values])
        sessions[path] = (s, values)
        return s

    monkeypatch.setattr(
        "app.services.embedding_service.create_inference_session",
        fake_session,
    )
    return sessions


def test_text_wrapper_init_loads_tokenizer_and_creates_text_session(monkeypatch, tmp_path):
    fake_tokenizer, _ = _patch_modelscope(monkeypatch)
    sessions = _patch_inference_session(monkeypatch)

    model_dir = tmp_path / "clip-text"
    model_dir.mkdir()
    wrapper = ONNXCLIPTextWrapper(str(model_dir))

    # Tokenizer loaded from modelscope into the wrapper.
    assert wrapper.tokenizer is fake_tokenizer
    assert wrapper.model_dir == str(model_dir)
    # ONNX session created for the textual.onnx path inside the dir.
    text_session_path = str(model_dir / "textual.onnx")
    assert text_session_path in sessions
    assert wrapper.text_session is sessions[text_session_path][0]


def test_text_wrapper_encode_text_returns_l2_normalized_embedding(monkeypatch, tmp_path):
    _patch_modelscope(monkeypatch)
    _patch_inference_session(monkeypatch, embedding_dim=8)

    model_dir = tmp_path / "clip-text-2"
    model_dir.mkdir()
    wrapper = ONNXCLIPTextWrapper(str(model_dir))

    result = wrapper.encode_text(["hello world"])

    assert isinstance(result, np.ndarray)
    assert result.shape == (1, 8)
    # L2 normalization: every row's L2 norm must be ~1 (allowing tiny epsilon drift).
    norm = np.linalg.norm(result, axis=1)
    assert np.allclose(norm, 1.0, atol=1e-5)
    # Tokenizer was invoked with the right kwargs contract.
    wrapper.tokenizer.assert_called_once()
    call_kwargs = wrapper.tokenizer.call_args.kwargs
    assert call_kwargs["text"] == ["hello world"]
    assert call_kwargs["return_tensors"] == "np"
    assert call_kwargs["padding"] is True
    assert call_kwargs["truncation"] is True
    assert call_kwargs["max_length"] == 128


def test_image_wrapper_init_loads_processor_and_creates_vision_session(monkeypatch, tmp_path):
    _, fake_processor = _patch_modelscope(monkeypatch)
    sessions = _patch_inference_session(monkeypatch)

    model_dir = tmp_path / "clip-image"
    model_dir.mkdir()
    wrapper = ONNXCLIPImageWrapper(str(model_dir))

    assert wrapper.processor is fake_processor
    assert wrapper.model_dir == str(model_dir)
    vision_session_path = str(model_dir / "visual.onnx")
    assert vision_session_path in sessions
    assert wrapper.vision_session is sessions[vision_session_path][0]


def test_image_wrapper_encode_image_returns_l2_normalized_embedding(monkeypatch, tmp_path):
    _patch_modelscope(monkeypatch)
    _patch_inference_session(monkeypatch, embedding_dim=12)

    model_dir = tmp_path / "clip-image-2"
    model_dir.mkdir()
    wrapper = ONNXCLIPImageWrapper(str(model_dir))

    # A 16x16 RGB PIL image - enough to exercise the wrapper path without disk I/O.
    from PIL import Image

    images = [Image.new("RGB", (16, 16), color=(10, 20, 30))]

    result = wrapper.encode_image(images)

    assert isinstance(result, np.ndarray)
    assert result.shape == (1, 12)
    norm = np.linalg.norm(result, axis=1)
    assert np.allclose(norm, 1.0, atol=1e-5)
    wrapper.processor.assert_called_once()
    call_kwargs = wrapper.processor.call_args.kwargs
    assert call_kwargs["images"] is images
    assert call_kwargs["return_tensors"] == "np"
