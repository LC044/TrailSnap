"""Nightly gap coverage for app/services/ticket_parser.py.

The nightly coverage scan reported several date/time and seat-code branches of
``parse_ticket_info`` as uncovered. These cases pin the documented behaviour of
the parser for the ticket formats that users actually hit.
"""

from __future__ import annotations

import pytest

from app.services.ticket_parser import parse_ticket_info

pytestmark = [pytest.mark.smoke, pytest.mark.module_ticket]


def test_parses_full_date_with_colon_time():
    info = parse_ticket_info(["2020年08月29日20:54开"], [])

    assert info["datetime"] == "2020年08月29日 20:54"


def test_parses_glued_carriage_and_seat_code():
    info = parse_ticket_info(["二等座0206F号"], [])

    assert info["carriage"] == "02"
    assert info["seat_num"] == "06F"


def test_parses_sticky_day_and_time():
    info = parse_ticket_info(["2024年02月26014:08"], [])

    assert info["datetime"].startswith("2024年02月26日")
    assert info["datetime"].endswith("14:08")


def test_empty_text_does_not_raise_and_keeps_expected_shape():
    info = parse_ticket_info([], [])

    assert isinstance(info, dict)
    assert info.get("datetime") in (None, "")
