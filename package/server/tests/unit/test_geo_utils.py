"""Tests for geographic distance, bearing, and compass helpers."""
import pytest
from app.utils.geo import calculate_bearing, calculate_haversine_distance, get_compass_direction

pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]

def test_haversine_distance_is_zero_for_same_point():
    assert calculate_haversine_distance(39.9, 116.4, 39.9, 116.4) == 0

def test_haversine_distance_and_bearing_for_due_east():
    assert calculate_haversine_distance(0, 0, 0, 1) == pytest.approx(111.195, rel=1e-3)
    assert calculate_bearing(0, 0, 0, 1) == pytest.approx(90)

def test_compass_direction_covers_wraparound_boundaries():
    assert get_compass_direction(0) == "北"
    assert get_compass_direction(90) == "东"
    assert get_compass_direction(359) == "北"
