"""MP4 `ftyp` sniffing used to tell motion clips from HEIF stills."""
import pytest

from app.utils.motion_photo import _is_video_ftyp

pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


def _box(major_brand, compatible=()):
    size = 16 + 4 * len(compatible)
    data = size.to_bytes(4, "big") + b"ftyp" + major_brand + b"\x00\x00\x00\x00"
    for brand in compatible:
        data += brand
    return data


def test_video_major_brand_is_accepted():
    data = _box(b"isom")
    assert _is_video_ftyp(data, 0, len(data)) is True


def test_heif_major_brand_is_rejected():
    data = _box(b"heic")
    assert _is_video_ftyp(data, 0, len(data)) is False


def test_heif_compatible_brand_rejects_an_otherwise_video_box():
    data = _box(b"isom", (b"heic",))
    assert _is_video_ftyp(data, 0, len(data)) is False


def test_video_compatible_brand_is_accepted():
    data = _box(b"mp42", (b"isom",))
    assert _is_video_ftyp(data, 0, len(data)) is True


def test_three_gp_brand_is_accepted():
    data = _box(b"3gp4")
    assert _is_video_ftyp(data, 0, len(data)) is True


def test_box_smaller_than_the_minimum_is_rejected():
    data = (12).to_bytes(4, "big") + b"ftyp" + b"isom" + b"\x00\x00\x00\x00"
    assert _is_video_ftyp(data, 0, len(data)) is False


def test_box_that_is_not_a_multiple_of_four_is_rejected():
    data = bytearray(_box(b"isom"))
    data[3] = 0x11
    assert _is_video_ftyp(bytes(data), 0, len(data)) is False


def test_box_larger_than_the_file_is_rejected():
    data = _box(b"isom")
    assert _is_video_ftyp(data, 0, len(data) - 1) is False


def test_box_outside_the_file_is_rejected():
    data = _box(b"isom")
    assert _is_video_ftyp(data, 8, len(data)) is False
