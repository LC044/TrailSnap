"""Filename timestamp extraction patterns."""
from datetime import datetime

import pytest

from app.utils.filename import _extract_datetime_from_filename

pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


def test_extracts_underscore_separated_datetime():
    assert _extract_datetime_from_filename("IMG_2024_03_05_11_22_33.jpg") == datetime(2024, 3, 5, 11, 22, 33)


def test_extracts_compact_date_and_time():
    assert _extract_datetime_from_filename("20240305_112233.jpg") == datetime(2024, 3, 5, 11, 22, 33)


def test_extracts_dash_separated_date_with_compact_time():
    assert _extract_datetime_from_filename("2024-03-05_112233.jpg") == datetime(2024, 3, 5, 11, 22, 33)


def test_extracts_compact_datetime_without_separator():
    assert _extract_datetime_from_filename("20240305112233.jpg") == datetime(2024, 3, 5, 11, 22, 33)


def test_day_first_filename_keeps_the_current_month_day_order():
    # The implementation feeds "DD-MM-YYYY" to a "%m-%d-%Y" parser, so the two
    # leading components are swapped. This case locks the current behaviour so a
    # future fix has to update it deliberately.
    assert _extract_datetime_from_filename("05-03-2024_112233.jpg") == datetime(2024, 5, 3, 11, 22, 33)


def test_returns_none_when_no_timestamp_is_present():
    assert _extract_datetime_from_filename("holiday-photo.jpg") is None


def test_returns_none_for_out_of_range_values():
    # The implementation swallows parsing errors, so an impossible month yields None.
    assert _extract_datetime_from_filename("2024-13-45_999999.jpg") is None
