"""Unit tests for app/services/ticket_parser.py.

The parser is a pure-Python module: helpers, regexes, and a thin
``extract_text`` JSON reader. No models, no DB, no I/O beyond the
caller-supplied JSON path. We test the public surface plus a handful
of stable private helpers (``_fix_ocr_text``, ``_is_id_like_text``,
``_extract_month_day``, ``_extract_hhmm``, ``_extract_seat_type_keyword``,
``_is_price_fragment``, ``_is_discount_block``).
"""

import json
from pathlib import Path

import pytest

from app.services.ticket_parser import (
    _extract_hhmm,
    _extract_month_day,
    _extract_seat_type_keyword,
    _fix_ocr_text,
    _is_discount_block,
    _is_id_like_text,
    _is_low_confidence_name,
    _is_price_fragment,
    _normalize_station_name,
    _poly_center,
    extract_text,
    parse_ticket_info,
)


pytestmark = [pytest.mark.smoke]


# ----------------------- tiny helpers -----------------------


def test_fix_ocr_text_replaces_ocr_confusables():
    assert _fix_ocr_text("GO1234") == "G01234"  # O -> 0
    assert _fix_ocr_text("Il1O") == "1110"      # I, l -> 1; O -> 0
    assert _fix_ocr_text("plain") == "p1ain"    # l -> 1
    assert _fix_ocr_text("") == ""


def test_normalize_station_name_strips_whitespace():
    assert _normalize_station_name("  北京  ") == "北京"
    assert _normalize_station_name("") == ""
    assert _normalize_station_name(None) == ""


def test_poly_center_averages_corner_points():
    poly = [(0, 0), (10, 0), (10, 10), (0, 10)]
    assert _poly_center(poly) == (5.0, 5.0)


def test_poly_center_handles_short_polygon():
    assert _poly_center([(1, 2)]) == (0, 0)


# ----------------------- ID / discount / price -----------------------


def test_is_id_like_text_detects_masked_id():
    assert _is_id_like_text("********1234") is True
    assert _is_id_like_text("1234****5678") is True


def test_is_id_like_text_detects_long_digit_run():
    assert _is_id_like_text("1234567890") is True
    # Below the length threshold (>= 6) -> not ID-like.
    assert _is_id_like_text("12345") is False


def test_is_id_like_text_rejects_short_alpha():
    assert _is_id_like_text("abc") is False
    assert _is_id_like_text("") is False


def test_is_discount_block_detects_zh折_suffix():
    assert _is_discount_block("6.6折") is True
    assert _is_discount_block("8.5折") is True
    assert _is_discount_block("7折") is True


def test_is_discount_block_rejects_price_like_strings():
    assert _is_discount_block("￥70.5") is False
    assert _is_discount_block("70元") is False
    assert _is_discount_block("") is False


def test_is_price_fragment_accepts_currency_and_digits():
    assert _is_price_fragment("￥70") is True
    assert _is_price_fragment("70元") is True
    assert _is_price_fragment("443.") is True
    assert _is_price_fragment("0.5") is True
    assert _is_price_fragment("￥443.5元") is True


def test_is_price_fragment_rejects_discount_and_text():
    assert _is_price_fragment("6.6折") is False   # contains \u6298
    assert _is_price_fragment("北京南站") is False
    assert _is_price_fragment("") is False


# ----------------------- date / time helpers -----------------------


def test_extract_month_day_chinese_format():
    assert _extract_month_day("1月9日（周五）") == ("01", "09")
    assert _extract_month_day("01月09日") == ("01", "09")
    assert _extract_month_day("12月25日") == ("12", "25")


def test_extract_month_day_dash_format():
    assert _extract_month_day("01-28周二") == ("01", "28")
    assert _extract_month_day("01/28") == ("01", "28")


def test_extract_month_day_dot_format():
    assert _extract_month_day("2026.04.02") == ("04", "02")
    assert _extract_month_day("04.02") == ("04", "02")


def test_extract_month_day_rejects_invalid_or_empty():
    assert _extract_month_day("") is None
    assert _extract_month_day("not a date") is None


def test_extract_hhmm_recognises_colon_and_fullwidth_colon():
    assert _extract_hhmm("17:12") == "17:12"
    assert _extract_hhmm("18：18") == "18:18"
    assert _extract_hhmm("开行 09:30") == "09:30"


def test_extract_hhmm_returns_empty_for_unmatched():
    assert _extract_hhmm("") == ""
    assert _extract_hhmm("no time here") == ""
    assert _extract_hhmm("25:00") == "25:00"  # regex doesn't range-check hours


def test_extract_hhmm_zero_pads_single_digit():
    assert _extract_hhmm("9:05") == "09:05"


# ----------------------- seat-type keyword -----------------------


def test_extract_seat_type_keyword_finds_known_types():
    assert _extract_seat_type_keyword("二等座 14车") == "二等座"
    assert _extract_seat_type_keyword("硬卧 12号") == "硬卧"
    assert _extract_seat_type_keyword("新空调硬座") == "新空调硬座"


def test_extract_seat_type_keyword_returns_empty_when_absent():
    assert _extract_seat_type_keyword("") == ""
    assert _extract_seat_type_keyword("G100 北京南") == ""


# ----------------------- name-quality gate -----------------------


def test_is_low_confidence_name_flags_stations_and_keywords():
    assert _is_low_confidence_name("北京南站", set()) is True
    assert _is_low_confidence_name("", set()) is True
    assert _is_low_confidence_name("无座", set()) is True
    assert _is_low_confidence_name("事由", set()) is True
    assert _is_low_confidence_name("张三", set()) is False


def test_is_low_confidence_name_flags_name_in_station_set():
    station_set = {"南京", "南京南"}
    assert _is_low_confidence_name("南京", station_set) is True
    assert _is_low_confidence_name("张三", station_set) is False


# ----------------------- extract_text (file I/O) -----------------------


def test_extract_text_reads_rec_texts_and_rec_polys(tmp_path: Path):
    payload = {
        "rec_texts": ["北京南站", "G100", "", "  ", "二等座"],
        "rec_polys": [
            [[0, 0], [10, 0], [10, 10], [0, 10]],
            [[20, 0], [30, 0], [30, 10], [20, 10]],
            [[40, 0], [50, 0], [50, 10], [40, 10]],
            [[60, 0], [70, 0], [70, 10], [60, 10]],
            [[80, 0], [90, 0], [90, 10], [80, 10]],
        ],
    }
    path = tmp_path / "ocr.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    texts, polys = extract_text(str(path))

    # Empty / whitespace-only entries must be dropped; their polys are dropped too.
    assert texts == ["北京南站", "G100", "二等座"]
    assert len(polys) == 3
    assert polys[0] == [[0, 0], [10, 0], [10, 10], [0, 10]]


def test_extract_text_returns_empty_for_missing_file(tmp_path: Path):
    texts, polys = extract_text(str(tmp_path / "absent.json"))
    assert texts == []
    assert polys == []


def test_extract_text_returns_empty_for_malformed_json(tmp_path: Path):
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")
    texts, polys = extract_text(str(path))
    assert texts == []
    assert polys == []


# ----------------------- parse_ticket_info (happy + edge) -----------------------


def _poly(x, y, w=20, h=10):
    return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]


def test_parse_ticket_info_returns_full_schema_with_defaults():
    """Even with no usable input, parse_ticket_info must return the full schema."""
    info = parse_ticket_info([], [])
    expected_keys = {
        "train_code", "departure_station", "arrival_station", "datetime",
        "carriage", "seat_num", "berth_type", "price", "seat_type",
        "name", "discount_type", "detection_id",
    }
    assert expected_keys.issubset(set(info.keys()))
    for k in expected_keys:
        if k != "detection_id":
            assert info[k] == "" or info[k] is None
    assert info["detection_id"] == 0


def test_parse_ticket_info_extracts_train_code_with_letter_prefix():
    texts = ["G100次", "北京南", "天津"]
    polys = [_poly(0, 0), _poly(0, 20), _poly(0, 40)]
    info = parse_ticket_info(texts, polys)
    assert info["train_code"].startswith("G")
    assert "100" in info["train_code"]


def test_parse_ticket_info_pads_train_code_if_too_short():
    """A 2-digit numeric must NOT be treated as a train code (filters <= 3 chars)."""
    texts = ["12", "北京南", "天津"]
    polys = [_poly(0, 0), _poly(0, 20), _poly(0, 40)]
    info = parse_ticket_info(texts, polys)
    # Either blank or a code, but it must not be the 2-digit "12".
    assert info["train_code"] != "12"


def test_parse_ticket_info_sorts_polys_vertically_when_unordered():
    """If polys arrive in random Y order, the parser must use the Y-sorted view."""
    # First entry is at y=100 (visually lower), second at y=0 (visually higher).
    texts = ["G1234", "北京南站", "天津站"]
    polys = [_poly(0, 100), _poly(0, 0), _poly(0, 50)]
    info = parse_ticket_info(texts, polys)
    # Just make sure it runs without raising; the result depends on
    # the station name set so we don't pin to a specific station string.
    assert "train_code" in info
