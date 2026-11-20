"""Export filename templating and metadata scrubbing."""
import json
from datetime import datetime
from types import SimpleNamespace

import pytest

from app.utils.export_formatter import (
    METADATA_VARS,
    _parse_exif_info,
    _sanitize,
    format_export_filename,
)

pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


def _photo(**kwargs):
    base = {"photo_time": datetime(2024, 3, 5, 7, 8, 9), "upload_time": None}
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_metadata_vars_cover_documented_placeholders():
    assert METADATA_VARS == {"city", "location", "camera", "lens", "iso"}


def test_sanitize_replaces_every_invalid_filename_char():
    assert _sanitize('a/b\\c:d*e?f"g<h>i|j') == "a_b_c_d_e_f_g_h_i_j"


def test_sanitize_coerces_non_string_values():
    assert _sanitize(12) == "12"
    assert _sanitize(None) == "None"


def test_parse_exif_info_returns_empty_for_missing_values():
    assert _parse_exif_info(None) == {}
    assert _parse_exif_info("") == {}
    assert _parse_exif_info({}) == {}


def test_parse_exif_info_keeps_already_decoded_dicts():
    payload = {"Make": "Canon"}
    assert _parse_exif_info(payload) == payload


def test_parse_exif_info_decodes_json_strings():
    assert _parse_exif_info('{"Make": "Canon"}') == {"Make": "Canon"}


def test_parse_exif_info_rejects_invalid_or_non_object_payloads():
    assert _parse_exif_info("not-json") == {}
    assert _parse_exif_info("[1, 2]") == {}
    assert _parse_exif_info(123) == {}


def test_format_export_filename_renders_date_and_sequence_placeholders():
    result = format_export_filename(
        "{year}-{month}-{day}_{sequence3}-{sequence4}", _photo(), 7
    )
    assert result == "2024-03-05_007-0007"


def test_format_export_filename_drops_unknown_placeholders():
    assert format_export_filename("{year}-{nope}", _photo(), 1) == "2024-"


def test_format_export_filename_uses_exif_and_sanitizes_metadata():
    metadata = SimpleNamespace(
        exif_info=json.dumps({"Make": "Canon", "Model": "EOS", "LensModel": "RF50"}),
        make=None,
        model=None,
        city="Bei/Jing",
        address="Shanghai",
    )
    result = format_export_filename("{city}_{camera}_{lens}", _photo(), 1, metadata)
    assert result.startswith("Bei_Jing_Canon EOS_RF50")
    assert "/" not in result


def test_format_export_filename_falls_back_to_upload_time():
    photo = _photo(photo_time=None, upload_time=datetime(2023, 12, 31, 23, 59, 58))
    result = format_export_filename("{year}-{month}-{day} {hour}:{minute}:{time}", photo, 1)
    assert result == "2023-12-31 23:59:235958"


def test_format_export_filename_uses_original_basename():
    result = format_export_filename("{original}", _photo(), 1, original_filename="IMG_9.jpg")
    assert result == "IMG_9"

