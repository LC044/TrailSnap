"""Nightly gap coverage (2026-11-12) - app/services/ticket_parser.py.

The 2026-11-12 AI coverage scan reported ``services/ticket_parser.py`` at
94.5% with 59 uncovered lines.  The remaining gaps sit in two places:

* the *fallback* datetime patterns of ``parse_ticket_info``.  The primary
  candidate scan (``YYYY年MM月DD日`` + ``HH:MM``) already handles the common
  shapes, so the fallback table below it only runs for OCR text that the
  primary scan cannot match.  This file pins those fallback shapes:

  - ``1201-1207``  - ``20200929日1234``  (compact ``YYYYMMDD日HHMM``)
  - ``1210-1215``  - ``2024年1245日16:50开`` (``YYYY年MMDD日HH:MM``)
  - ``1217-1229``  - ``202410月05日1650开`` (``YYYYMM月DD日HHMM``)
  - ``1231-1237``  - ``2025年01月18H13:46`` (separator between day and time)

* the *price* fallbacks.  ``1437-1484`` first tries the price inside a single
  block, then joins price fragments across blocks and only then accepts a
  bare numeric fragment.  This file pins:

  - ``1462``  - the fragment join stops at the first non-price block
  - ``1476-1482`` - a bare ``5.元`` block is accepted as the fare
  - ``1516-1517`` - the low-evidence passenger-name rule
  - ``1557`` - a name that equals the station name is dropped

Every case feeds a synthetic OCR block list into ``parse_ticket_info``; no
model, no network and no image is involved.
"""

from __future__ import annotations

import pytest

from app.services.ticket_parser import parse_ticket_info

pytestmark = [pytest.mark.smoke, pytest.mark.module_ticket]


# --------------------------------------------------------------------------- #
# Fallback datetime shapes
# --------------------------------------------------------------------------- #

def test_compact_yyyymmdd_with_day_and_hhmm_is_parsed():
    """``20200929日1234`` -> the compact ``YYYYMMDD日HHMM`` fallback."""
    info = parse_ticket_info(["20200929日1234"], [])

    assert info["datetime"] == "2020年09月29日 12:34"


def test_year_with_two_digit_month_day_and_colon_time_is_parsed():
    """``2024年1245日16:50开`` -> the ``YYYY年MMDD日HH:MM`` fallback."""
    info = parse_ticket_info(["2024年1245日16:50开"], [])

    assert info["datetime"] == "2024年12月45日 16:50"


def test_numeric_year_month_day_with_compact_time_is_parsed():
    """``202410月05日1650开`` -> the ``YYYYMM月DD日HHMM`` fallback."""
    info = parse_ticket_info(["202410月05日1650开"], [])

    assert info["datetime"] == "2024年10月05日 16:50"


def test_separator_between_day_and_time_is_tolerated():
    """``2025年01月18H13:46`` -> a non-digit separator may sit before the time."""
    info = parse_ticket_info(["2025年01月18H13:46"], [])

    assert info["datetime"] == "2025年01月18日 13:46"


# --------------------------------------------------------------------------- #
# Price fallbacks
# --------------------------------------------------------------------------- #

def test_price_fragment_join_stops_at_the_first_non_price_block():
    """A ``￥`` block followed by a text block must not be joined into a fare."""
    info = parse_ticket_info(["￥", "开票"], [])

    assert info["price"] == ""


def test_bare_numeric_price_block_is_accepted():
    """``5.元`` is a valid fare fragment and yields ``5``."""
    info = parse_ticket_info(["5.元"], [])

    assert info["price"] == "5"


# --------------------------------------------------------------------------- #
# Passenger name fallbacks
# --------------------------------------------------------------------------- #

def test_long_digit_prefix_before_a_name_is_used_as_the_name():
    """``123456789012345X张三`` -> the low-evidence name rule still applies."""
    info = parse_ticket_info(["123456789012345X张三"], [])

    assert info["name"] == "张三"


def test_name_equal_to_the_station_name_is_dropped():
    """A name that merely repeats the station name is not a passenger name."""
    info = parse_ticket_info(["北京南站 123456789012345X北京南"], [])

    assert info["name"] == ""
    assert info["departure_station"] == "北京南"
