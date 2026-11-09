"""Nightly watch 2026-11-09 (round 2): AI ticket parser text gaps.

Targets uncovered branches in ``app/services/ticket_parser.py`` reported by the
2026-11-09 AI coverage snapshot:

* the date/time blocks that are recognised from a single OCR chunk
  (``20240407日1022``, ``202404月07日1022开``) and the sticky date-time form
  (``2024年02月26014:08``),
* the price-fragment fallbacks: a bare currency symbol followed by the amount,
  and a conservative decimal block that only counts when it carries a
  currency marker,
* the passenger-name fallback for the ``5678 张三`` pattern,
* the guard that clears a passenger name which is really a station name.

Every test exercises already-implemented behaviour; no production code changes.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.smoke]


def _parse(texts):
    from app.services import ticket_parser

    return ticket_parser.parse_ticket_info(texts, [[[0, 0], [1, 1], [2, 2]] for _ in texts])


def test_datetime_is_parsed_from_a_day_block_with_trailing_time():
    info = _parse(["20240407日1022"])
    assert info["datetime"] == "2024年04月07日 10:22"


def test_datetime_is_parsed_from_a_month_block_with_four_digit_time():
    info = _parse(["202404月07日1022开"])
    assert info["datetime"] == "2024年04月07日 10:22"


def test_datetime_is_parsed_from_the_sticky_date_time_block():
    info = _parse(["2024年02月26014:08"])
    assert info["datetime"] == "2024年02月26日 14:08"


def test_price_fragment_blocks_are_combined_into_a_single_price():
    info = _parse(["￥", "443.5"])
    assert info["price"] == "443.5"


def test_conservative_decimal_price_block_is_accepted():
    info = _parse(["￥88.5"])
    assert info["price"] == "88.5"


def test_passenger_name_falls_back_to_the_digits_plus_name_pattern():
    info = _parse(["5678 张三"])
    assert info["name"] == "张三"


def test_name_equal_to_a_station_name_is_cleared():
    info = _parse(["北京南", "5678 北京南"])
    assert info["name"] == ""
