"""2026-11-18 nightly coverage for the geo helpers in ``app/utils/geo.py``.

No test file referenced ``app/utils/geo.py``.  The helpers back the
"photos taken nearby" / "which way was the camera pointing" features, so the
distance, the bearing and the Chinese compass label are all worth pinning.

Covered here:

* the great-circle distance between two known cities;
* the zero distance for identical points;
* the bearing on the cardinal axes (north / east / south / west);
* the compass label for every sector, including the wrap-around at 360.
"""

from __future__ import annotations

import math

import pytest

from app.utils.geo import calculate_bearing, calculate_haversine_distance, get_compass_direction


pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


def test_the_distance_between_two_known_cities_is_about_1000_km():
    # Beijing -> Shanghai is roughly 1064 km.
    distance = calculate_haversine_distance(39.9042, 116.4074, 31.2304, 121.4737)

    assert 1000 < distance < 1150


def test_the_distance_between_a_point_and_itself_is_zero():
    assert calculate_haversine_distance(39.9042, 116.4074, 39.9042, 116.4074) == pytest.approx(0.0)


def test_the_distance_is_symmetric():
    a = calculate_haversine_distance(39.9042, 116.4074, 31.2304, 121.4737)
    b = calculate_haversine_distance(31.2304, 121.4737, 39.9042, 116.4074)

    assert a == pytest.approx(b)


def test_the_bearing_to_the_north_is_zero():
    assert calculate_bearing(39.9042, 116.4074, 40.9042, 116.4074) == pytest.approx(0.0, abs=1e-6)


def test_the_bearing_to_the_east_is_ninety():
    assert calculate_bearing(0.0, 0.0, 0.0, 1.0) == pytest.approx(90.0, abs=1e-6)


def test_the_bearing_to_the_south_is_one_hundred_and_eighty():
    assert calculate_bearing(0.0, 0.0, -1.0, 0.0) == pytest.approx(180.0, abs=1e-6)


def test_the_bearing_to_the_west_is_two_hundred_and_seventy():
    assert calculate_bearing(0.0, 0.0, 0.0, -1.0) == pytest.approx(270.0, abs=1e-6)


def test_the_bearing_is_always_normalised_into_the_zero_to_360_range():
    for lat, lon in ((10.0, 20.0), (-30.0, 170.0), (45.0, -179.0)):
        bearing = calculate_bearing(0.0, 0.0, lat, lon)

        assert 0.0 <= bearing < 360.0


@pytest.mark.parametrize(
    ("bearing", "direction"),
    [
        (0.0, "北"),
        (45.0, "东北"),
        (90.0, "东"),
        (135.0, "东南"),
        (180.0, "南"),
        (225.0, "西南"),
        (270.0, "西"),
        (315.0, "西北"),
        (359.9, "北"),
    ],
)
def test_every_sector_maps_to_a_chinese_compass_direction(bearing, direction):
    assert get_compass_direction(bearing) == direction


def test_a_bearing_just_below_north_is_still_north():
    assert get_compass_direction(359.0) == "北"


def test_a_bearing_just_below_east_is_still_east():
    assert get_compass_direction(89.0) == "东"
