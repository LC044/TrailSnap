"""Unit tests for the remaining ``app/utils/exif.py`` fallback branches.

The 2026-10-30 coverage scan showed ``app/utils/exif.py`` at 88.8% with 24
missed lines.  All of them sat in the defensive fallbacks of
``_convert_to_degrees`` / ``get_exif_data`` plus the "image could not be
opened" guard of ``extract_metadata``:

* ``_to_float`` -- a value that cannot be cast to float and has no
  ``numerator``/``denominator`` attributes, and an IFDRational whose
  denominator is zero;
* ``get_exif_data`` -- binary tag values that cannot be decoded, the
  Exif IFD / GPS IFD readers raising, and the legacy ``_getexif()``
  fallback (GPS dictionary + undecodable bytes);
* ``extract_metadata`` -- the file handle must be closed when Pillow
  refuses to open the file.

These are pure unit tests: no database, no network, no Pillow decoding.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.utils import exif
from app.utils.exif import _convert_to_degrees, extract_metadata, get_exif_data


pytestmark = [pytest.mark.smoke]


class _FakeExif(dict):
    """dict that also answers ``get_ifd`` like a real Pillow Exif object."""


def _image(top_level=None, exif_ifd=None, gps_ifd=None, legacy=None):
    """Build an image double whose EXIF readers can be told to fail."""
    fake = _FakeExif(top_level or {})
    fake.get_ifd = MagicMock(
        side_effect=lambda ifd: {
            0x8769: (exif_ifd or {}),
            0x8825: (gps_ifd or {}),
        }.get(ifd, {})
    )
    return SimpleNamespace(
        getexif=MagicMock(return_value=fake),
        _getexif=MagicMock(return_value=legacy),
    )


# -------------------------------------------------------------------------
# _convert_to_degrees -> _to_float fallbacks
# -------------------------------------------------------------------------


class _Uncastable:
    """A value that refuses float() and carries no IFDRational attributes."""

    def __float__(self):
        raise TypeError("not a number")


class _ZeroDenominator:
    """An IFDRational-like value whose denominator is zero."""

    numerator = 30
    denominator = 0

    def __float__(self):
        raise TypeError("not a number")


def test_convert_to_degrees_falls_back_to_zero_for_uncastable_value():
    # A GPS tuple whose members cannot be converted at all must degrade to
    # 0.0 instead of raising, otherwise one broken tag kills the import.
    assert _convert_to_degrees((_Uncastable(), 0, 0)) == 0.0


def test_convert_to_degrees_guards_zero_denominator_ifdrational():
    assert _convert_to_degrees((_ZeroDenominator(), 0, 0)) == 0.0


# -------------------------------------------------------------------------
# get_exif_data -> binary values that cannot be decoded
# -------------------------------------------------------------------------


def test_get_exif_data_stringifies_undecodable_top_level_bytes():
    image = _image(top_level={270: b"\xff\xfe"})
    result = get_exif_data(image)
    assert result["ImageDescription"] == str(b"\xff\xfe")


def test_get_exif_data_stringifies_undecodable_exif_ifd_bytes():
    image = _image(top_level={271: "x"}, exif_ifd={315: b"\xff\xfe"})
    result = get_exif_data(image)
    assert result["Artist"] == str(b"\xff\xfe")


def test_get_exif_data_keeps_non_binary_exif_ifd_values():
    image = _image(top_level={271: "x"}, exif_ifd={315: "Grace"})
    result = get_exif_data(image)
    assert result["Artist"] == "Grace"


def test_get_exif_data_survives_exif_ifd_reader_failure():
    image = _image(top_level={271: "x"})
    image.getexif.return_value.get_ifd = MagicMock(side_effect=RuntimeError("broken ifd"))
    result = get_exif_data(image)
    assert result["Make"] == "x"


def test_get_exif_data_survives_gps_ifd_reader_failure():
    image = _image(top_level={271: "x"})
    image.getexif.return_value.get_ifd = MagicMock(side_effect=RuntimeError("broken gps"))
    result = get_exif_data(image)
    assert result["Make"] == "x"
    assert "GPSInfo" not in result


# -------------------------------------------------------------------------
# get_exif_data -> legacy _getexif() fallback
# -------------------------------------------------------------------------


def test_get_exif_data_legacy_fallback_decodes_gps_dictionary():
    legacy = {34853: {1: "N", 2: (30, 0, 0)}}
    image = _image(top_level=None, legacy=legacy)
    result = get_exif_data(image)
    assert result["GPSInfo"]["GPSLatitudeRef"] == "N"
    assert result["GPSInfo"]["GPSLatitude"] == (30, 0, 0)


def test_get_exif_data_legacy_fallback_stringifies_undecodable_bytes():
    legacy = {270: b"\xff\xfe"}
    image = _image(top_level=None, legacy=legacy)
    result = get_exif_data(image)
    assert result["ImageDescription"] == str(b"\xff\xfe")


# -------------------------------------------------------------------------
# extract_metadata -> the file handle must be released on decode failure
# -------------------------------------------------------------------------


def test_extract_metadata_closes_file_handle_when_image_cannot_be_opened(tmp_path):
    image_path = tmp_path / "broken.jpg"
    image_path.write_bytes(b"not-an-image")

    source = MagicMock()
    with patch.object(exif, "budgeted_open", return_value=source), \
            patch.object(exif.Image, "open", side_effect=OSError("cannot open")):
        metadata = extract_metadata(str(image_path), "broken.jpg")

    # The unreadable file must not leak its descriptor, and the caller still
    # gets a usable metadata dict.
    assert source.close.call_count == 1
    assert metadata["photo_time"] is not None
