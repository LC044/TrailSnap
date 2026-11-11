"""Nightly gap coverage (2026-11-11) — app/services/ticket_service.py.

The 2026-11-11 AI coverage scan reported ``ticket_service.py`` at 94.9% with
20 uncovered lines.  The remaining reachable branches live in the two
"second opinion" helpers:

* ``_full_image_ticket`` — the full-page fallback only accepts a page that
  carries real railway evidence, a complete train code / station pair and a
  printed date; anything less is rejected instead of returning half a ticket.
* ``supplement_train_code`` — when the detector cropped one card, the missing
  counterpart station and the printed date may be imported from the same
  card's full-image parse, but only when both endpoints agree.

No model is loaded and no image is decoded: the OCR session and the parser
are stubbed, so the file stays fast and CI-safe.
"""

from __future__ import annotations

import contextlib
from unittest.mock import patch

import numpy as np
import pytest

from app.services import ticket_service


pytestmark = [pytest.mark.smoke, pytest.mark.module_ticket]


@contextlib.contextmanager
def _null_lock():
    yield


def _fake_ocr(result=None):
    """Minimal stand-in for the ONNX OCR session."""
    def ocr(image, **kwargs):
        return result
    return ocr


def _image():
    return np.zeros((64, 64, 3), dtype=np.uint8)


# --------------------------------------------------------------------------- #
# _full_image_ticket
# --------------------------------------------------------------------------- #

def test_full_image_ticket_requires_railway_evidence():
    """A page without railway evidence is not a ticket."""
    with patch.object(ticket_service, "openvino_infer_lock", _null_lock), \
            patch.object(ticket_service, "_ocr_blocks", return_value=(["票价 100 元"], [])), \
            patch.object(ticket_service, "has_railway_evidence", return_value=False):
        assert ticket_service._full_image_ticket(_image(), _fake_ocr()) is None


def test_full_image_ticket_requires_train_code_and_both_stations():
    """Train code plus departure and arrival are all mandatory."""
    with patch.object(ticket_service, "openvino_infer_lock", _null_lock), \
            patch.object(ticket_service, "_ocr_blocks",
                         return_value=(["北京南站 上海虹桥站"], [])), \
            patch.object(ticket_service, "has_railway_evidence", return_value=True), \
            patch.object(ticket_service, "parse_ticket_info",
                         return_value={"train_code": "", "departure_station": "北京南",
                                       "arrival_station": "上海虹桥", "datetime": "5月2日 08:30"}):
        assert ticket_service._full_image_ticket(_image(), _fake_ocr()) is None


def test_full_image_ticket_requires_a_printed_date():
    """Without a date the page cannot be trusted as a train ticket."""
    with patch.object(ticket_service, "openvino_infer_lock", _null_lock), \
            patch.object(ticket_service, "_ocr_blocks",
                         return_value=(["北京南站 G1234 上海虹桥站"], [])), \
            patch.object(ticket_service, "has_railway_evidence", return_value=True), \
            patch.object(ticket_service, "parse_ticket_info",
                         return_value={"train_code": "G1234", "departure_station": "北京南",
                                       "arrival_station": "上海虹桥", "datetime": "12:30"}):
        assert ticket_service._full_image_ticket(_image(), _fake_ocr()) is None


def test_full_image_ticket_returns_the_parsed_ticket():
    """A complete page is returned as a train ticket."""
    parsed = {"train_code": "G1234", "departure_station": "北京南",
              "arrival_station": "上海虹桥", "datetime": "2026-05-02 08:30"}
    with patch.object(ticket_service, "openvino_infer_lock", _null_lock), \
            patch.object(ticket_service, "_ocr_blocks",
                         return_value=(["北京南站 G1234 上海虹桥站"], [])), \
            patch.object(ticket_service, "has_railway_evidence", return_value=True), \
            patch.object(ticket_service, "parse_ticket_info", return_value=parsed):
        info = ticket_service._full_image_ticket(_image(), _fake_ocr())
    assert info["train_code"] == "G1234"
    assert info["type"] == "train"
    assert info["detection_id"] == 0


# --------------------------------------------------------------------------- #
# supplement_train_code
# --------------------------------------------------------------------------- #

def _supplement(info, full):
    """Run ``supplement_train_code`` with a stubbed OCR + parser."""
    with patch.object(ticket_service, "openvino_infer_lock", _null_lock), \
            patch.object(ticket_service, "_ocr_blocks",
                         return_value=(["北京南站 G1234 上海虹桥站"], [(0, 0, 10, 10)])), \
            patch.object(ticket_service, "resolve_train_code", return_value="G1234"), \
            patch.object(ticket_service, "candidate_train_codes", return_value={"G1234"}), \
            patch.object(ticket_service, "parse_ticket_info", return_value=full), \
            patch("app.services.ticket_journey_parser.extract_journey_time", return_value={}):
        ticket_service.supplement_train_code(info, _image(), _fake_ocr())
    return info


def test_supplement_train_code_imports_the_missing_endpoint():
    """The counterpart station may be imported from the same card."""
    info = {"train_code": "G1234", "departure_station": "北京南",
            "arrival_station": "", "datetime": ""}
    full = {"train_code": "G1234", "departure_station": "北京南",
            "arrival_station": "上海虹桥", "datetime": "2026-05-02 08:30"}
    _supplement(info, full)
    assert info["arrival_station"] == "上海虹桥"


def test_supplement_train_code_imports_the_printed_date():
    """The printed date may be imported when the crop lost it."""
    info = {"train_code": "G1234", "departure_station": "北京南",
            "arrival_station": "上海虹桥", "datetime": ""}
    full = {"train_code": "G1234", "departure_station": "北京南",
            "arrival_station": "上海虹桥", "datetime": "2026-05-02 08:30"}
    _supplement(info, full)
    assert info["datetime"] == "2026-05-02 08:30"


def test_supplement_train_code_keeps_conflicting_endpoints():
    """Endpoints that disagree with the full image must not be merged."""
    info = {"train_code": "G1234", "departure_station": "北京南",
            "arrival_station": "上海虹桥", "datetime": "2026-05-02 08:30"}
    full = {"train_code": "G1234", "departure_station": "北京南",
            "arrival_station": "南京南", "datetime": "2026-05-02 08:30"}
    _supplement(info, full)
    assert info["arrival_station"] == "上海虹桥"


def test_supplement_train_code_ignores_ambiguous_train_codes():
    """More than one service on the page is ambiguous -> keep the crop result."""
    info = {"train_code": "G1234", "departure_station": "北京南",
            "arrival_station": "", "datetime": ""}
    with patch.object(ticket_service, "openvino_infer_lock", _null_lock), \
            patch.object(ticket_service, "_ocr_blocks",
                         return_value=(["G1234 G5678"], [(0, 0, 10, 10)])), \
            patch.object(ticket_service, "resolve_train_code", return_value="G1234"), \
            patch.object(ticket_service, "candidate_train_codes",
                         return_value={"G1234", "G5678"}), \
            patch.object(ticket_service, "parse_ticket_info", return_value={}):
        ticket_service.supplement_train_code(info, _image(), _fake_ocr())
    assert info["arrival_station"] == ""
