"""Nightly watch 2026-11-04: printed pinyin station recovery."""
import pytest

from app.services import ticket_parser

pytestmark = [pytest.mark.smoke]


def test_printed_pinyin_recovers_one_damaged_station_glyph(monkeypatch):
    poly = [[0, 0], [20, 0], [20, 10], [0, 10]]
    printed = [[0, 12], [20, 12], [20, 22], [0, 22]]
    monkeypatch.setattr(
        ticket_parser,
        "_STATION_PINYIN",
        {"北京南": "beijingnan", "北京西": "beijingxi"},
    )

    assert (
        ticket_parser._station_from_printed_pinyin(
            "北亰南", poly, ["BEIJING NAN"], [printed]
        )
        == "北京南"
    )
