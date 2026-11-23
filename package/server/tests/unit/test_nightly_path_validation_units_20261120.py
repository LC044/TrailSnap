"""UTF-16 code-unit accounting behind the Windows path guards."""
import pytest

from app.utils.path_validation import _utf16_units

pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


def test_ascii_name_costs_one_unit_per_character():
    assert _utf16_units("abc.jpg") == 7


def test_cjk_character_costs_a_single_unit():
    assert _utf16_units("中文") == 2


def test_emoji_outside_the_bmp_costs_two_units():
    # U+1F600 is stored as a surrogate pair, which is what NTFS counts.
    assert _utf16_units("\U0001F600") == 2


def test_mixed_name_adds_both_contributions():
    assert _utf16_units("a\U0001F600中") == 4


def test_empty_name_has_no_units():
    assert _utf16_units("") == 0
