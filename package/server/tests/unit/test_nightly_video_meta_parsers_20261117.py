"""2026-11-17 nightly coverage for the pure parsers in ``app/utils/video_meta.py``.

The 2026-11-17 targeted coverage scan reported ``utils/video_meta.py`` at 92%
with the following helpers never exercised:

* ``_iter_boxes`` - the 64-bit ``largesize`` header, the ``size == 0``
  "extends to the end of the container" form, and the truncated-header guards
  are never fed a malformed box;
* ``_qt_time_to_datetime`` - the out-of-range year guard and the
  non-positive timestamp guard are never hit;
* ``parse_datetime_string`` - a value that is not a string, an empty value and
  a year outside the plausible range are never handled;
* ``parse_iso6709`` - the type guard, the out-of-range guard and the
  ``0,0`` "null island" guard are never hit;
* ``_decode_text`` - the oversized payload guard and the non-printable guard
  are never hit.

These helpers are the boundary between untrusted vendor atoms and the photo
metadata store, so each guard deserves an explicit regression test.
"""

from __future__ import annotations

import io
from datetime import datetime

import pytest

from app.utils import video_meta


pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


def _box(box_type: bytes, payload: bytes = b"", size_override: int | None = None) -> bytes:
    """Build one ISO BMFF box header plus payload."""
    size = size_override if size_override is not None else 8 + len(payload)
    return size.to_bytes(4, "big") + box_type + payload


def test_is_video_file_accepts_every_supported_extension():
    for name in ("a.mp4", "a.MOV", "a.m4v", "a.avi", "a.mkv", "a.webm", "a.3gp"):
        assert video_meta.is_video_file(name) is True
    assert video_meta.is_video_file("a.jpg") is False


def test_is_isobmff_file_only_accepts_the_parsed_container_family():
    for name in ("a.mp4", "a.mov", "a.m4v", "a.3gp"):
        assert video_meta.is_isobmff_file(name) is True
    for name in ("a.avi", "a.mkv", "a.webm"):
        assert video_meta.is_isobmff_file(name) is False


def test_iter_boxes_reads_a_plain_box():
    stream = io.BytesIO(_box(b"moov", b"payload!"))
    assert list(video_meta._iter_boxes(stream, 0, len(stream.getvalue()))) == [
        (b"moov", 8, 16)
    ]


def test_iter_boxes_reads_a_64_bit_largesize_header():
    payload = b"x" * 4
    header = (1).to_bytes(4, "big") + b"moov" + (16 + len(payload)).to_bytes(8, "big")
    stream = io.BytesIO(header + payload)
    assert list(video_meta._iter_boxes(stream, 0, len(stream.getvalue()))) == [
        (b"moov", 16, 16 + len(payload))
    ]


def test_iter_boxes_stops_on_a_truncated_largesize_header():
    header = (1).to_bytes(4, "big") + b"moov" + b"\x00\x00"
    stream = io.BytesIO(header)
    assert list(video_meta._iter_boxes(stream, 0, len(stream.getvalue()))) == []


def test_iter_boxes_treats_size_zero_as_extending_to_the_end():
    payload = b"y" * 10
    stream = io.BytesIO((0).to_bytes(4, "big") + b"mdat" + payload)
    assert list(video_meta._iter_boxes(stream, 0, len(stream.getvalue()))) == [
        (b"mdat", 8, 18)
    ]


def test_iter_boxes_stops_on_a_truncated_header():
    stream = io.BytesIO(b"abc")
    assert list(video_meta._iter_boxes(stream, 0, len(stream.getvalue()))) == []


def test_iter_boxes_stops_on_a_box_smaller_than_its_own_header():
    stream = io.BytesIO((4).to_bytes(4, "big") + b"moov")
    assert list(video_meta._iter_boxes(stream, 0, len(stream.getvalue()))) == []


def test_fixed_point_helpers_decode_big_endian_values():
    assert video_meta._fixed16_16((1 << 16).to_bytes(4, "big", signed=True)) == 1.0
    assert video_meta._fixed2_30((1 << 30).to_bytes(4, "big", signed=True)) == 1.0


def test_qt_time_to_datetime_rejects_a_non_positive_timestamp():
    assert video_meta._qt_time_to_datetime(0) is None
    assert video_meta._qt_time_to_datetime(-1) is None


def test_qt_time_to_datetime_rejects_a_year_outside_the_plausible_range():
    # 1904 epoch + 100 years is still far below the accepted lower bound.
    assert video_meta._qt_time_to_datetime(1) is None
    assert video_meta._qt_time_to_datetime(60 * 60 * 24 * 365 * 200) is None


def test_qt_time_to_datetime_returns_a_naive_local_timestamp():
    parsed = video_meta._qt_time_to_datetime(60 * 60 * 24 * 365 * 100)
    assert isinstance(parsed, datetime)
    assert parsed.tzinfo is None
    assert 2003 <= parsed.year <= 2004


def test_parse_datetime_string_rejects_a_non_string_value():
    assert video_meta.parse_datetime_string(20261117) is None
    assert video_meta.parse_datetime_string(None) is None


def test_parse_datetime_string_rejects_an_empty_value():
    assert video_meta.parse_datetime_string("   ") is None
    assert video_meta.parse_datetime_string("\x00") is None


def test_parse_datetime_string_rejects_an_implausible_year():
    assert video_meta.parse_datetime_string("1850-01-01") is None


def test_parse_datetime_string_keeps_the_wall_clock_reading_of_an_offset():
    parsed = video_meta.parse_datetime_string("2024-03-01T08:30:00+08:00")
    assert parsed == datetime(2024, 3, 1, 8, 30, 0)
    assert parsed.tzinfo is None


def test_parse_datetime_string_normalises_a_zulu_suffix():
    parsed = video_meta.parse_datetime_string("2024-03-01T00:30:00Z")
    assert parsed == datetime(2024, 3, 1, 0, 30, 0)


def test_parse_iso6709_rejects_a_non_string_value():
    assert video_meta.parse_iso6709(1234) is None


def test_parse_iso6709_rejects_an_unparsable_string():
    assert video_meta.parse_iso6709("not a coordinate") is None


def test_parse_iso6709_rejects_an_out_of_range_coordinate():
    assert video_meta.parse_iso6709("+134.0522-118.2437+000.000/") is None
    assert video_meta.parse_iso6709("+34.0522+218.2437+000.000/") is None


def test_parse_iso6709_rejects_the_null_island_coordinate():
    assert video_meta.parse_iso6709("+00.0000+00.0000+000.000/") is None


def test_parse_iso6709_returns_latitude_and_longitude():
    parsed = video_meta.parse_iso6709("+34.0522-118.2437+000.000/")
    assert parsed == {"latitude": 34.0522, "longitude": -118.2437}


def test_decode_text_rejects_an_oversized_payload():
    assert video_meta._decode_text(b"a" * (video_meta._MAX_TEXT_BYTES + 1)) == ""


def test_decode_text_rejects_a_non_printable_payload():
    assert video_meta._decode_text(b"ok\x00\x01binary") == ""


def test_decode_text_decodes_a_plain_utf8_payload():
    assert video_meta._decode_text("  北京  ".encode("utf-8")) == "北京"
