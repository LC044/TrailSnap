"""Nightly coverage for the text helpers of ``app/services/ticket_parser.py``.

The 2026-10-26 AI coverage scan listed ``services/ticket_parser.py`` at 88.8%
with 103 missed lines.  The missed lines are the small, pure helpers that sit
between the raw OCR output and the parsed ticket:

* ``normalize_ticket_text`` unifies traditional characters and repairs the
  glued date/time and train-code blocks that OCR produces.
* ``_extract_month_day`` must not read a price or a discount as a date.
* ``_is_price_fragment`` / ``_is_discount_block`` decide which blocks may be
  glued into a ticket price.
* ``_split_carriage_seat_if_glued`` splits ``0812A`` into carriage and seat.

None of these need an OCR engine or a database, so they are driven directly.
"""

from __future__ import annotations

import json

import pytest

pytestmark = [pytest.mark.smoke]


# ---------------------------------------------------------------------------
# extract_text
# ---------------------------------------------------------------------------


def test_extract_text_keeps_only_non_empty_blocks(tmp_path):
    from app.services import ticket_parser

    payload = {"rec_texts": ["  G1  ", "", "北京南"], "rec_polys": [[0, 0], [1, 1], [2, 2]]}
    path = tmp_path / "ocr.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    texts, polys = ticket_parser.extract_text(str(path))
    assert texts == ["G1", "北京南"]
    assert polys == [[0, 0], [2, 2]]


def test_extract_text_survives_a_broken_file(tmp_path, capsys):
    from app.services import ticket_parser

    texts, polys = ticket_parser.extract_text(str(tmp_path / "missing.json"))
    assert texts == [] and polys == []
    assert "读取JSON文件失败" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# normalize_ticket_text / candidate_train_codes
# ---------------------------------------------------------------------------


def test_normalize_ticket_text_converts_traditional_characters():
    from app.services import ticket_parser

    assert ticket_parser.normalize_ticket_text(" 車號 G1234 ") == "车号 G1234"


def test_normalize_ticket_text_separates_a_glued_date_and_time():
    from app.services import ticket_parser

    assert ticket_parser.normalize_ticket_text("10-2612:30") == "10-26 12:30"


def test_normalize_ticket_text_repairs_a_lowercase_train_code():
    from app.services import ticket_parser

    assert ticket_parser.normalize_ticket_text("g1234") == "G1234"


def test_candidate_train_codes_prefers_a_modern_code():
    from app.services import ticket_parser

    assert ticket_parser.candidate_train_codes(["G1234", "N5次"]) == {"G1234"}


def test_candidate_train_codes_falls_back_to_a_legacy_code():
    from app.services import ticket_parser

    assert ticket_parser.candidate_train_codes(["K7次"]) == {"K7"}


def test_fix_ocr_text_repairs_confusable_characters():
    from app.services import ticket_parser

    assert ticket_parser._fix_ocr_text("IOl") == "101"
    assert ticket_parser._fix_ocr_text("lo") == "10"


# ---------------------------------------------------------------------------
# carriage / seat
# ---------------------------------------------------------------------------


def test_split_carriage_seat_if_glued_splits_the_seat_number():
    from app.services import ticket_parser

    info = {"carriage": "", "seat_num": "0812A"}
    ticket_parser._split_carriage_seat_if_glued(info)
    assert info == {"carriage": "08", "seat_num": "12A"}


def test_split_carriage_seat_if_glued_keeps_an_existing_carriage():
    from app.services import ticket_parser

    info = {"carriage": "05", "seat_num": "12A"}
    ticket_parser._split_carriage_seat_if_glued(info)
    assert info == {"carriage": "05", "seat_num": "12A"}


def test_split_carriage_seat_if_glued_ignores_a_plain_seat():
    from app.services import ticket_parser

    info = {"carriage": "", "seat_num": "12A"}
    ticket_parser._split_carriage_seat_if_glued(info)
    assert info == {"carriage": "", "seat_num": "12A"}


# ---------------------------------------------------------------------------
# identity / name confidence
# ---------------------------------------------------------------------------


def test_is_id_like_text_detects_a_masked_id():
    from app.services import ticket_parser

    assert ticket_parser._is_id_like_text("****8035") is True


def test_is_id_like_text_detects_a_long_digit_block():
    from app.services import ticket_parser

    assert ticket_parser._is_id_like_text("123456") is True
    assert ticket_parser._is_id_like_text("12345") is False
    assert ticket_parser._is_id_like_text("") is False


def test_is_low_confidence_name_rejects_a_station_name():
    from app.services import ticket_parser

    assert ticket_parser._is_low_confidence_name("北京南", {"北京南"}) is True
    assert ticket_parser._is_low_confidence_name("北京南站", set()) is True
    assert ticket_parser._is_low_confidence_name("", set()) is True


def test_is_low_confidence_name_accepts_a_plain_name():
    from app.services import ticket_parser

    assert ticket_parser._is_low_confidence_name("张三", {"北京南"}) is False


def test_extract_tail_name_from_masked_id_block():
    from app.services import ticket_parser

    assert ticket_parser._extract_tail_name_from_masked_id_block("****8035张三") == "张三"
    assert ticket_parser._extract_tail_name_from_masked_id_block("****8035北京南站") == ""
    assert ticket_parser._extract_tail_name_from_masked_id_block("张三") == ""


# ---------------------------------------------------------------------------
# seat type / price blocks
# ---------------------------------------------------------------------------


def test_extract_seat_type_keyword_finds_the_longest_match():
    from app.services import ticket_parser

    assert ticket_parser._extract_seat_type_keyword("新空调硬座") == "新空调硬座"
    assert ticket_parser._extract_seat_type_keyword("二等座") == "二等座"
    assert ticket_parser._extract_seat_type_keyword("无座位") == "无座"
    assert ticket_parser._extract_seat_type_keyword("") == ""


def test_is_discount_block_detects_a_discount():
    from app.services import ticket_parser

    assert ticket_parser._is_discount_block("6.6折") is True
    assert ticket_parser._is_discount_block("7折") is True
    assert ticket_parser._is_discount_block("￥553.5") is False


def test_is_price_fragment_accepts_prices_only():
    from app.services import ticket_parser

    assert ticket_parser._is_price_fragment("￥553.5") is True
    assert ticket_parser._is_price_fragment("553.5元") is True
    assert ticket_parser._is_price_fragment("6.6折") is False
    assert ticket_parser._is_price_fragment("") is False


# ---------------------------------------------------------------------------
# date / time extraction
# ---------------------------------------------------------------------------


def test_extract_month_day_reads_a_dotted_date():
    from app.services import ticket_parser

    assert ticket_parser._extract_month_day("2026.04.02") == ("04", "02")


def test_extract_month_day_ignores_a_discount_block():
    from app.services import ticket_parser

    assert ticket_parser._extract_month_day("6.6折") is None
    assert ticket_parser._extract_month_day("￥12.5") is None


def test_extract_month_day_reads_a_chinese_date():
    from app.services import ticket_parser

    assert ticket_parser._extract_month_day("1月9日（周五）") == ("01", "09")


def test_extract_month_day_reads_a_dashed_date():
    from app.services import ticket_parser

    assert ticket_parser._extract_month_day("01-28周二") == ("01", "28")
    assert ticket_parser._extract_month_day("13-28") is None


def test_extract_hhmm_reads_both_separators():
    from app.services import ticket_parser

    assert ticket_parser._extract_hhmm("17:12") == "17:12"
    assert ticket_parser._extract_hhmm("18：18") == "18:18"
    assert ticket_parser._extract_hhmm("没有时间") == ""


def test_extract_hhmm_pads_a_single_digit_hour():
    from app.services import ticket_parser

    assert ticket_parser._extract_hhmm("9:05") == "09:05"

