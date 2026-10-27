"""Nightly coverage for the AI ticket-recognition helpers.

The 2026-10-27 AI coverage scan reported:

* ``services/ticket_parser.py`` at 89.9% -- 109 missed lines.  The missed
  code is the station-name cache failure path, the pinyin fallback and the
  "read the endpoint from the opposite station column" recovery.
* ``services/ticket_service.py`` at 91.7% -- 33 missed lines.  The missed
  code is the *evidence* guards that decide whether a detected card may be
  promoted to a real ticket: ``has_railway_evidence`` and
  ``_full_image_ticket``.

Both modules decide whether a blob of OCR text is a train ticket at all.  A
loose guard here turns a boarding pass or an advertisement into a bogus
ticket in the user's library, so every branch is worth a test.

Everything runs without a model: the OCR callback and the ONNX session are
plain stubs.
"""

from __future__ import annotations

import json
import re

import numpy as np
import pytest

from app.services import ticket_parser, ticket_service


pytestmark = [pytest.mark.smoke]


# ---------------------------------------------------------------------------
# services/ticket_service.py -- has_railway_evidence
# ---------------------------------------------------------------------------


def test_has_railway_evidence_needs_a_code_and_a_railway_hint():
    assert ticket_service.has_railway_evidence(["G1", "二等座"]) is True
    # A code alone is not enough.
    assert ticket_service.has_railway_evidence(["G1", "姓名"]) is False
    # A railway hint alone is not enough.
    assert ticket_service.has_railway_evidence(["二等座", "张三"]) is False


def test_has_railway_evidence_rejects_an_airline_document():
    texts = ["G3915", "经济舱", "登机口"]

    assert ticket_service.has_railway_evidence(texts) is False


def test_has_railway_evidence_accepts_a_traditional_chinese_ticket():
    texts = ["G1", "8車", "12號", "復興號"]

    assert ticket_service.has_railway_evidence(texts) is True


def test_has_railway_evidence_ignores_a_code_inside_a_word():
    # "AG1234" is not a train number.
    assert ticket_service.has_railway_evidence(["AG1234", "二等座"]) is False


# ---------------------------------------------------------------------------
# services/ticket_service.py -- _full_image_ticket
# ---------------------------------------------------------------------------


class _OcrResult:
    def __init__(self, texts, boxes):
        self.txts = texts
        self.boxes = boxes


def _full_image_ticket(texts, boxes=None, monkeypatch=None):
    """Run the full-image detector against a stubbed OCR callback."""
    import contextlib

    boxes = boxes or [[[0, 0], [100, 0], [100, 10], [0, 10]] for _ in texts]

    def fake_ocr(image, **kwargs):
        return _OcrResult(texts, boxes)

    monkeypatch.setattr(ticket_service, "openvino_infer_lock", lambda: contextlib.nullcontext())
    return ticket_service._full_image_ticket(np.zeros((10, 10, 3), dtype="uint8"), fake_ocr)


def test_full_image_ticket_requires_railway_evidence(monkeypatch):
    assert _full_image_ticket(["张三", "李四"], monkeypatch=monkeypatch) is None


def test_full_image_ticket_requires_both_endpoints(monkeypatch):
    result = _full_image_ticket(["G1", "北京南", "二等座"], monkeypatch=monkeypatch)

    assert result is None


def test_full_image_ticket_requires_a_parsable_date(monkeypatch):
    texts = ["G1", "北京南", "上海虹桥", "二等座"]

    assert _full_image_ticket(texts, monkeypatch=monkeypatch) is None


def test_full_image_ticket_accepts_a_complete_ticket(monkeypatch):
    texts = ["G1", "北京南", "上海虹桥", "2026年01月01日 08:00", "二等座"]

    result = _full_image_ticket(texts, monkeypatch=monkeypatch)

    assert result is not None
    assert result["type"] == "train"
    assert result["detection_id"] == 0


# ---------------------------------------------------------------------------
# services/ticket_service.py -- recover_station_line
# ---------------------------------------------------------------------------


def test_recover_station_line_needs_exactly_one_endpoint(monkeypatch):
    info = {"train_code": "G1", "departure_station": "北京南", "arrival_station": "上海虹桥"}

    ticket_service.recover_station_line(
        info, np.zeros((10, 10, 3), dtype="uint8"), [], [], lambda *a, **k: None
    )

    assert "station_source" not in info


def test_recover_station_line_needs_a_train_code(monkeypatch):
    info = {"train_code": "", "departure_station": "北京南"}

    ticket_service.recover_station_line(
        info, np.zeros((10, 10, 3), dtype="uint8"), [], [], lambda *a, **k: None
    )

    assert "station_source" not in info


def test_recover_station_line_survives_a_broken_ocr(monkeypatch):
    info = {"train_code": "G1", "departure_station": "北京南"}
    image = np.zeros((20, 20, 3), dtype="uint8")
    polys = [[[0, 0], [10, 0], [10, 5], [0, 5]]]
    texts = ["北京南"]

    def broken_ocr(*args, **kwargs):
        raise RuntimeError("ocr offline")

    monkeypatch.setattr(ticket_service, "openvino_infer_lock",
                        lambda: __import__("contextlib").nullcontext())
    ticket_service.recover_station_line(info, image, texts, polys, broken_ocr)

    assert "station_source" not in info


# ---------------------------------------------------------------------------
# services/ticket_service.py -- recover_mirrored_card
# ---------------------------------------------------------------------------


def test_recover_mirrored_card_keeps_a_readable_ticket(monkeypatch):
    info = {"train_code": "G1", "departure_station": "北京南", "arrival_station": "上海虹桥",
            "datetime": "2026年01月01日 08:00"}
    image = np.zeros((10, 10, 3), dtype="uint8")
    texts = ["G1"]
    polys = [[[0, 0], [10, 0], [10, 5], [0, 5]]]

    def never_called(*args, **kwargs):
        raise AssertionError("a readable ticket must not be re-read")

    result, out_texts, out_polys = ticket_service.recover_mirrored_card(
        info, image, texts, polys, never_called
    )

    assert result is info
    assert out_texts is texts


def test_recover_mirrored_card_survives_a_broken_ocr(monkeypatch):
    info = {"train_code": "G1"}
    image = np.zeros((10, 10, 3), dtype="uint8")

    def broken_ocr(*args, **kwargs):
        raise RuntimeError("ocr offline")

    monkeypatch.setattr(ticket_service, "openvino_infer_lock",
                        lambda: __import__("contextlib").nullcontext())
    result, _, _ = ticket_service.recover_mirrored_card(
        info, image, [], [], broken_ocr
    )

    assert result is info


# ---------------------------------------------------------------------------
# services/ticket_service.py -- _ticket_readability
# ---------------------------------------------------------------------------


def test_ticket_readability_counts_the_known_endpoints():
    info = {"train_code": "G1", "departure_station": "北京南", "arrival_station": "上海虹桥",
            "datetime": "2026年01月01日 08:00"}

    known, has_code, date_ok = ticket_service._ticket_readability(info)

    assert known == 2
    assert has_code is True
    assert date_ok is True


def test_ticket_readability_rejects_an_unknown_endpoint():
    info = {"train_code": "G1", "departure_station": "并不存在的站",
            "arrival_station": "上海虹桥", "datetime": "2026年01月01日 08:00"}

    known, _, _ = ticket_service._ticket_readability(info)

    assert known == 1


def test_ticket_readability_rejects_a_broken_date():
    info = {"train_code": "G1", "departure_station": "北京南", "arrival_station": "上海虹桥",
            "datetime": "not-a-date"}

    _, _, date_ok = ticket_service._ticket_readability(info)

    assert date_ok is False


# ---------------------------------------------------------------------------
# services/ticket_parser.py -- station name helpers
# ---------------------------------------------------------------------------


def test_is_valid_station_name_rejects_a_weekday(monkeypatch):
    monkeypatch.setattr(ticket_parser, "_get_valid_station_names", lambda: {"北京南"})

    assert ticket_parser._is_valid_station_name("周二") is False
    assert ticket_parser._is_valid_station_name("星期三") is False


def test_is_valid_station_name_accepts_a_known_single_character(monkeypatch):
    monkeypatch.setattr(ticket_parser, "_get_valid_station_names", lambda: {"北"})

    assert ticket_parser._is_valid_station_name("北") is True
    assert ticket_parser._is_valid_station_name("南") is False


def test_is_valid_station_name_rejects_an_out_of_range_length(monkeypatch):
    monkeypatch.setattr(ticket_parser, "_get_valid_station_names", lambda: set())

    assert ticket_parser._is_valid_station_name("一二三四五六七八九") is False


def test_get_valid_station_names_survives_a_missing_data_file(monkeypatch):
    """A missing station dictionary must not crash the recogniser."""
    def broken_open(*args, **kwargs):
        raise OSError("station dictionary missing")

    monkeypatch.setattr(ticket_parser, "_VALID_STATION_NAMES", set())
    monkeypatch.setattr(ticket_parser, "open", broken_open, raising=False)

    assert ticket_parser._get_valid_station_names() == set()


def test_station_from_printed_pinyin_survives_a_missing_dictionary(monkeypatch):
    def broken_open(*args, **kwargs):
        raise OSError("pinyin dictionary missing")

    monkeypatch.setattr(ticket_parser, "_STATION_PINYIN", None)
    monkeypatch.setattr(ticket_parser, "_get_valid_station_names", lambda: set())
    monkeypatch.setattr(ticket_parser, "open", broken_open, raising=False)

    poly = [[0, 0], [10, 0], [10, 10], [0, 10]]

    # The name is not known and the poly is complete, so the pinyin path runs
    # and must fall back to the original name instead of raising.
    result = ticket_parser._station_from_printed_pinyin("测试站", poly, [], [])

    assert result == "测试站"


# ---------------------------------------------------------------------------
# services/ticket_parser.py -- _extract_month_day / _extract_hhmm
# ---------------------------------------------------------------------------


def test_extract_month_day_rejects_a_discount_block():
    assert ticket_parser._extract_month_day("6.6折") is None


def test_extract_month_day_rejects_a_price_block():
    assert ticket_parser._extract_month_day("￥12.5") is None
    assert ticket_parser._extract_month_day("5.5元") is None


def test_extract_month_day_rejects_an_impossible_date():
    assert ticket_parser._extract_month_day("13.40") is None


def test_extract_hhmm_returns_an_empty_string_for_a_blank_input():
    assert ticket_parser._extract_hhmm("") == ""
    assert ticket_parser._extract_hhmm("没有时间") == ""


def test_extract_hhmm_pads_a_single_digit_hour():
    assert ticket_parser._extract_hhmm("9:05") == "09:05"
    assert ticket_parser._extract_hhmm("18：18") == "18:18"


# ---------------------------------------------------------------------------
# services/ticket_parser.py -- parse_ticket_cards
# ---------------------------------------------------------------------------


def _poly(y):
    return [[0, y], [100, y], [100, y + 10], [0, y + 10]]


def test_parse_ticket_cards_keeps_a_single_anchor():
    texts = ["G1", "北京南"]
    polys = [_poly(0), _poly(20)]

    cards = ticket_parser.parse_ticket_cards(texts, polys)

    assert len(cards) == 1


def test_parse_ticket_cards_keeps_two_anchors_that_are_too_close():
    texts = ["G1", "G2"]
    polys = [_poly(0), _poly(20)]

    cards = ticket_parser.parse_ticket_cards(texts, polys)

    assert len(cards) == 1


def test_parse_ticket_cards_rejects_an_incomplete_card():
    texts = ["G1", "G2"]
    polys = [_poly(0), _poly(200)]

    cards = ticket_parser.parse_ticket_cards(texts, polys)

    # The split could not produce complete cards, so the original result stays.
    assert len(cards) == 1
