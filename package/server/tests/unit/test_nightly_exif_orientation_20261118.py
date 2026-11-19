"""Nightly 2026-11-18: app/utils/exif.py 与 image_orientation.py 盲区。"""
import math

import pytest

from app.utils.exif import valid_gps_location
from app.utils.image_orientation import display_image_size

pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


class _FakeImage:
    """display_image_size 只依赖 size 与 getexif()，用最小桩隔离 PIL 细节。"""

    def __init__(self, size, orientation=None):
        self.size = size
        self._orientation = orientation

    def getexif(self):
        exif = {}
        if self._orientation is not None:
            exif[274] = self._orientation
        return exif


def test_valid_gps_location_returns_none_for_empty():
    assert valid_gps_location(None) is None
    assert valid_gps_location({}) is None


def test_valid_gps_location_accepts_normal_pair():
    gps = {"latitude": 31.2304, "longitude": 121.4737}
    assert valid_gps_location(gps) == gps


def test_valid_gps_location_rejects_missing_keys():
    assert valid_gps_location({"latitude": 31.0}) is None
    assert valid_gps_location({"longitude": 121.0}) is None


def test_valid_gps_location_rejects_non_numeric():
    assert valid_gps_location({"latitude": "abc", "longitude": "121"}) is None
    assert valid_gps_location({"latitude": None, "longitude": None}) is None


def test_valid_gps_location_rejects_out_of_range():
    assert valid_gps_location({"latitude": 91.0, "longitude": 121.0}) is None
    assert valid_gps_location({"latitude": 31.0, "longitude": 181.0}) is None
    # 边界值合法
    assert valid_gps_location({"latitude": 90.0, "longitude": 180.0}) is not None


def test_valid_gps_location_rejects_non_finite():
    assert valid_gps_location({"latitude": math.inf, "longitude": 0.0}) is None
    assert valid_gps_location({"latitude": 0.0, "longitude": math.nan}) is None


def test_display_image_size_without_orientation():
    assert display_image_size(_FakeImage((120, 80))) == (120, 80)
    assert display_image_size(_FakeImage((120, 80), orientation=1)) == (120, 80)


def test_display_image_size_swaps_for_rotated_orientation():
    for orientation in (5, 6, 7, 8):
        assert display_image_size(_FakeImage((120, 80), orientation=orientation)) == (80, 120)
