"""Nightly watch coverage for AI ticket-parser helper boundaries."""

import pytest

from app.services import ticket_parser


pytestmark = [pytest.mark.smoke]


def test_glued_carriage_and_seat_are_split():
    ticket = {"seat_num": "0708A", "carriage": None}

    ticket_parser._split_carriage_seat_if_glued(ticket)

    assert ticket == {"carriage": "07", "seat_num": "08A"}


def test_glued_seat_parser_preserves_explicit_carriage():
    ticket = {"seat_num": "0708A", "carriage": "12"}

    ticket_parser._split_carriage_seat_if_glued(ticket)

    assert ticket == {"carriage": "12", "seat_num": "0708A"}


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2026.04.02", ("04", "02")),
        ("6.6折", None),
        ("￥12.5", None),
        ("01-28周二", ("01", "28")),
    ],
)
def test_month_day_parser_accepts_dates_and_rejects_price_fragments(text, expected):
    assert ticket_parser._extract_month_day(text) == expected
