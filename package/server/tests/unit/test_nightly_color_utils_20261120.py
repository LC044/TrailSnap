"""Hex colour conversion helpers used by the colour analysis output."""
import pytest

from app.utils.color import _hex_to_rgb, _rgb_to_hex

pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


def test_hex_to_rgb_parses_components():
    assert _hex_to_rgb("#FF8000") == (255, 128, 0)


def test_hex_to_rgb_accepts_lowercase_hex():
    assert _hex_to_rgb("#ff8000") == (255, 128, 0)


def test_rgb_to_hex_pads_single_digit_components():
    assert _rgb_to_hex(1, 2, 3) == "#010203"


def test_rgb_to_hex_uses_uppercase_digits():
    assert _rgb_to_hex(171, 205, 239) == "#ABCDEF"


def test_conversion_round_trips():
    assert _hex_to_rgb(_rgb_to_hex(18, 52, 86)) == (18, 52, 86)
