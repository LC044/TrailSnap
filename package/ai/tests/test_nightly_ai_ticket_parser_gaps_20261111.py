"""Nightly gap coverage (2026-11-11) — app/services/ticket_parser.py.

The 2026-11-11 AI coverage scan reported ``ticket_parser.py`` at 93.9% with
66 uncovered lines.  This file pins the branches of ``parse_ticket_info``
that are still reachable:

* 1070-1071 — a train code that is not known yet is picked up from the text
  block and remembered together with its position inside that block.
* 1093 — the departure station is the last station printed *before* the train
  code, the arrival station is the first one printed *after* it.
* 1449 — a price block that only carries a points value ("价值...") must not
  be mistaken for the ticket price.

The two ``except: pass`` blocks around the dot-form date parsing were removed
as part of this nightly run: the matched groups are always digit strings, so
``int()`` can never raise there.

All ticket fixtures are synthetic; no real passenger data is used.
"""

from __future__ import annotations

import pytest

from app.services.ticket_parser import parse_ticket_info

pytestmark = [pytest.mark.smoke, pytest.mark.module_ticket]


# --------------------------------------------------------------------------- #
# Train code + stations inside a single text block
# --------------------------------------------------------------------------- #

def test_train_code_and_stations_are_read_from_one_text_block():
    """``北京南站 G1234 上海虹桥站`` -> train code plus both stations."""
    info = parse_ticket_info(["北京南站 G1234 上海虹桥站"], [])

    assert info["train_code"] == "G1234"
    assert info["departure_station"] == "北京南"
    assert info["arrival_station"] == "上海虹桥"


def test_departure_station_is_the_last_station_before_the_train_code():
    """Several stations before the train code: the closest one wins."""
    info = parse_ticket_info(["北京南站 石家庄站 G1234 上海虹桥站"], [])

    assert info["departure_station"] == "石家庄"
    assert info["arrival_station"] == "上海虹桥"


def test_train_code_is_not_invented_without_any_candidate():
    """Text without a train code leaves the field empty."""
    info = parse_ticket_info(["北京南站 上海虹桥站"], [])

    assert info["train_code"] == ""


# --------------------------------------------------------------------------- #
# Price blocks that are not prices
# --------------------------------------------------------------------------- #

def test_points_value_block_is_not_used_as_the_ticket_price():
    """A "价值" block is a points amount, not the fare."""
    info = parse_ticket_info(["价值100元"], [])

    assert info["price"] == ""


def test_real_price_is_still_parsed_after_a_points_block():
    """A points block must not stop the real fare from being parsed."""
    info = parse_ticket_info(["价值100元", "￥553.0元"], [])

    assert info["price"] == "553.0"
