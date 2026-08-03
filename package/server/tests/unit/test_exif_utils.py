"""Nightly watch gap coverage for app.utils.exif.

Targets the EXIF/GPS/filename metadata helpers (app/utils/exif.py
154/175 lines uncovered in nightly coverage scan). Covers:

* Happy path: get_gps_info returns lat/lng for both hemispheres.
* Edge: missing GPS keys return None; malformed DateTimeOriginal
  is swallowed and the filename fallback runs.
* Error: extract_metadata swallows internal exceptions and still
  returns a well-formed metadata dict.
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest


pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


def test_get_gps_info_returns_lat_lng_for_north_and_east():
    from app.utils.exif import get_gps_info
    exif = {"GPSInfo": {
        "GPSLatitude": (40.0, 0.0, 0.0),
        "GPSLatitudeRef": "N",
        "GPSLongitude": (74.0, 0.0, 0.0),
        "GPSLongitudeRef": "E",
    }}
    assert get_gps_info(exif) == {
        "latitude": pytest.approx(40.0), "longitude": pytest.approx(74.0)}


def test_get_gps_info_flips_sign_for_south_and_west():
    from app.utils.exif import get_gps_info
    exif = {"GPSInfo": {
        "GPSLatitude": (33.0, 0.0, 0.0),
        "GPSLatitudeRef": "S",
        "GPSLongitude": (151.0, 0.0, 0.0),
        "GPSLongitudeRef": "W",
    }}
    result = get_gps_info(exif)
    assert result["latitude"] == pytest.approx(-33.0)
    assert result["longitude"] == pytest.approx(-151.0)


def test_get_gps_info_returns_none_when_keys_missing():
    from app.utils.exif import get_gps_info
    assert get_gps_info({}) is None
    exif_no_lng = {"GPSInfo": {"GPSLatitude": (1.0, 0.0, 0.0), "GPSLatitudeRef": "N"}}
    assert get_gps_info(exif_no_lng) is None
    assert get_gps_info({"GPSInfo": {}}) is None


def test_extract_metadata_falls_back_to_filename_when_exif_invalid():
    from app.utils.exif import extract_metadata
    fake_image = SimpleNamespace(width=100, height=80, close=lambda: None)
    fake_exif = {"DateTimeOriginal": "not-a-valid-date"}
    with patch("app.utils.exif.get_exif_data", return_value=fake_exif), patch("app.utils.exif.get_gps_info", return_value=None), patch("app.utils.exif.extract_datetime_from_filename", return_value=datetime(2024, 6, 1, 12, 0, 0)):
        result = extract_metadata(
            file_path="ignored.jpg",
            filename="trip_20240601_120000.jpg",
            image_obj=fake_image,
            extract_location_details=False,
        )
    assert result["photo_time"] == datetime(2024, 6, 1, 12, 0, 0)
    assert result["width"] == 100
    assert result["height"] == 80
    assert result["exif_info"] is fake_exif
    assert result["location"] is None


def test_extract_metadata_swallows_reverse_geocode_failure():
    from app.utils.exif import extract_metadata
    fake_image = SimpleNamespace(width=10, height=10, close=lambda: None)
    exif_with_gps = {
        "DateTimeOriginal": "2025:01:02 03:04:05",
        "GPSInfo": {"GPSLatitude": (1.0, 0.0, 0.0), "GPSLatitudeRef": "N",
                    "GPSLongitude": (2.0, 0.0, 0.0), "GPSLongitudeRef": "E"},
    }
    with patch("app.utils.exif.get_exif_data", return_value=exif_with_gps), patch("app.utils.exif.reverse_geocode", side_effect=RuntimeError("network down")):
        result = extract_metadata(
            file_path="whatever.jpg",
            filename="whatever.jpg",
            image_obj=fake_image,
            extract_location_details=True,
        )
    assert result["photo_time"] == datetime(2025, 1, 2, 3, 4, 5)
    assert result["location"] == {"latitude": pytest.approx(1.0), "longitude": pytest.approx(2.0)}
    assert "location_details" not in result


def test_extract_metadata_returns_now_when_all_sources_fail():
    from app.utils.exif import extract_metadata
    fake_image = SimpleNamespace(width=1, height=1, close=lambda: None)
    with patch("app.utils.exif.get_exif_data", return_value={}), patch("app.utils.exif.get_gps_info", return_value=None), patch("app.utils.exif.extract_datetime_from_filename", return_value=None), patch("app.utils.exif.get_file_time_form_system", side_effect=OSError("missing")):
        before = datetime.now()
        result = extract_metadata(
            file_path="x.jpg",
            filename="x.jpg",
            image_obj=fake_image,
            extract_location_details=False,
        )
        after = datetime.now()
    assert before <= result["photo_time"] <= after
