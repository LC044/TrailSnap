"""2026-10-28 nightly coverage for ``app/services/ticket_parser.py``.

The 2026-10-28 AI coverage scan reported ``services/ticket_parser.py`` at
90.4% with 103 uncovered lines.  The uncovered code is the OCR-noise repair
of the departure datetime and of the carriage / seat number:

* the sticky-time recovery (``2024年02月26014:08``) with its invalid-hour
  guard, and the compact ``YYYY年MM月DDHHMM`` shape;
* the seat / carriage repair rules (``03车03A号``, a lone ``03车``, a lone
  ``12C号`` and the glued ``二等座0206F号``);
* the low-evidence passenger-name rules.

Every case feeds a synthetic OCR block list into ``parse_ticket_info``; no
model, no network and no image is involved.
"""

from __future__ import annotations

import pytest


pytestmark = [pytest.mark.smoke]


def _poly(x, y, w=20, h=10):
    return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]


def _parse(*texts):
    from app.services.ticket_parser import parse_ticket_info

    polys = [_poly(0, index * 50) for index in range(len(texts))]
    return parse_ticket_info(list(texts), polys)


# ---------------------------------------------------------------------------
# datetime repair
# ---------------------------------------------------------------------------


def test_sticky_time_with_four_digits_is_split_into_day_and_hour():
    """``2024年02月26014:08`` hides the day boundary inside the time."""
    assert _parse("2024年02月26014:08")["datetime"] == "2024年02月26日 14:08"


def test_sticky_time_with_six_digits_is_split_into_day_and_hour():
    assert _parse("2024年02月261408:08")["datetime"] == "2024年02月26日 14:08"


def test_sticky_time_with_an_impossible_hour_is_rejected():
    """``26994`` would mean hour 94 -- the parser must not invent a time."""
    assert not _parse("2024年02月26994:08")["datetime"]


def test_compact_day_and_time_without_a_separator_is_recognised():
    """``2020年08月29日2054`` is a date and a time glued together."""
    assert _parse("2020年08月29日2054")["datetime"] == "2020年08月29日 20:54"


# ---------------------------------------------------------------------------
# carriage / seat repair
# ---------------------------------------------------------------------------


def test_explicit_carriage_and_seat_are_split():
    info = _parse("03车03A号")
    assert info["carriage"] == "03"
    assert info["seat_num"] == "03A"


def test_a_lone_carriage_number_is_kept():
    assert _parse("03车")["carriage"] == "03"


def test_a_lone_seat_number_is_kept():
    assert _parse("12C号")["seat_num"] == "12C"


def test_a_glued_seat_keeps_its_seat_type():
    """``二等座0206F号`` still reports the seat type of the carriage."""
    info = _parse("二等座0206F号")
    assert info["seat_type"] == "二等座"
    assert info["carriage"] == "02"
    assert info["seat_num"] == "06F"


# ---------------------------------------------------------------------------
# passenger name
# ---------------------------------------------------------------------------


def test_a_name_after_a_masked_id_is_kept():
    """A long masked id followed by a name is a passenger name."""
    assert _parse("110101199001011234张三")["name"] == "张三"


def test_a_name_that_equals_a_station_is_dropped():
    """The station name must never be reported as the passenger name."""
    info = _parse("上海虹桥", "上海虹桥")
    assert info.get("name") in (None, "")
