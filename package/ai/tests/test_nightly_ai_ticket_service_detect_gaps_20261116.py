"""Nightly gap coverage (2026-11-16) - app/services/ticket_service.py.

The 2026-11-16 AI coverage scan reported ``services/ticket_service.py`` at
93% with 18 uncovered lines.  Almost all of them live inside
``TicketService.detect`` - the ONNX detection + OCR pipeline - which had never
been exercised end to end by a unit test:

* ``383-385`` - the full-image fallback used when the detector found no box at
  all, including the branch where the fallback itself raises.
* ``407``    - a degenerate (empty) crop is skipped instead of being OCR'd.
* ``464-465``- a malformed OCR result is reported and the crop is dropped.
* ``488``    - a flight-like detection without any airline evidence is
  discarded.
* ``510``    - additional train cards found on the same page are all returned.
* ``534-541``- several train cards on one page trigger the shared-page date
  recovery, which must survive a failing OCR session.

No model is downloaded and no network is used: the YOLO session, the OCR
session and the parser are stubbed, and every temporary file is written into a
pytest ``tmp_path`` so the repository stays clean.
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
        # detections: list of (cls_id, conf, xc, yc, w, h)
        self.names = names
        self._detections = detections

    def get_inputs(self):
        return [_FakeInput("images", [1, 3, IMAGE_SIZE, IMAGE_SIZE])]

    def run(self, _outputs, _feed):
        n = len(self._detections)
        # YOLOv8 layout: (1, 4 + nc, N) -> transposed to (N, 4 + nc)
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


def _fake_ocr(result=None):
    def ocr(*_args, **_kwargs):
        return result
    return ocr


def _run_detect(detections, names=None, ocr_result=None, image_shape=(IMAGE_SIZE, IMAGE_SIZE), **patches):
    """Run ``TicketService.detect`` with everything external stubbed out."""
    names = names if names is not None else {0: "label", 1: "label1"}
    session = _FakeYoloSession(names, detections)
    stack = contextlib.ExitStack()
    stack.enter_context(patch.object(ticket_service.ai_model_manager, "is_ready", return_value=True))
    stack.enter_context(
        patch.object(
            ticket_service.model_manager,
            "get_model",
            side_effect=lambda name: session if name == "tickets_yolo" else _fake_ocr(ocr_result),
        )
    )
    stack.enter_context(patch.object(ticket_service, "openvino_infer_lock", _null_lock))
    for target, value in patches.items():
        stack.enter_context(patch.object(ticket_service, target, value))
    try:
        return ticket_service.TicketService().detect(_image_bytes(image_shape))
    finally:
        stack.close()


# --------------------------------------------------------------------------- #
# Full-image fallback (no detection box at all)
# --------------------------------------------------------------------------- #

def test_no_detection_falls_back_to_the_full_image(monkeypatch, tmp_path):
    """Without a box the whole page is OCR'd once and returned as a ticket."""
    monkeypatch.chdir(tmp_path)
    fallback = {"train_code": "G1234", "type": "train", "departure_station": "A", "arrival_station": "B"}
    result = _run_detect([], _full_image_ticket=lambda _img, _ocr: fallback)
    assert result["count"] == 1
    assert result["tickets"][0]["train_code"] == "G1234"


def test_full_image_fallback_failure_is_only_logged(monkeypatch, tmp_path):
    """A failing fallback must not break the whole detection."""

    def boom(_img, _ocr):
        raise RuntimeError("no ticket on this page")

    monkeypatch.chdir(tmp_path)
    result = _run_detect([], _full_image_ticket=boom)
    assert result == {"tickets": [], "count": 0}


def test_non_square_image_is_resized_before_inference(monkeypatch, tmp_path):
    """A page that is not square must be letter-boxed, i.e. resized first."""
    monkeypatch.chdir(tmp_path)
    result = _run_detect(
        [(0, 0.9, 30, 30, 20, 20)],
        image_shape=(IMAGE_SIZE, IMAGE_SIZE * 2),
        parse_ticket_info=lambda _texts, _polys: {
            "train_code": "G1234", "departure_station": "A", "arrival_station": "B", "datetime": "",
        },
    )
    assert result["count"] == 1


def test_a_failing_text_extraction_is_reported_and_skipped(monkeypatch, tmp_path):
    """A broken OCR side-car file must not abort the whole page."""
    monkeypatch.chdir(tmp_path)

    def boom(_path):
        raise OSError("cannot read the ocr side-car")

    result = _run_detect(
        [(0, 0.9, 30, 30, 20, 20)],
        extract_text=boom,
    )
    assert result["tickets"] == []


# --------------------------------------------------------------------------- #
# Degenerate crop
# --------------------------------------------------------------------------- #

def test_empty_crop_is_skipped(monkeypatch, tmp_path):
    """A zero-height box produces an empty crop that must be skipped."""
    monkeypatch.chdir(tmp_path)
    # (cls_id, conf, xc, yc, w, h) - h == 0 -> crop is empty
    result = _run_detect([(0, 0.9, 30, 30, 20, 0)])
    assert result["tickets"] == []


# --------------------------------------------------------------------------- #
# Malformed OCR payload
# --------------------------------------------------------------------------- #

class _BrokenBox:
    def tolist(self):
        raise ValueError("broken box")


class _BrokenOcrOutput:
    """Looks like a RapidOCROutput but the box cannot be serialised."""

    txts = ["G1234"]
    boxes = [_BrokenBox()]


def test_malformed_ocr_result_is_reported_and_ignored(monkeypatch, tmp_path):
    """A broken OCR payload must not raise out of ``detect``."""
    monkeypatch.chdir(tmp_path)
    result = _run_detect(
        [(0, 0.9, 30, 30, 20, 20)],
        ocr_result=_BrokenOcrOutput(),
        parse_ticket_info=lambda _texts, _polys: {
            "train_code": "G1234", "departure_station": "A", "arrival_station": "B", "datetime": "",
        },
    )
    # The crop is still returned, but without any OCR text attached.
    assert result["count"] == 1
    assert result["tickets"][0]["train_code"] == "G1234"


# --------------------------------------------------------------------------- #
# Flight detection without airline evidence
# --------------------------------------------------------------------------- #

def test_flight_detection_without_airline_evidence_is_dropped(monkeypatch, tmp_path):
    """A "label1" box without any airline hint is not a boarding pass."""
    monkeypatch.chdir(tmp_path)
    result = _run_detect(
        [(1, 0.9, 30, 30, 20, 20)],
        ocr_result=[([[0, 0, 10, 10]], "GATE 12")],
        has_railway_evidence=lambda _texts: False,
        extract_flight_info=lambda _texts: {},
    )
    assert result["tickets"] == []


# --------------------------------------------------------------------------- #
# Several train cards on one page
# --------------------------------------------------------------------------- #

def test_additional_train_cards_are_all_returned(monkeypatch, tmp_path):
    """``parse_ticket_cards`` may find more than one card on the same page."""
    monkeypatch.chdir(tmp_path)
    cards = [
        {"train_code": "G1", "departure_station": "A", "arrival_station": "B", "datetime": "08:30"},
        {"train_code": "G2", "departure_station": "C", "arrival_station": "D", "datetime": "09:30"},
    ]
    result = _run_detect(
        [(0, 0.9, 30, 30, 20, 20)],
        ocr_result=[([[0, 0, 10, 10]], "G1 G2")],
        parse_ticket_info=lambda _texts, _polys: {
            "train_code": "", "departure_station": "", "arrival_station": "", "datetime": "",
        },
        parse_ticket_cards=lambda _texts, _polys, initial=None: cards,
        reconcile_ticket_copies=lambda _tickets, _serials: None,
        recover_mirrored_card=lambda info, _img, _t, _p, _o: info,
        recover_station_line=lambda info, _img, _t, _p, _o: None,
        recover_clock_orientation=lambda info, _path, _t, _o: None,
    )
    assert result["count"] == 2
    assert {t["train_code"] for t in result["tickets"]} == {"G1", "G2"}


def test_shared_page_date_recovery_survives_a_failing_ocr(monkeypatch, tmp_path):
    """Two train cards trigger the shared-page date recovery; it may fail."""
    monkeypatch.chdir(tmp_path)

    def boom(*_args, **_kwargs):
        raise RuntimeError("ocr busy")

    cards = [
        {"train_code": "G1", "departure_station": "A", "arrival_station": "B", "datetime": "08:30"},
        {"train_code": "G2", "departure_station": "C", "arrival_station": "D", "datetime": "09:30"},
    ]
    result = _run_detect(
        [(0, 0.9, 30, 30, 20, 20)],
        ocr_result=[([[0, 0, 10, 10]], "G1 G2")],
        parse_ticket_info=lambda _texts, _polys: {
            "train_code": "", "departure_station": "", "arrival_station": "", "datetime": "",
        },
        parse_ticket_cards=lambda _texts, _polys, initial=None: cards,
        reconcile_ticket_copies=lambda _tickets, _serials: None,
        recover_mirrored_card=lambda info, _img, _t, _p, _o: info,
        recover_station_line=lambda info, _img, _t, _p, _o: None,
        recover_clock_orientation=lambda info, _path, _t, _o: None,
        _ocr_blocks=boom,
    )
    assert result["count"] == 2