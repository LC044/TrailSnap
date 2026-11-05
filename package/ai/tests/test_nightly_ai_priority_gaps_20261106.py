"""Nightly coverage guards for 2026-11-06 AI priority gaps."""

import pytest

from app.services.ticket_journey_parser import _center, extract_journey_time
from app.services.ticket_parser import _pick_dep_arr_from_station_candidates
from app.services.ticket_service import recover_clock_orientation

pytestmark = pytest.mark.smoke


def _poly(x=0, y=0):
    return [[x, y], [x + 10, y], [x + 10, y + 10], [x, y + 10]]


def test_center_rejects_insufficient_geometry():
    """OCR polygons with fewer than four points cannot yield a center."""
    assert _center(None) is None
    assert _center([[0, 0], [10, 10]]) is None


def test_oversized_minute_only_duration_is_ignored():
    """A duration over seven days is not plausible and must not be imported."""
    assert extract_journey_time(["10000分钟"], [_poly()], {"train_code": "G123"}) == {}


def test_station_pair_rejects_empty_or_interface_only_names():
    """Non-station labels must never become train endpoints."""
    candidates = [("", 10, 10), ("时刻表", 20, 10)]
    assert _pick_dep_arr_from_station_candidates(candidates) == ("", "")


def test_clock_orientation_recovery_survives_ocr_failure():
    """OCR failure must retain the original card values and not raise."""
    info = {"train_code": "G123", "datetime": "25:99"}

    def failing_ocr(*args, **kwargs):
        raise RuntimeError("ocr unavailable")

    recover_clock_orientation(info, "unused.png", ["25:99"], failing_ocr)

    assert info == {"train_code": "G123", "datetime": "25:99"}


