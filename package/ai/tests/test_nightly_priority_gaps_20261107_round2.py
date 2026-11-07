"""Second nightly AI priority-gap pass for 2026-11-07.

Fresh coverage still places ticket_parser and ticket_service near the bottom of
the AI scan. These tests guard station-layout extraction, conservative date
parsing, name proximity, and station-line recovery preconditions.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services import ticket_parser, ticket_service


pytestmark = [pytest.mark.smoke, pytest.mark.module_ai]


def _poly():
    return [[0, 0], [100, 0], [100, 20], [0, 20]]


def test_station_candidates_expands_known_route_pair():
    candidates = ticket_parser._station_candidates(["北京南—上海虹桥"], [_poly()])

    assert [item[0] for item in candidates] == ["北京南", "上海虹桥"]
    assert candidates[0][1] == candidates[1][1] == 0
    assert candidates[0][2] < candidates[1][2]


def test_station_candidates_expands_compact_route_with_train_code():
    candidates = ticket_parser._station_candidates(["G123北京南—上海虹桥"], [_poly()])

    assert [item[0] for item in candidates] == ["北京南", "上海虹桥"]


@pytest.mark.parametrize("text", ["6.6折", "￥12.5"])
def test_month_day_rejects_price_and_discount_dot_blocks(text):
    assert ticket_parser._extract_month_day(text) is None


@pytest.mark.parametrize("text", ["13-28", "01/32"])
def test_month_day_rejects_invalid_ranges(text):
    assert ticket_parser._extract_month_day(text) is None


def test_name_proximity_returns_empty_when_anchor_has_no_candidates():
    ocr_texts = ["****8035"]
    station_names = {"北京南", "上海虹桥"}
    ticket_info = {"departure_station": "北京南", "arrival_station": "上海虹桥"}

    assert ticket_parser._select_name_by_proximity(ocr_texts, station_names, ticket_info) == ""


def test_station_line_recovery_requires_one_endpoint_and_train_code():
    info = {"departure_station": "北京南", "arrival_station": ""}
    before = dict(info)

    ticket_service.recover_station_line(
        info, image=SimpleNamespace(shape=(100, 200, 3)), texts=[], polys=[], ocr=MagicMock()
    )

    assert info == before
