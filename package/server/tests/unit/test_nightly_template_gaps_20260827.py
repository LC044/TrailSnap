"""Unit tests covering 2026-08-27 nightly coverage gap scan.

Targets uncovered branches in app.utils.template (64.8 percent covered,
50 of 142 lines missed). The existing test_template_utils.py covers the
happy path of render(); this file complements it by exercising every
remaining branch.
"""
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.utils.template import (
    RenderResult,
    TemplateError,
    _format_date,
    _resolve_album,
    _resolve_camera_field,
    _resolve_index,
    _resolve_location_chain,
    _resolve_location_field,
    _resolve_original,
    _resolve_tag,
    build_extension,
    collect_tokens,
    render,
    validate_template,
)


pytestmark = [pytest.mark.smoke, pytest.mark.module_template]


def _make_photo(**kwargs):
    base = dict(
        filename="photo.jpg",
        photo_time=None,
        upload_time=None,
        file_path=None,
        metadata_info=None,
        tags=None,
        albums=None,
        file_type="image",
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def _make_metadata(country=None, province=None, city=None, district=None):
    return SimpleNamespace(country=country, province=province, city=city, district=district)


# _format_date default format (43), mtime fallback (46-50), strftime exception (55-56)

def test_format_date_unknown_when_no_moment_and_no_file():
    photo = _make_photo(photo_time=None, upload_time=None, file_path=None)
    assert _format_date(photo, {}, "%Y%m%d") == "unknown"


def test_format_date_falls_back_to_file_mtime(tmp_path):
    p = tmp_path / "photo.jpg"
    p.write_bytes(b"x")
    photo = _make_photo(photo_time=None, upload_time=None, file_path=str(p))
    result = _format_date(photo, {}, "%Y%m%d")
    assert isinstance(result, str)
    assert len(result) == 8
    assert result.isdigit()


def test_format_date_handles_missing_file_for_mtime():
    photo = _make_photo(photo_time=None, upload_time=None, file_path="Z:/missing/path.jpg")
    assert _format_date(photo, {}, "%Y%m%d") == "unknown"


def test_format_date_strftime_exception_falls_back_to_default_fmt():
    photo = _make_photo()
    photo.photo_time = SimpleNamespace(
        strftime=lambda fmt: "fallback" if fmt == "%Y%m%d" else (_ for _ in ()).throw(ValueError("bad"))
    )
    assert _format_date(photo, {}, "%Y%m%d") == "fallback"


# _resolve_index zfill (62)

def test_resolve_index_zfills_when_digits_positive():
    photo = _make_photo()
    assert _resolve_index(photo, {"index": 7}, digits=3) == "007"
    assert _resolve_index(photo, {"index": 42}, digits=5) == "00042"


def test_resolve_index_uses_raw_when_no_digits():
    photo = _make_photo()
    assert _resolve_index(photo, {"index": 12}, digits=0) == "12"


# _resolve_original branches (67-69)

def test_resolve_original_strips_extension():
    photo = _make_photo(filename="beach.jpg")
    assert _resolve_original(photo, {}) == "beach"


def test_resolve_original_returns_photo_when_filename_empty():
    photo = _make_photo(filename="")
    assert _resolve_original(photo, {}) == "photo"


def test_resolve_original_no_extension():
    photo = _make_photo(filename="raw_no_ext")
    assert _resolve_original(photo, {}) == "raw_no_ext"


# _resolve_location_chain depths 1-4 (73-85)

def test_location_chain_empty_when_no_metadata():
    photo = _make_photo(metadata_info=None)
    assert _resolve_location_chain(photo, {}, depth=3) == ""


def test_location_chain_depth_1_country_only():
    photo = _make_photo(metadata_info=_make_metadata(country="CN"))
    assert _resolve_location_chain(photo, {}, depth=1) == "CN"


def test_location_chain_depth_2_country_province():
    photo = _make_photo(metadata_info=_make_metadata(country="CN", province="BJ"))
    assert _resolve_location_chain(photo, {}, depth=2) == "CN-BJ"


def test_location_chain_depth_3_full():
    photo = _make_photo(metadata_info=_make_metadata(country="CN", province="BJ", city="Beijing"))
    assert _resolve_location_chain(photo, {}, depth=3) == "CN-BJ-Beijing"


def test_location_chain_depth_4_with_district():
    photo = _make_photo(metadata_info=_make_metadata(
        country="CN", province="BJ", city="Beijing", district="Haidian"
    ))
    assert _resolve_location_chain(photo, {}, depth=4) == "CN-BJ-Beijing-Haidian"


def test_location_chain_skips_empty_intermediate_parts():
    photo = _make_photo(metadata_info=_make_metadata(country="CN", province=None, city="Beijing"))
    assert _resolve_location_chain(photo, {}, depth=4) == "CN-Beijing"


# _resolve_camera_field (89-92)

def test_camera_field_empty_when_no_metadata():
    photo = _make_photo(metadata_info=None)
    assert _resolve_camera_field(photo, {}, "make") == ""


def test_camera_field_returns_string_of_attribute():
    photo = _make_photo(metadata_info=SimpleNamespace(make="Canon", model="EOS R5"))
    assert _resolve_camera_field(photo, {}, "make") == "Canon"
    assert _resolve_camera_field(photo, {}, "model") == "EOS R5"


def test_camera_field_handles_missing_attribute():
    photo = _make_photo(metadata_info=SimpleNamespace(make="Canon"))
    assert _resolve_camera_field(photo, {}, "model") == ""


# _resolve_tag (96-106)

def test_resolve_tag_empty_when_no_tags():
    photo = _make_photo(tags=None)
    assert _resolve_tag(photo, {}) == ""
    photo = _make_photo(tags=[])
    assert _resolve_tag(photo, {}) == ""


def test_resolve_tag_returns_first_when_no_confidence():
    tag_a = SimpleNamespace(tag_name="alpha", confidence=None)
    tag_b = SimpleNamespace(tag_name="beta", confidence=None)
    photo = _make_photo(tags=[tag_a, tag_b])
    assert _resolve_tag(photo, {}) == "alpha"


def test_resolve_tag_picks_highest_confidence():
    tag_a = SimpleNamespace(tag_name="low", confidence=10)
    tag_b = SimpleNamespace(tag_name="high", confidence=90)
    tag_c = SimpleNamespace(tag_name="mid", confidence=50)
    photo = _make_photo(tags=[tag_a, tag_b, tag_c])
    assert _resolve_tag(photo, {}) == "high"


def test_resolve_tag_treats_missing_confidence_as_zero():
    tag_a = SimpleNamespace(tag_name="scored", confidence=20)
    tag_b = SimpleNamespace(tag_name="missing", confidence=None)
    photo = _make_photo(tags=[tag_a, tag_b])
    assert _resolve_tag(photo, {}) == "scored"


# _resolve_album (110-114)

def test_resolve_album_empty_when_no_albums():
    photo = _make_photo(albums=None)
    assert _resolve_album(photo, {}) == ""
    photo = _make_photo(albums=[])
    assert _resolve_album(photo, {}) == ""


def test_resolve_album_returns_first_album_name():
    album_a = SimpleNamespace(name="Travel 2025")
    album_b = SimpleNamespace(name="Family")
    photo = _make_photo(albums=[album_a, album_b])
    assert _resolve_album(photo, {}) == "Travel 2025"


def test_resolve_album_returns_empty_when_first_name_is_blank():
    # The helper returns albums[0].name with a trailing ``or ""`` guard, so
    # an empty string on the first album returns "" rather than skipping to
    # the next album. This pins down the current (intentional) behavior.
    album_a = SimpleNamespace(name="")
    album_b = SimpleNamespace(name="Trips")
    photo = _make_photo(albums=[album_a, album_b])
    assert _resolve_album(photo, {}) == ""


# RenderResult.to_dict (168)

def test_render_result_to_dict_basic():
    rr = RenderResult("output-name")
    assert rr.to_dict() == {"name": "output-name", "errors": []}


def test_render_result_to_dict_preserves_errors():
    rr = RenderResult("name", errors=["unknown:foo", "sequence:bad"])
    d = rr.to_dict()
    assert d["name"] == "name"
    assert d["errors"] == ["unknown:foo", "sequence:bad"]
    d["errors"].append("mutated")
    assert rr.errors == ["unknown:foo", "sequence:bad"]


# render() unknown-token error reporting (224-225)

def test_validate_template_rejects_unknown_variable():
    with pytest.raises(TemplateError) as exc:
        validate_template("{date}_{bogus_var}_{original}")
    assert "bogus_var" in str(exc.value)


def test_render_collects_errors_for_unknown_via_patched_validate():
    photo = _make_photo(photo_time=None, upload_time=None, file_path=None)
    with patch("app.utils.template.validate_template", return_value=[]):
        result = render("{date}_{ghost}", photo, index=1, date_format="%Y%m%d")
    assert any(e.startswith("unknown:") for e in result.errors)


# build_extension (269, 277)

def test_build_extension_uses_filename_extension():
    photo = _make_photo(filename="clip.MOV", file_type="video")
    assert build_extension(photo) == ".mov"


def test_build_extension_maps_video_to_mp4_when_no_extension():
    photo = _make_photo(filename="noext", file_type="video")
    assert build_extension(photo) == ".mp4"


def test_build_extension_maps_live_photo_to_mov_when_no_extension():
    photo = _make_photo(filename="noext", file_type="live_photo")
    assert build_extension(photo) == ".mov"


def test_build_extension_maps_image_to_jpg_when_no_extension():
    photo = _make_photo(filename="noext", file_type="image")
    assert build_extension(photo) == ".jpg"


def test_build_extension_falls_back_when_type_unknown():
    photo = _make_photo(filename="noext", file_type="unknown_kind")
    assert build_extension(photo, fallback=".dat") == ".dat"


def test_build_extension_handles_enum_value_attribute():
    file_type_enum = SimpleNamespace(value="video")
    photo = _make_photo(filename="noext", file_type=file_type_enum)
    assert build_extension(photo) == ".mp4"


# _resolve_location_field helper (284-287)

def test_resolve_location_field_empty_when_no_metadata():
    photo = _make_photo(metadata_info=None)
    assert _resolve_location_field(photo, "city") == ""


def test_resolve_location_field_returns_attribute():
    md = _make_metadata(city="Beijing", province="BJ")
    photo = _make_photo(metadata_info=md)
    assert _resolve_location_field(photo, "city") == "Beijing"
    assert _resolve_location_field(photo, "province") == "BJ"


# collect_tokens smoke

def test_collect_tokens_parses_digits():
    assert collect_tokens("{date}_{index:3}") == [("date", 0), ("index", 3)]


def test_validate_template_rejects_empty():
    with pytest.raises(TemplateError) as exc:
        validate_template("")
    assert "不能为空" in str(exc.value)
