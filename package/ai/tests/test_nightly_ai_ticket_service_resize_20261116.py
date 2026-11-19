"""2026-11-16 nightly coverage (round 2) for ``app/services/ticket_service.py``.

The AI coverage scan of 2026-11-16 still reported two lines of
``services/ticket_service.py`` as uncovered:

* line 309 -- the aspect-ratio preserving resize of a page whose size differs
  from the detector input size (the earlier round only used a square 64x64
  page, which skipped the resize);
* line 522 -- the summary log for filtered detections.  ``filtered_count`` is
  never incremented in the current implementation, so this branch is dead
  code and is deliberately not forced here.

No model is downloaded: the YOLO session and the OCR session are stubbed and
the page is written into a pytest ``tmp_path``.
"""

from __future__ import annotations

import contextlib
from unittest.mock import patch

import cv2
import numpy as np
import pytest

from app.services import ticket_service


pytestmark = [pytest.mark.smoke, pytest.mark.module_ticket]

IMAGE_SIZE = 64


@contextlib.contextmanager
def _null_lock():
    yield


class _FakeInput:
    def __init__(self, name: str, shape):
        self.name = name
        self.shape = shape


class _FakeYoloSession:
    """Minimal stand-in for the ONNX YOLO ticket detector."""

    def __init__(self, names, detections):
        self.names = names
        self._detections = detections

    def get_inputs(self):
        return [_FakeInput("images", [1, 3, IMAGE_SIZE, IMAGE_SIZE])]

    def run(self, _outputs, _feed):
        n = len(self._detections)
        preds = np.zeros((1, 4 + len(self.names), max(n, 1)), dtype=np.float32)
        for i, (cls_id, conf, xc, yc, w, h) in enumerate(self._detections):
            preds[0, 0, i] = xc
            preds[0, 1, i] = yc
            preds[0, 2, i] = w
            preds[0, 3, i] = h
            preds[0, 4 + cls_id, i] = conf
        return [preds]


def _image_bytes(shape=(IMAGE_SIZE, IMAGE_SIZE)) -> bytes:
    img = np.zeros((shape[0], shape[1], 3), dtype=np.uint8)
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return buf.tobytes()


def test_a_non_square_page_is_resized_before_detection(monkeypatch, tmp_path):
    """A page that differs from the detector input size goes through cv2.resize."""
    monkeypatch.chdir(tmp_path)
    session = _FakeYoloSession({0: "label", 1: "label1"}, [])
    real_resize = cv2.resize
    calls = []

    def counting_resize(image, size, **kwargs):
        calls.append((image.shape, size))
        return real_resize(image, size, **kwargs)

    with patch.object(ticket_service.ai_model_manager, "is_ready", return_value=True), \
            patch.object(ticket_service.model_manager, "get_model", return_value=session), \
            patch.object(ticket_service, "openvino_infer_lock", _null_lock), \
            patch.object(ticket_service, "_full_image_ticket", return_value=None), \
            patch.object(ticket_service.cv2, "resize", counting_resize):
        result = ticket_service.TicketService().detect(_image_bytes((100, 50)))

    assert calls, "the page should have been resized for the detector"
    assert result["count"] == 0


def test_a_square_page_of_the_input_size_is_not_resized(monkeypatch, tmp_path):
    """The resize branch is skipped when the page already matches the input."""
    monkeypatch.chdir(tmp_path)
    session = _FakeYoloSession({0: "label", 1: "label1"}, [])
    calls = []

    def counting_resize(image, size, **kwargs):
        calls.append(size)
        return cv2.resize(image, size, **kwargs)

    with patch.object(ticket_service.ai_model_manager, "is_ready", return_value=True), \
            patch.object(ticket_service.model_manager, "get_model", return_value=session), \
            patch.object(ticket_service, "openvino_infer_lock", _null_lock), \
            patch.object(ticket_service, "_full_image_ticket", return_value=None), \
            patch.object(ticket_service.cv2, "resize", counting_resize):
        result = ticket_service.TicketService().detect(_image_bytes())

    assert calls == []
    assert result["count"] == 0
