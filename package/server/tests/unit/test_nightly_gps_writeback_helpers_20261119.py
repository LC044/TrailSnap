"""覆盖 app/utils/gps_writeback.py 中此前没有任何测试引用的内部辅助函数。

本轮用「函数级静态引用扫描」定位盲区，本文件针对扫描出的 9 个未覆盖辅助
函数补测，全部不依赖样本文件 / 网络 / 外部服务：

* _is_supported_image / _validate_coordinates：格式与坐标校验分支；
* _make_temp_path / _atomic_replace：临时文件命名与原子替换；
* _to_dms / _build_gps_ifd：EXIF GPS IFD 编码；
* _format_iso6709 / _udta_text_atom：ISO 6709 文本串与 QuickTime 文本 atom；
* _read_range：区间读取。
"""

from __future__ import annotations

import os
import struct

import pytest

from app.utils import gps_writeback as gw

pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


# --------------------------------------------------------------------------- #
# _is_supported_image
# --------------------------------------------------------------------------- #

def test_is_supported_image_accepts_every_write_extension():
    for name in ("a.jpg", "a.JPEG", "a.webp", "a.tiff", "a.tif"):
        assert gw._is_supported_image(name) is True


def test_is_supported_image_rejects_unsupported_and_extensionless_paths():
    for name in ("a.heic", "a.mp4", "a.mov", "a.png", "a", "a.jpg.txt"):
        assert gw._is_supported_image(name) is False


# --------------------------------------------------------------------------- #
# _validate_coordinates
# --------------------------------------------------------------------------- #

def test_validate_coordinates_returns_float_pair():
    assert gw._validate_coordinates("30.5", "104.1") == (30.5, 104.1)
    assert gw._validate_coordinates(-90, 180) == (-90.0, 180.0)
    assert gw._validate_coordinates(0, 0) == (0.0, 0.0)


@pytest.mark.parametrize("bad", [
    (91.0, 0.0), (-91.0, 0.0), (0.0, 181.0), (0.0, -181.0),
    (float("nan"), 0.0), (0.0, float("nan")),
    (float("inf"), 0.0), (0.0, float("-inf")),
])
def test_validate_coordinates_rejects_out_of_range_and_non_finite(bad):
    with pytest.raises(ValueError):
        gw._validate_coordinates(*bad)


# --------------------------------------------------------------------------- #
# _make_temp_path / _atomic_replace
# --------------------------------------------------------------------------- #

def test_make_temp_path_keeps_extension_and_stays_next_to_source(tmp_path):
    target = tmp_path / "photo.jpg"
    target.write_bytes(b"payload")
    temp = gw._make_temp_path(str(target))
    try:
        assert temp.endswith(".gps.jpg")
        assert os.path.dirname(temp) == str(tmp_path)
        assert os.path.isfile(temp)
    finally:
        if os.path.exists(temp):
            os.remove(temp)


def test_make_temp_path_falls_back_to_cwd_without_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    temp = gw._make_temp_path("photo.png")
    try:
        assert temp.endswith(".gps.png")
        assert os.path.dirname(temp) == str(tmp_path.resolve())
    finally:
        if os.path.exists(temp):
            os.remove(temp)


def test_atomic_replace_overwrites_target_and_consumes_source(tmp_path):
    source = tmp_path / "src.bin"
    target = tmp_path / "dst.bin"
    source.write_bytes(b"new")
    target.write_bytes(b"old")
    gw._atomic_replace(str(source), str(target))
    assert target.read_bytes() == b"new"
    assert not source.exists()


# --------------------------------------------------------------------------- #
# _to_dms / _build_gps_ifd
# --------------------------------------------------------------------------- #

def test_to_dms_converts_decimal_degrees_to_rational_tuple():
    assert gw._to_dms(30.5) == ((30, 1), (30, 1), (0, 10000))
    assert gw._to_dms(0.0) == ((0, 1), (0, 1), (0, 10000))
    assert gw._to_dms(45.0) == ((45, 1), (0, 1), (0, 10000))


def test_to_dms_uses_absolute_value_and_keeps_four_decimal_seconds():
    assert gw._to_dms(-45.25) == ((45, 1), (15, 1), (0, 10000))
    degrees, minutes, seconds = gw._to_dms(12.345678)
    assert degrees == (12, 1)
    assert minutes == (20, 1)
    assert seconds[1] == 10000
    assert abs(seconds[0] / 10000 - 44.4408) < 1e-6


def test_build_gps_ifd_encodes_hemisphere_references():
    piexif = pytest.importorskip("piexif")
    north = gw._build_gps_ifd(30.5, 104.1)
    assert north[piexif.GPSIFD.GPSLatitudeRef] == b"N"
    assert north[piexif.GPSIFD.GPSLongitudeRef] == b"E"
    south = gw._build_gps_ifd(-30.5, -104.1)
    assert south[piexif.GPSIFD.GPSLatitudeRef] == b"S"
    assert south[piexif.GPSIFD.GPSLongitudeRef] == b"W"
    assert north[piexif.GPSIFD.GPSLatitude] == gw._to_dms(30.5)
    assert south[piexif.GPSIFD.GPSLongitude] == gw._to_dms(-104.1)


# --------------------------------------------------------------------------- #
# _format_iso6709 / _udta_text_atom
# --------------------------------------------------------------------------- #

def test_format_iso6709_matches_quicktime_layout():
    assert gw._format_iso6709(30.5, 104.1) == "+30.500000+104.100000+0000.0/"
    assert gw._format_iso6709(-30.5, -104.1) == "-30.500000-104.100000+0000.0/"


def test_udta_text_atom_encodes_size_type_language_and_text():
    atom = gw._udta_text_atom(b"\xa9xyz", "hello")
    assert struct.unpack(">I", atom[:4])[0] == len(atom)
    assert atom[4:8] == b"\xa9xyz"
    text_size, language = struct.unpack(">HH", atom[8:12])
    assert (text_size, language) == (5, 0)
    assert atom[12:] == b"hello"


def test_udta_text_atom_handles_empty_text():
    atom = gw._udta_text_atom(b"\xa9xyz", "")
    assert struct.unpack(">I", atom[:4])[0] == len(atom) == 12


# --------------------------------------------------------------------------- #
# _read_range
# --------------------------------------------------------------------------- #

def test_read_range_returns_requested_slice(tmp_path):
    path = tmp_path / "blob.bin"
    path.write_bytes(bytes(range(32)))
    with open(path, "rb") as handle:
        assert gw._read_range(handle, 8, 16) == bytes(range(8, 16))
        assert handle.tell() == 16
        assert gw._read_range(handle, 0, 4) == bytes(range(4))


def test_read_range_returns_empty_bytes_for_zero_length(tmp_path):
    path = tmp_path / "blob.bin"
    path.write_bytes(b"abcdef")
    with open(path, "rb") as handle:
        assert gw._read_range(handle, 3, 3) == b""
