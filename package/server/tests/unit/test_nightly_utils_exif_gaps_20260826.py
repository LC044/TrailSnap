"""Unit tests for app/utils/exif.py (2026-08-26 round).

Coverage gaps were concentrated in three functions we can drive with plain
inputs:
  * ``_convert_to_degrees`` -- pure helper for the GPS tuple arithmetic
  * ``get_gps_info`` -- shaped EXIF dict -> (lat, lng) or None
  * ``get_file_time_form_system`` -- os.stat wrapper with a fallback

``extract_metadata`` touches PIL + reverse_geocoder, so we exercise it with
a stub image and a stub reverse-geocoder.
"""
import os
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.utils import exif
from app.utils.exif import (
    _convert_to_degrees,
    extract_metadata,
    get_exif_data,
    get_file_time_form_system,
    get_gps_info,
    reverse_geocode,
)


pytestmark = [pytest.mark.smoke]


# -------------------------------------------------------------------------
# _convert_to_degrees
# -------------------------------------------------------------------------


def test_convert_handles_simple_floats():
    assert _convert_to_degrees((30, 0, 0)) == 30.0


def test_convert_handles_dms_tuple():
    # 30 deg 15 min 45 sec = 30 + 15/60 + 45/3600 = 30.2625
    assert _convert_to_degrees((30, 15, 45)) == pytest.approx(30.2625)


def test_convert_handles_fraction_tuples():
    # EXIF stores 30 deg 15 min 45/2 sec
    # 30 + 15/60 + (45/2)/3600 = 30 + 0.25 + 0.00625 = 30.25625
    assert _convert_to_degrees(((30, 1), (15, 1), (45, 2))) == pytest.approx(30.25625)


def test_convert_handles_zero_denominator():
    # Guard against division by zero on malformed EXIF.
    assert _convert_to_degrees(((1, 0), (2, 1), (3, 1))) == pytest.approx(2.0 / 60 + 3.0 / 3600)


def test_convert_handles_ifd_rational_fallback():
    class _Rat:
        def __init__(self, num, den):
            self.numerator = num
            self.denominator = den

    val = (_Rat(30, 1), _Rat(15, 1), _Rat(0, 1))
    assert _convert_to_degrees(val) == pytest.approx(30.25)


# -------------------------------------------------------------------------
# get_gps_info
# -------------------------------------------------------------------------


def test_get_gps_info_returns_none_when_no_gps_section():
    assert get_gps_info({"DateTimeOriginal": "2024:01:01 12:00:00"}) is None


def test_get_gps_info_returns_lat_lng_in_north_east_hemi():
    exif_dict = {
        "GPSInfo": {
            "GPSLatitude": (30, 0, 0),
            "GPSLatitudeRef": "N",
            "GPSLongitude": (120, 0, 0),
            "GPSLongitudeRef": "E",
        }
    }
    assert get_gps_info(exif_dict) == {"latitude": 30.0, "longitude": 120.0}


def test_get_gps_info_negates_for_south_or_west_hemi():
    exif_dict = {
        "GPSInfo": {
            "GPSLatitude": (30, 0, 0),
            "GPSLatitudeRef": "S",
            "GPSLongitude": (120, 0, 0),
            "GPSLongitudeRef": "W",
        }
    }
    result = get_gps_info(exif_dict)
    assert result["latitude"] == -30.0
    assert result["longitude"] == -120.0


def test_get_gps_info_returns_none_when_partial():
    exif_dict = {
        "GPSInfo": {
            "GPSLatitude": (30, 0, 0),
            "GPSLatitudeRef": "N",
        }
    }
    assert get_gps_info(exif_dict) is None


# -------------------------------------------------------------------------
# get_file_time_form_system
# -------------------------------------------------------------------------


def test_get_file_time_returns_stat_mtime(tmp_path):
    p = tmp_path / "f.txt"
    p.write_text("x")
    mtime = os.stat(p).st_mtime
    assert get_file_time_form_system(str(p)) == datetime.fromtimestamp(mtime)


def test_get_file_time_falls_back_to_now_on_missing(tmp_path):
    missing = tmp_path / "does_not_exist"
    with patch("app.utils.exif.datetime") as dt_mod:
        dt_mod.now.return_value = datetime(2024, 1, 2, 3, 4, 5)
        result = get_file_time_form_system(str(missing))
    assert result == datetime(2024, 1, 2, 3, 4, 5)


# -------------------------------------------------------------------------
# get_exif_data
# -------------------------------------------------------------------------


class _FakeExif(dict):
    pass


def test_get_exif_data_returns_empty_when_image_has_no_exif():
    img = SimpleNamespace(
        getexif=MagicMock(return_value=None),
        _getexif=MagicMock(return_value=None),
    )
    assert get_exif_data(img) == {}


def test_get_exif_data_uses_getexif_for_top_level_tags():
    info = {256: 100, 257: 200}
    fake_exif = _FakeExif(info)
    fake_exif.get_ifd = MagicMock(return_value={})
    img = SimpleNamespace(
        getexif=MagicMock(return_value=fake_exif),
        _getexif=MagicMock(return_value=None),
    )
    result = get_exif_data(img)
    assert result["ImageWidth"] == 100
    assert result["ImageLength"] == 200


def test_get_exif_data_decodes_bytes_to_str():
    info = {306: b"2024:01:01 12:00:00"}
    fake_exif = _FakeExif(info)
    fake_exif.get_ifd = MagicMock(return_value={})
    img = SimpleNamespace(
        getexif=MagicMock(return_value=fake_exif),
        _getexif=MagicMock(return_value=None),
    )
    result = get_exif_data(img)
    assert result["DateTime"] == "2024:01:01 12:00:00"


def test_get_exif_data_falls_back_to_legacy_getexif():
    legacy = {256: 1024, 257: 768}
    img = SimpleNamespace(
        getexif=MagicMock(return_value=None),
        _getexif=MagicMock(return_value=legacy),
    )
    result = get_exif_data(img)
    assert result["ImageWidth"] == 1024
    assert result["ImageLength"] == 768


# -------------------------------------------------------------------------
# extract_metadata (uses image_obj to avoid PIL)
# -------------------------------------------------------------------------


def _img_with_exif(width, height, exif_dict, exif_ifd=None):
    """Build a MagicMock image whose getexif() returns a populated EXIF.

    The top-level dict must be non-empty so ``if info:`` is truthy; we add a
    placeholder key 36867 (DateTimeOriginal) and override the value with
    whatever lives in the ExifIFD 0x8769.
    """
    img = MagicMock()
    img.width = width
    img.height = height
    top_level = _FakeExif({36867: b"placeholder"})
    top_level.get_ifd = MagicMock(return_value=exif_ifd or {})
    img.getexif.return_value = top_level
    return img


def test_extract_metadata_uses_exif_datetime_when_present(tmp_path):
    image_path = tmp_path / "x.jpg"
    image_path.write_bytes(b"\x00")
    # DateTimeOriginal (36867) lives in ExifIFD 0x8769.
    img = _img_with_exif(100, 200, {}, exif_ifd={36867: b"2024:05:01 10:00:00"})
    with patch.object(exif, "reverse_geocode", return_value={}):
        result = extract_metadata(
            str(image_path), image_path.name, image_obj=img, extract_location_details=False
        )
    assert result["photo_time"] == datetime(2024, 5, 1, 10, 0, 0)
    assert result["width"] == 100
    assert result["height"] == 200
    assert result["exif_info"] is not None


def test_extract_metadata_falls_back_to_filename_time(tmp_path):
    image_path = tmp_path / "x.jpg"
    image_path.write_bytes(b"\x00")
    img = _img_with_exif(50, 60, {})
    with patch.object(exif, "reverse_geocode", return_value={}), \
         patch.object(exif, "get_file_time_form_system",
                       return_value=datetime(2024, 6, 1, 0, 0, 0)):
        result = extract_metadata(
            str(image_path), "IMG_20240601_120000.jpg",
            image_obj=img, extract_location_details=False,
        )
    assert result["photo_time"] == datetime(2024, 6, 1, 12, 0, 0)


def test_extract_metadata_passes_location_through_when_present(tmp_path):
    image_path = tmp_path / "x.jpg"
    image_path.write_bytes(b"\x00")
    img = _img_with_exif(10, 20, {}, exif_ifd={36867: b"2024:05:01 10:00:00"})
    with patch.object(exif, "reverse_geocode", return_value={"address": "上海"}):
        result = extract_metadata(
            str(image_path), image_path.name,
            image_obj=img, extract_location_details=True,
        )
    assert "photo_time" in result
    assert result["photo_time"] == datetime(2024, 5, 1, 10, 0, 0)


def test_extract_metadata_falls_back_to_now(tmp_path):
    image_path = tmp_path / "x.jpg"
    image_path.write_bytes(b"\x00")
    img = _img_with_exif(1, 1, {})
    with patch.object(exif, "reverse_geocode", return_value={}), \
         patch.object(exif, "get_file_time_form_system", return_value=None), \
         patch("app.utils.exif.datetime") as dt_mod:
        dt_mod.strptime.side_effect = ValueError
        dt_mod.now.return_value = datetime(2030, 1, 1, 0, 0, 0)
        result = extract_metadata(
            str(image_path), "no_time_in_name.jpg", image_obj=img
        )
    assert result["photo_time"] == datetime(2030, 1, 1, 0, 0, 0)


# -------------------------------------------------------------------------
# reverse_geocode (smoke)
# -------------------------------------------------------------------------


def test_reverse_geocode_returns_address_dict():
    fake_row = {
        "admin_1": "上海市",
        "admin_2": "市辖区",
        "admin_3": "黄浦区",
        "admin_4": "",
        "name": "外滩",
        "country": "中国",
    }
    with patch.object(exif.rg, "search", return_value=[fake_row]):
        result = reverse_geocode(31.23, 121.47)
    assert result["province"] == "上海市"
    assert result["city"] == "市辖区"
    assert result["district"] == "黄浦区"
    assert "外滩" in result["address"]


def test_reverse_geocode_returns_empty_on_exception():
    with patch.object(exif.rg, "search", side_effect=RuntimeError("rg broken")):
        assert reverse_geocode(0, 0) == {}
