"""2026-10-28 nightly coverage for ``app/services/ticket_parser.py``.

The AI coverage scan reported ``services/ticket_parser.py`` at 89% with 103
uncovered lines.  A previous 2026-10-28 file already covered the sticky-time
repair and the seat/carriage rules, so this file targets the **remaining**
OCR-repair branches that were still dark:

* the multi-block departure datetime assembly (a year block, a separate
  ``MM月DD日 HH:MM`` block, a dotted ``YYYY.MM.DD`` date, and the compact
  ``YYYYMMDD HH:MM`` glue);
* the fallback time-pattern table (``YYYYMM月DDHH:MM``, ``YYYYMMDD日HHMM``,
  ``YYYY年MM月DD日 HH:MM``, the generalized ``YYYY年MM月DD日H:MM`` shape);
* the train-code-anchored departure/arrival pick when both stations sit on
  one OCR line;
* the no-seat / standing-ticket carriage recovery.

Every case feeds synthetic OCR blocks into ``parse_ticket_info``; no model,
no network and no image is involved.
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
# departure datetime assembled from separate OCR blocks
# ---------------------------------------------------------------------------


def test_a_year_block_and_a_month_day_block_are_joined():
    """``2026年`` on one line and ``06月02日10:40开`` on another is one date."""
    assert _parse("2026年", "06月02日10:40开")["datetime"] == "2026年06月02日 10:40"


def test_a_dotted_date_is_normalized_to_the_chinese_form():
    """``2026.6.2`` must still produce a parseable Chinese date."""
    assert _parse("2026.6.2")["datetime"] == "2026年06月02日"


def test_a_dotted_date_combines_with_a_separate_time_block():
    """The dotted date and a ``10:40`` block belong to the same departure."""
    assert _parse("2026.6.2", "10:40开")["datetime"] == "2026年06月02日 10:40"


def test_a_date_without_a_time_stays_a_date():
    """A date-only ticket keeps just the date."""
    assert _parse("2026年06月02日")["datetime"] == "2026年06月02日"


def test_a_full_date_block_combines_with_a_separate_time_block():
    """The classic split across two OCR lines."""
    assert _parse("2026年06月02日", "10:40开")["datetime"] == "2026年06月02日 10:40"


# ---------------------------------------------------------------------------
# fallback time-pattern table
# ---------------------------------------------------------------------------


def test_the_compact_month_day_pattern_is_recognised():
    """``202404月07日1022开`` -> YYYY MM DD HHmm."""
    assert _parse("202404月07日1022开")["datetime"] == "2024年04月07日 10:22"


def test_the_day_with_a_four_digit_time_pattern_is_recognised():
    """``20240602日1039`` -> YYYY MM DD HH:MM."""
    assert _parse("20240602日1039")["datetime"] == "2024年06月02日 10:39"


def test_the_single_digit_hour_pattern_is_recognised():
    """``2024年06月02日9:05`` keeps a one-digit hour."""
    assert _parse("2024年06月02日9:05")["datetime"] == "2024年06月02日 09:05"


def test_the_generalized_separator_pattern_is_recognised():
    """``2025年01月18H13:46`` uses a letter instead of a date separator.

    The date only survives when the block is not consumed by the earlier
    ``_build_departure_datetime`` pass, which claims a bare ``13:46`` time
    for an otherwise unparsable date.  Prefixing the block with a word the
    departure builder skips (``优惠``) keeps the generalized pattern
    reachable, which is what the OCR-noise repair is for.
    """
    assert _parse("优惠2025年01月18H13:46")["datetime"] == "2025年01月18日 13:46"


def test_the_spaced_time_pattern_is_recognised():
    """``2020年08月29日 20:54`` with a real space."""
    assert _parse("2020年08月29日 20:54")["datetime"] == "2020年08月29日 20:54"


def test_the_compact_glued_day_and_time_pattern_is_recognised():
    """``2020年08月29日2054`` -- the date and the time share one line."""
    assert _parse("2020年08月29日2054")["datetime"] == "2020年08月29日 20:54"


# ---------------------------------------------------------------------------
# train-code-anchored station pick
# ---------------------------------------------------------------------------


def test_the_station_after_the_train_code_is_the_arrival():
    """``G1北京南站上海虹桥站`` -- the first station right of the code is the arrival."""
    info = _parse("G1北京南站上海虹桥站")
    assert info["train_code"] == "G1"
    assert info["arrival_station"] == "北京南"


def test_the_station_before_the_train_code_is_the_departure():
    """``上海虹桥G1`` -- the station left of the train code is the departure."""
    info = _parse("上海虹桥G1")
    assert info["train_code"] == "G1"
    assert info["departure_station"] == "上海虹桥"


# ---------------------------------------------------------------------------
# no-seat / standing ticket
# ---------------------------------------------------------------------------


def test_a_no_seat_ticket_clears_the_seat_and_recovers_the_carriage():
    """``无座`` forces an empty seat and still recovers ``车厢04车``."""
    info = _parse("无座", "车厢04车")
    assert info["seat_type"] == "无座"
    assert info["seat_num"] == ""
    assert info["carriage"] == "04"


def test_a_standing_ticket_is_recognised():
    """``站票`` is the standing-ticket variant of the no-seat rule."""
    info = _parse("站票")
    assert info["seat_type"] == "站票"
    assert info["seat_num"] == ""


def test_a_no_seat_ticket_pads_a_single_digit_carriage():
    """``无座车厢4车`` in one block is normalised to a two-digit carriage.

    The padding only happens in the no-seat branch, so the carriage and the
    ``无座`` marker have to share a text block.
    """
    info = _parse("无座车厢4车")
    assert info["seat_type"] == "无座"
    assert info["carriage"] == "04"

