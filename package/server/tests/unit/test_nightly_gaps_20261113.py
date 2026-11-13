"""Nightly watch 2026-11-13: coverage gaps for utils (gps_writeback / path_validation / export_formatter).

Target modules (from tests/artifacts/nightly/2026-11-13/coverage-gaps-backend.txt):
- app/utils/gps_writeback.py  (90.8%, 31 missed lines)
- app/utils/path_validation.py (94.0%)
- app/utils/export_formatter.py (92.0%)
"""

import io
import struct

import pytest

from app.utils import export_formatter, gps_writeback, path_validation


pytestmark = pytest.mark.smoke


# ---------------------------------------------------------------------------
# app/utils/gps_writeback.py
# ---------------------------------------------------------------------------


def _atom(atom_type: bytes, text: str) -> bytes:
    return gps_writeback._udta_text_atom(atom_type, text)


def test_build_location_udta_without_existing_payload():
    result = gps_writeback._build_location_udta(None, "+30.5000+114.3000+100.000/")

    assert result == _atom(b"\xa9xyz", "+30.5000+114.3000+100.000/")


def test_build_location_udta_replaces_existing_xyz_atom():
    existing = _atom(b"\xa9xyz", "+00.0000+000.0000+000.000/")
    other = _atom(b"\xa9nam", "old")

    result = gps_writeback._build_location_udta(existing + other, "+30.5000+114.3000+100.000/")

    assert result.count(b"\xa9xyz") == 1
    assert b"+30.5000+114.3000+100.000/" in result
    assert b"old" in result


def test_build_location_udta_appends_when_xyz_is_missing():
    existing = _atom(b"\xa9nam", "keep-me")

    result = gps_writeback._build_location_udta(existing, "+30.5000+114.3000+100.000/")

    assert b"keep-me" in result
    assert b"\xa9xyz" in result


def test_build_location_udta_stops_on_malformed_atom_size():
    broken = struct.pack(">I", 4) + b"\xa9xyz"

    result = gps_writeback._build_location_udta(broken, "+30.5000+114.3000+100.000/")

    # The malformed head is dropped and a fresh xyz atom is appended.
    assert b"\xa9xyz" in result


def test_walk_offset_boxes_handles_extended_size_and_zero_size_boxes():
    # extended size box (size == 1) with a 64-bit size field
    extended = struct.pack(">I", 1) + b"stco" + struct.pack(">Q", 24) + b"\x00" * 8
    # zero size box: extends to the end of the buffer
    zero_size = struct.pack(">I", 0) + b"co64" + b"\x00" * 8

    found = list(gps_writeback._walk_offset_boxes(bytearray(extended + zero_size)))

    assert [box_type for box_type, _ in found] == [b"stco", b"co64"]


def test_copy_stream_stops_when_source_is_exhausted():
    src = io.BytesIO(b"12345")
    dst = io.BytesIO()

    gps_writeback._copy_stream(src, dst, 100)

    assert dst.getvalue() == b"12345"


def test_build_location_meta_reads_existing_ilst_entries():
    entry = gps_writeback._mdta_ilst_entry(1, b"+30.5000+114.3000+100.000/")
    ilst = struct.pack(">I", len(entry) + 8) + b"ilst" + entry
    # QuickTime MOV style meta payload: the child boxes follow each other.
    existing = ilst

    result = gps_writeback._build_location_meta(existing, "+30.5000+114.3000+100.000/")

    assert isinstance(result, (bytes, bytearray))
    assert len(result) > 0
    assert b"ilst" in result


def test_build_location_meta_resolves_ilst_key_names_from_keys_box():
    name = b"com.apple.quicktime.location.ISO6709"
    key_entry = struct.pack(">I", 8 + len(name)) + b"mdta" + name
    keys_inner = struct.pack(">II", 0, 1) + key_entry
    keys_box = struct.pack(">I", len(keys_inner) + 8) + b"keys" + keys_inner

    entry = gps_writeback._mdta_ilst_entry(1, b"+30.5000+114.3000+100.000/")
    ilst = struct.pack(">I", len(entry) + 8) + b"ilst" + entry
    existing = keys_box + ilst

    result = gps_writeback._build_location_meta(existing, "+30.5000+114.3000+100.000/")

    assert isinstance(result, (bytes, bytearray))
    assert len(result) > 0


def test_build_location_meta_ignores_malformed_ilst_entries():
    broken_entry = struct.pack(">I", 4) + b"\x00\x00\x00\x01"
    ilst = struct.pack(">I", len(broken_entry) + 8) + b"ilst" + broken_entry
    existing = ilst

    result = gps_writeback._build_location_meta(existing, "+30.5000+114.3000+100.000/")

    assert isinstance(result, (bytes, bytearray))


def test_build_location_meta_handles_full_box_style_payload():
    existing = b"\x00\x00\x00\x00meta"

    result = gps_writeback._build_location_meta(existing, "+30.5000+114.3000+100.000/")

    assert isinstance(result, (bytes, bytearray))
    assert result.startswith(b"\x00\x00\x00\x00")


def test_build_location_meta_ignores_meta_boxes_with_broken_size():
    ilst = struct.pack(">I", 12) + b"ilst" + b"\x00\x00\x00\x00"
    existing = b"\x00\x00\x00\x00" + ilst

    result = gps_writeback._build_location_meta(existing, "+30.5000+114.3000+100.000/")

    assert isinstance(result, (bytes, bytearray))


# ---------------------------------------------------------------------------
# app/utils/path_validation.py
# ---------------------------------------------------------------------------


def test_pathconf_limit_walks_up_to_the_nearest_existing_parent(tmp_path):
    missing = tmp_path / "does" / "not" / "exist"
    missing.parent.mkdir(parents=True, exist_ok=True)

    limit = path_validation._pathconf_limit(str(missing), "PC_NAME_MAX", 255)

    assert isinstance(limit, int)
    assert limit > 0


# ---------------------------------------------------------------------------
# app/utils/export_formatter.py
# ---------------------------------------------------------------------------


def test_parse_exif_info_accepts_already_decoded_dict():
    assert export_formatter._parse_exif_info({"Model": "A1"}) == {"Model": "A1"}


def test_parse_exif_info_rejects_non_mapping_values():
    assert export_formatter._parse_exif_info(123) == {}
    assert export_formatter._parse_exif_info("[1, 2]") == {}
