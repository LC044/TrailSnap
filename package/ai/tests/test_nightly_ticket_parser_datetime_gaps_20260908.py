"""Nightly gap tests for train-ticket departure datetime geometry (2026-09-08)."""
import pytest

pytestmark = [pytest.mark.smoke]


def _poly(x, y, w=20, h=10):
    return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]


def test_build_departure_datetime_pairs_nearest_date_and_time_with_year():
    from app.services.ticket_parser import _build_departure_datetime

    texts = ["2025年", "01月09日", "17:12", "18:20"]
    polys = [_poly(0, 0), _poly(20, 0), _poly(50, 0), _poly(200, 200)]

    assert _build_departure_datetime(texts, polys) == "2025年01月09日 17:12"


def test_build_departure_datetime_time_only_prefers_leftmost_horizontal_candidate():
    from app.services.ticket_parser import _build_departure_datetime

    texts = ["17:12", "18:20"]
    polys = [_poly(100, 0), _poly(10, 0)]

    assert _build_departure_datetime(texts, polys) == "18:20"


def test_build_departure_datetime_date_only_prefers_topmost_candidate():
    from app.services.ticket_parser import _build_departure_datetime

    texts = ["01月09日", "02月10日"]
    polys = [_poly(0, 100), _poly(0, 10)]

    assert _build_departure_datetime(texts, polys) == "02月10日"
