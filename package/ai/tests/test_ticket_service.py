"""Unit tests for app/services/ticket_service.py.

The real TicketService.detect() pulls a heavy ONNX session out of
model_manager, runs a YOLOv8 forward pass, NMS, RapidOCR, and the train
/ flight ticket parsers. We mock every one of those so the test exercises
only the orchestration logic of ``detect()``.
"""

import sys
import types
from unittest.mock import MagicMock, patch

import numpy as np
import pytest


pytestmark = [pytest.mark.smoke]


# ----------------------- fixtures -----------------------


def _install_fake_cv2(monkeypatch):
    """Install a minimal cv2 stub used by the service.

    Only the symbols TicketService.detect() actually touches are provided:
    - imdecode -> returns a synthetic 640x640 RGB image
    - resize -> passthrough (the real cv2 would resize; we don't care)
    - copyMakeBorder -> passthrough
    - dnn.NMSBoxes -> deterministic first-box-only filter
    - imwrite -> no-op (return True)
    """
    fake = types.SimpleNamespace()

    def _imdecode(buf, flags):
        return np.full((640, 640, 3), 200, dtype=np.uint8)

    def _imwrite(path, img):
        return True

    def _resize(img, size, **kwargs):
        return img

    def _copy_make_border(img, top, bottom, left, right, border_type, value=None):
        h, w = img.shape[:2]
        new_h = h + top + bottom
        new_w = w + left + right
        out = np.full((new_h, new_w, 3), value[0] if value else 0, dtype=img.dtype)
        out[top:top + h, left:left + w] = img
        return out

    fake.imdecode = _imdecode
    fake.imwrite = _imwrite
    fake.resize = _resize
    fake.copyMakeBorder = _copy_make_border
    fake.IMREAD_COLOR = 1
    fake.BORDER_CONSTANT = 0

    class _NMS:
        @staticmethod
        def NMSBoxes(boxes, scores, score_threshold, nms_threshold):
            # Keep the first box (mirrors the production code's expected shape).
            return [0] if boxes else []

    dnn_mod = types.SimpleNamespace(NMSBoxes=_NMS.NMSBoxes)
    fake.dnn = dnn_mod

    monkeypatch.setitem(sys.modules, "cv2", fake)
    return fake


def _build_fake_session(class_id, class_name, conf=0.9, return_box=True):
    """Return a MagicMock that quacks like an ONNX inference session."""
    sess = MagicMock()
    sess.names = {0: "label", 1: "label1"}
    if return_box:
        # Output shape after squeeze+transpose: (8400, 84).
        preds = np.zeros((1, 84, 8400), dtype=np.float32)
        for i in range(8400):
            preds[0, 0:4, i] = [320, 320, 200, 200]  # xc, yc, w, h
            preds[0, 4 + class_id, i] = conf
        sess.run = MagicMock(return_value=[preds])
    else:
        # No detections: all class probs below threshold.
        preds = np.zeros((1, 84, 8400), dtype=np.float32)
        sess.run = MagicMock(return_value=[preds])
    sess.get_inputs = MagicMock(return_value=[MagicMock(name="images", shape=[1, 3, 640, 640])])
    return sess


@pytest.fixture
def patched_env(tmp_path, monkeypatch):
    """Patch every external dependency TicketService touches."""
    _install_fake_cv2(monkeypatch)

    # model_manager.get_model returns whatever we ask for.
    from app.services import ticket_service as ts_mod

    fake_manager = MagicMock()
    monkeypatch.setattr(ts_mod, "model_manager", fake_manager)

    fake_downloader = MagicMock()
    fake_downloader.is_ready = MagicMock(return_value=True)
    monkeypatch.setattr(ts_mod, "ai_model_manager", fake_downloader)

    # settings.MODEL_PATH -> tmp_path so the disk existence check is irrelevant.
    ts_mod.settings.MODEL_PATH = str(tmp_path)

    # Stub out the OCR model so we don't need rapidocr.
    monkeypatch.setattr(
        ts_mod,
        "openvino_infer_lock",
        MagicMock(),
    )
    return {
        "module": ts_mod,
        "manager": fake_manager,
        "downloader": fake_downloader,
    }


# ----------------------- tests -----------------------


def test_detect_raises_when_model_not_ready(patched_env, monkeypatch):
    """If the model is not yet downloaded, detect() must surface an error."""
    patched_env["downloader"].is_ready = MagicMock(return_value=False)
    # Also force the disk-existence fallback path.
    patched_env["module"].settings.MODEL_PATH = str(__import__("pathlib").Path.cwd() / "definitely_missing_dir")

    svc = patched_env["module"].TicketService()
    with pytest.raises(Exception, match="not ready"):
        svc.detect(b"\x89PNG\r\n\x1a\nfakebytes")


def test_detect_raises_value_error_on_undecodable_bytes(patched_env, monkeypatch):
    """If cv2.imdecode returns None, detect() raises ValueError."""
    patched_env["manager"].get_model = MagicMock(return_value=_build_fake_session(0, "label"))
    monkeypatch.setattr(patched_env["module"].cv2, "imdecode", lambda buf, flags: None)

    svc = patched_env["module"].TicketService()
    with pytest.raises(ValueError, match="Could not decode"):
        svc.detect(b"\x00\x00\x00not a real image")


def test_detect_returns_empty_when_no_detections(patched_env, monkeypatch):
    """Empty predictions -> empty ticket list, count=0."""
    patched_env["manager"].get_model = MagicMock(return_value=_build_fake_session(0, "label", return_box=False))
    monkeypatch.setattr(patched_env["module"].cv2, "imdecode", lambda buf, flags: np.full((640, 640, 3), 128, dtype=np.uint8))

    svc = patched_env["module"].TicketService()
    result = svc.detect(b"any bytes")

    assert result == {"tickets": [], "count": 0}


def test_detect_parses_train_ticket_when_label_class_matches(patched_env, monkeypatch, tmp_path):
    """class_id=0 ('label') -> parse_ticket_info branch is used."""
    patched_env["manager"].get_model = MagicMock(return_value=_build_fake_session(0, "label"))
    monkeypatch.setattr(patched_env["module"].cv2, "imdecode", lambda buf, flags: np.full((640, 640, 3), 200, dtype=np.uint8))

    # OCR result must look like a RapidOCROutput (txts/boxes) so the
    # service walks the "object" branch in its result-format dispatch.
    ocr_out = MagicMock()
    ocr_out.txts = ["G100", "Beijing", "Shanghai"]
    ocr_out.boxes = [[[0, 0], [10, 0], [10, 10], [0, 10]]] * 3
    ocr_model = MagicMock(return_value=(ocr_out,))
    patched_env["manager"].get_model = MagicMock(side_effect=lambda name: ocr_model if name == "ocr" else _build_fake_session(0, "label"))

    monkeypatch.setattr(
        patched_env["module"],
        "parse_ticket_info",
        MagicMock(return_value={"train_code": "G100", "from": "Beijing", "to": "Shanghai"}),
    )
    monkeypatch.setattr(
        patched_env["module"],
        "extract_text",
        MagicMock(return_value=(["G100", "Beijing", "Shanghai"], ocr_out.boxes)),
    )
    monkeypatch.setattr(
        patched_env["module"],
        "extract_flight_info",
        MagicMock(return_value={"flight_code": "CA999"}),  # should NOT be called
    )

    svc = patched_env["module"].TicketService()
    result = svc.detect(b"any bytes")

    assert result["count"] == 1
    ticket = result["tickets"][0]
    assert ticket["type"] == "train"
    assert ticket["train_code"] == "G100"
    assert ticket["detection_id"] == 0
    patched_env["module"].extract_flight_info.assert_not_called()


def test_detect_parses_flight_ticket_when_label1_class_matches(patched_env, monkeypatch):
    """class_id=1 ('label1') -> extract_flight_info branch is used."""
    patched_env["manager"].get_model = MagicMock(return_value=_build_fake_session(1, "label1"))
    monkeypatch.setattr(patched_env["module"].cv2, "imdecode", lambda buf, flags: np.full((640, 640, 3), 50, dtype=np.uint8))

    ocr_out = MagicMock()
    ocr_out.txts = ["CA1234", "2025-09-27 13:25"]
    ocr_out.boxes = [[[0, 0], [10, 0], [10, 10], [0, 10]]] * 2
    ocr_model = MagicMock(return_value=(ocr_out,))
    patched_env["manager"].get_model = MagicMock(side_effect=lambda name: ocr_model if name == "ocr" else _build_fake_session(1, "label1"))

    monkeypatch.setattr(
        patched_env["module"],
        "extract_text",
        MagicMock(return_value=(ocr_out.txts, ocr_out.boxes)),
    )
    monkeypatch.setattr(
        patched_env["module"],
        "extract_flight_info",
        MagicMock(return_value={"flight_code": "CA1234", "date": "2025-09-27"}),
    )
    monkeypatch.setattr(
        patched_env["module"],
        "parse_ticket_info",
        MagicMock(return_value={"train_code": "GXXX"}),  # should NOT be called
    )

    svc = patched_env["module"].TicketService()
    result = svc.detect(b"any bytes")

    assert result["count"] == 1
    ticket = result["tickets"][0]
    assert ticket["type"] == "flight"
    assert ticket["flight_code"] == "CA1234"
    patched_env["module"].parse_ticket_info.assert_not_called()


def test_detect_keeps_going_when_ocr_inference_raises(patched_env, monkeypatch):
    """OCR exception for one crop must not abort the whole call.

    Production wraps each crop in try/except so a transient OCR failure
    yields an empty text/poly list, which the parsers then turn into
    an empty ticket dict. Either way, detect() returns a structure, it
    does not raise.
    """
    patched_env["manager"].get_model = MagicMock(return_value=_build_fake_session(0, "label"))
    monkeypatch.setattr(patched_env["module"].cv2, "imdecode", lambda buf, flags: np.full((640, 640, 3), 200, dtype=np.uint8))

    ocr_model = MagicMock(side_effect=RuntimeError("OCR backend exploded"))
    patched_env["manager"].get_model = MagicMock(side_effect=lambda name: ocr_model if name == "ocr" else _build_fake_session(0, "label"))

    monkeypatch.setattr(
        patched_env["module"],
        "extract_text",
        MagicMock(side_effect=OSError("temp json missing")),
    )
    monkeypatch.setattr(
        patched_env["module"],
        "parse_ticket_info",
        MagicMock(return_value={"train_code": "G1"}),
    )
    monkeypatch.setattr(
        patched_env["module"],
        "extract_flight_info",
        MagicMock(return_value={"flight_code": "CA1"}),
    )

    svc = patched_env["module"].TicketService()
    # Must not raise.
    result = svc.detect(b"any bytes")
    assert "tickets" in result
    assert "count" in result
    # No ticket could be parsed from the empty OCR result.
    assert result["count"] == 0
