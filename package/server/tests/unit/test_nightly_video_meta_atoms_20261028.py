"""2026-10-28 nightly coverage for ``app/utils/video_meta.py``.

The 2026-10-28 backend coverage scan reported ``utils/video_meta.py`` at 85%
with 44 uncovered lines.  Every uncovered line sat inside the ISO-BMFF atom
parsers, i.e. the pure byte-level helpers that decode QuickTime/MP4 metadata
without any external binary.

Those helpers are exactly where a silent regression hides: a mis-sized box
header makes ``_iter_boxes`` walk off the end of the file, a wrong offset in
``_parse_tkhd`` swaps the reported rotation, and an over-eager text decode
turns a JPEG cover-art blob into a multi-megabyte JSON string.

Every test below builds the box layout by hand so the expected value is
derived from the format spec rather than from the implementation.
"""

from __future__ import annotations

import io
import struct
from datetime import datetime, timezone

import pytest

pytestmark = [pytest.mark.smoke]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def box(box_type: bytes, payload: bytes) -> bytes:
    """A regular 32-bit-sized ISO-BMFF box."""
    assert len(box_type) == 4
    return struct.pack(">I", len(payload) + 8) + box_type + payload


def large_box(box_type: bytes, payload: bytes) -> bytes:
    """A box that uses the 64-bit ``largesize`` encoding."""
    return struct.pack(">I", 1) + box_type + struct.pack(">Q", len(payload) + 16) + payload


def data_box(type_indicator: int, value: bytes) -> bytes:
    """An ``ilst`` item body: a single ``data`` box."""
    inner = struct.pack(">I", type_indicator) + b"\x00\x00\x00\x00" + value
    return box(b"data", inner)


# ---------------------------------------------------------------------------
# _iter_boxes / _read_payload
# ---------------------------------------------------------------------------


def test_iter_boxes_walks_sibling_boxes():
    from app.utils import video_meta

    payload = box(b"ftyp", b"isom") + box(b"moov", b"data")
    boxes = list(video_meta._iter_boxes(io.BytesIO(payload), 0, len(payload)))

    assert [item[0] for item in boxes] == [b"ftyp", b"moov"]
    assert boxes[0][1] == 8
    assert boxes[0][2] == 12


def test_iter_boxes_reads_the_64_bit_largesize_header():
    from app.utils import video_meta

    payload = large_box(b"moov", b"abcd")
    boxes = list(video_meta._iter_boxes(io.BytesIO(payload), 0, len(payload)))

    assert len(boxes) == 1
    assert boxes[0][0] == b"moov"
    # The payload starts after the 16-byte header and ends at the box end.
    assert boxes[0][1] == 16
    assert boxes[0][2] == len(payload)


def test_iter_boxes_treats_a_zero_size_as_extending_to_the_end():
    from app.utils import video_meta

    payload = struct.pack(">I", 0) + b"free" + b"tail-bytes"
    boxes = list(video_meta._iter_boxes(io.BytesIO(payload), 0, len(payload)))

    assert len(boxes) == 1
    assert boxes[0][0] == b"free"
    assert boxes[0][2] == len(payload)


def test_iter_boxes_stops_on_a_size_smaller_than_the_header():
    from app.utils import video_meta

    payload = struct.pack(">I", 4) + b"free" + b"xxxx"
    assert list(video_meta._iter_boxes(io.BytesIO(payload), 0, len(payload))) == []


def test_iter_boxes_stops_when_a_box_overruns_its_container():
    from app.utils import video_meta

    payload = struct.pack(">I", 64) + b"free" + b"short"
    boxes = list(video_meta._iter_boxes(io.BytesIO(payload), 0, len(payload)))

    assert len(boxes) == 1
    assert boxes[0][2] == len(payload)


def test_iter_boxes_ignores_a_trailing_partial_header():
    from app.utils import video_meta

    payload = box(b"free", b"") + b"\x00\x00"
    boxes = list(video_meta._iter_boxes(io.BytesIO(payload), 0, len(payload)))

    assert [item[0] for item in boxes] == [b"free"]


def test_read_payload_returns_empty_for_a_zero_length_range():
    from app.utils import video_meta

    assert video_meta._read_payload(io.BytesIO(b"abc"), 2, 2) == b""


def test_read_payload_reads_the_requested_range():
    from app.utils import video_meta

    assert video_meta._read_payload(io.BytesIO(b"abcdef"), 1, 4) == b"bcd"


# ---------------------------------------------------------------------------
# fixed point / time helpers
# ---------------------------------------------------------------------------


def test_fixed_point_helpers_decode_the_two_qt_scales():
    from app.utils import video_meta

    assert video_meta._fixed16_16((1 << 16).to_bytes(4, "big")) == 1.0
    assert video_meta._fixed2_30((1 << 30).to_bytes(4, "big")) == 1.0
    # Negative values are signed in the QuickTime matrix encoding.
    assert video_meta._fixed16_16((-1 << 16).to_bytes(4, "big", signed=True)) == -1.0


def test_qt_time_to_datetime_rejects_non_positive_and_out_of_range_values():
    from app.utils import video_meta

    assert video_meta._qt_time_to_datetime(0) is None
    assert video_meta._qt_time_to_datetime(-10) is None
    # 1904 epoch + ~317 years lands far outside the accepted shooting window.
    assert video_meta._qt_time_to_datetime(10_000_000_000) is None


def test_qt_time_to_datetime_returns_a_naive_local_datetime():
    from app.utils import video_meta

    seconds = int((datetime(2024, 5, 6, 7, 8, 9, tzinfo=timezone.utc)
                    - datetime(1904, 1, 1, tzinfo=timezone.utc)).total_seconds())
    parsed = video_meta._qt_time_to_datetime(seconds)

    assert parsed is not None
    assert parsed.tzinfo is None
    assert parsed.year == 2024


# ---------------------------------------------------------------------------
# text decoding
# ---------------------------------------------------------------------------


def test_decode_text_rejects_an_oversized_payload():
    from app.utils import video_meta

    assert video_meta._decode_text(b"x" * (video_meta._MAX_TEXT_BYTES + 1)) == ""


def test_decode_text_reads_utf16_and_drops_the_null_terminator():
    from app.utils import video_meta

    # A non-ASCII character whose UTF-16BE bytes are invalid UTF-8 forces
    # the decoder past its first (UTF-8) attempt.
    assert video_meta._decode_text("caf\u00e9".encode("utf-16-be") + b"\x00\x00") == "caf\u00e9"


def test_decode_text_rejects_control_characters():
    from app.utils import video_meta

    assert video_meta._decode_text(b"ok\x01\x02") == ""


def test_atom_type_to_key_keeps_the_copyright_sign():
    from app.utils import video_meta

    assert video_meta._atom_type_to_key(b"\xa9day") == "\xa9day"


# ---------------------------------------------------------------------------
# udta / keys / ilst / meta
# ---------------------------------------------------------------------------


def test_parse_udta_reads_a_known_text_atom_and_skips_unknown_ones():
    from app.utils import video_meta

    text = b"2024-01-02"
    day_atom = box(b"\xa9day", struct.pack(">H", len(text)) + b"\x55\xc4" + text)
    unknown_atom = box(b"zzzz", b"\x00\x01\x02\x03")
    tags = video_meta._parse_udta(day_atom + unknown_atom)

    assert tags == {"\xa9day": "2024-01-02"}


def test_parse_udta_reads_a_bare_text_atom_without_the_length_header():
    from app.utils import video_meta

    tags = video_meta._parse_udta(box(b"\xa9nam", b"Beijing"))

    assert tags == {"\xa9nam": "Beijing"}


def test_parse_udta_merges_a_nested_meta_atom():
    from app.utils import video_meta

    meta_payload = b"\x00\x00\x00\x00" + box(b"ilst", box(b"\xa9nam", data_box(1, b"Nested")))
    tags = video_meta._parse_udta(box(b"meta", meta_payload))

    assert tags == {"\xa9nam": "Nested"}


def test_parse_keys_returns_an_empty_list_for_a_truncated_payload():
    from app.utils import video_meta

    assert video_meta._parse_keys(b"\x00\x00\x00\x00") == []


def test_parse_keys_reads_the_ordered_key_names():
    from app.utils import video_meta

    inner = b"\x00\x00\x00\x00" + struct.pack(">I", 2)
    inner += box(b"mdta", b"com.apple.quicktime.make")
    inner += box(b"mdta", b"com.apple.quicktime.model")
    keys = video_meta._parse_keys(inner)

    assert keys == ["com.apple.quicktime.make", "com.apple.quicktime.model"]


def test_parse_data_box_reads_text_signed_integers_and_floats():
    from app.utils import video_meta

    assert video_meta._parse_data_box(data_box(1, b"Beijing")) == "Beijing"
    assert video_meta._parse_data_box(data_box(21, (7).to_bytes(8, "big"))) == 7
    assert video_meta._parse_data_box(data_box(22, (7).to_bytes(8, "big"))) == 7
    assert video_meta._parse_data_box(data_box(23, struct.pack(">f", 1.5))) == 1.5


def test_parse_data_box_returns_none_for_cover_art_and_unknown_types():
    from app.utils import video_meta

    assert video_meta._parse_data_box(data_box(13, b"\xff\xd8\xff\xe0binary")) is None
    assert video_meta._parse_data_box(data_box(99, b"whatever")) is None


def test_parse_data_box_ignores_boxes_that_are_not_data_boxes():
    from app.utils import video_meta

    assert video_meta._parse_data_box(box(b"free", b"ignored")) is None


def test_parse_ilst_uses_the_keys_table_for_mdta_style_entries():
    from app.utils import video_meta

    payload = box(struct.pack(">I", 1), data_box(1, b"Apple"))
    tags = video_meta._parse_ilst(payload, ["com.apple.quicktime.make"])

    assert tags == {"com.apple.quicktime.make": "Apple"}


def test_parse_ilst_falls_back_to_the_itunes_style_key_and_skips_cover_art():
    from app.utils import video_meta

    payload = box(b"\xa9nam", data_box(1, b"Title")) + box(b"covr", data_box(13, b"\xff\xd8binary"))
    tags = video_meta._parse_ilst(payload, [])

    assert tags == {"\xa9nam": "Title"}


def test_parse_meta_skips_the_fullbox_version_and_flags_header():
    from app.utils import video_meta

    payload = b"\x00\x00\x00\x00" + box(b"ilst", box(b"\xa9nam", data_box(1, b"Nested")))
    tags = video_meta._parse_meta(payload)

    assert tags == {"\xa9nam": "Nested"}


def test_parse_meta_detects_a_quicktime_meta_without_a_fullbox_header():
    from app.utils import video_meta

    payload = box(b"hdlr", b"\x00\x00\x00\x00") + box(b"ilst", box(b"\xa9nam", data_box(1, b"QT")))
    tags = video_meta._parse_meta(payload)

    assert tags == {"\xa9nam": "QT"}


def test_parse_meta_returns_an_empty_dict_for_a_truncated_payload():
    from app.utils import video_meta

    assert video_meta._parse_meta(b"\x00\x00\x00") == {}


# ---------------------------------------------------------------------------
# track headers
# ---------------------------------------------------------------------------


def test_parse_mvhd_reads_the_version_zero_timing():
    from app.utils import video_meta

    payload = b"\x00" * 4 + struct.pack(">I", 0) + struct.pack(">I", 0)
    payload += struct.pack(">I", 1000) + struct.pack(">I", 5000)
    info = video_meta._parse_mvhd(payload)

    assert info["duration"] == 5.0


def test_parse_mvhd_omits_the_unknown_duration_sentinel():
    from app.utils import video_meta

    payload = b"\x00" * 4 + struct.pack(">I", 0) + struct.pack(">I", 0)
    payload += struct.pack(">I", 1000) + struct.pack(">I", 0xFFFFFFFF)
    info = video_meta._parse_mvhd(payload)

    assert "duration" not in info


def test_parse_mvhd_reads_the_version_one_timing():
    from app.utils import video_meta

    payload = b"\x01" + b"\x00" * 3 + struct.pack(">Q", 0)
    payload += b"\x00" * 8 + struct.pack(">I", 500) + struct.pack(">Q", 2500)
    info = video_meta._parse_mvhd(payload)

    assert info["duration"] == 5.0


def test_parse_mvhd_returns_an_empty_dict_for_a_truncated_payload():
    from app.utils import video_meta

    assert video_meta._parse_mvhd(b"\x00\x00") == {}


def test_parse_tkhd_swaps_the_reported_size_for_a_rotated_track():
    from app.utils import video_meta

    payload = bytearray(84)
    payload[0] = 0  # version 0
    payload[44:48] = struct.pack(">i", 1 << 16)  # matrix b == 1.0
    payload[76:80] = struct.pack(">i", 1920 << 16)
    payload[80:84] = struct.pack(">i", 1080 << 16)
    info = video_meta._parse_tkhd(bytes(payload))

    assert info["rotation"] == 90
    assert info["width"] == 1080
    assert info["height"] == 1920


def test_parse_tkhd_reports_no_rotation_for_an_upright_track():
    from app.utils import video_meta

    payload = bytearray(84)
    payload[0] = 0
    payload[40:44] = struct.pack(">i", 1 << 16)  # matrix a == 1.0
    payload[76:80] = struct.pack(">i", 1920 << 16)
    payload[80:84] = struct.pack(">i", 1080 << 16)
    info = video_meta._parse_tkhd(bytes(payload))

    assert info["rotation"] == 0
    assert (info["width"], info["height"]) == (1920, 1080)


def test_parse_tkhd_returns_an_empty_dict_for_a_truncated_payload():
    from app.utils import video_meta

    assert video_meta._parse_tkhd(b"\x00" * 10) == {}


def test_parse_mdhd_computes_the_media_duration():
    from app.utils import video_meta

    payload = b"\x00" * 12 + struct.pack(">I", 1000) + struct.pack(">I", 2500)
    info = video_meta._parse_mdhd(payload)

    assert info["duration"] == 2.5


def test_parse_mdhd_omits_the_duration_when_the_timescale_is_zero():
    from app.utils import video_meta

    payload = b"\x00" * 12 + struct.pack(">I", 0) + struct.pack(">I", 2500)

    assert "duration" not in video_meta._parse_mdhd(payload)


def test_parse_stsd_codec_and_sample_count():
    from app.utils import video_meta

    assert video_meta._parse_stsd_codec(b"\x00" * 12 + b"avc1") == "avc1"
    assert video_meta._parse_stsz_sample_count(b"\x00" * 8 + struct.pack(">I", 900)) == 900
    # A zero sample count is reported as "unknown" rather than 0.
    assert video_meta._parse_stsz_sample_count(b"\x00" * 8 + struct.pack(">I", 0)) is None
    assert video_meta._parse_stsz_sample_count(b"\x00" * 4) is None
