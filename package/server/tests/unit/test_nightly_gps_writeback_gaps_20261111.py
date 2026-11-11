"""Nightly gap coverage (2026-11-11) — app/utils/gps_writeback.py.

The 2026-11-11 backend coverage scan reported::

    utils/gps_writeback.py    82.4%   59 uncovered lines

``test_gps_writeback.py`` already covers the happy paths (JPEG/WebP/TIFF
round-trip, MP4 faststart / trailing-moov layouts, md5 relink).  What is
still uncovered are the *failure* branches — the ones that decide whether a
failed write-back leaves the user's original file intact:

* ``_cleanup`` swallowing an ``OSError`` while removing the temp file
* ``write_image_gps`` when piexif is unavailable
* ``write_image_gps`` when the write-back verification fails
* ``write_video_gps`` for a container without ``moov`` / for a tiny file
* ``_patch_chunk_offsets`` rejecting an stco / co64 offset overflow
* ``_verify_video_gps`` when the location or the structural metadata is lost
* ``update_photo_md5`` when the hash recalculation blows up

Every fixture is generated in-code (Pillow images + hand-built ISO BMFF
boxes), so the file stays CI-safe and needs no media assets.
"""

from __future__ import annotations

import hashlib
import os
import struct
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.utils import gps_writeback


pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


# --------------------------------------------------------------------------- #
# helpers (same style as test_gps_writeback.py)
# --------------------------------------------------------------------------- #

def _box(box_type: bytes, payload: bytes = b'') -> bytes:
    return struct.pack('>I', len(payload) + 8) + box_type + payload


def _mvhd() -> bytes:
    return _box(b'mvhd', b'\x00' * 100)


def _make_image(tmp_path, name: str = 'a.jpg'):
    from PIL import Image
    path = tmp_path / name
    Image.new('RGB', (8, 8), 'red').save(path, format='JPEG')
    return str(path)


def _video_file(tmp_path, name: str, *, with_moov: bool = True) -> str:
    ftyp = _box(b'ftyp', b'isom' + b'\x00' * 8)
    mdat = _box(b'mdat', b'X' * 64)
    moov = _box(b'moov', _mvhd()) if with_moov else b''
    path = tmp_path / name
    path.write_bytes(ftyp + mdat + moov)
    return str(path)


def _stco(entries: list[int]) -> bytes:
    payload = struct.pack('>II', 0, len(entries)) + b''.join(
        struct.pack('>I', e) for e in entries)
    return _box(b'stco', payload)


def _co64(entries: list[int]) -> bytes:
    payload = struct.pack('>II', 0, len(entries)) + b''.join(
        struct.pack('>Q', e) for e in entries)
    return _box(b'co64', payload)


# --------------------------------------------------------------------------- #
# _cleanup
# --------------------------------------------------------------------------- #

def test_cleanup_swallows_oserror_and_does_not_raise(tmp_path):
    """A temp file that cannot be removed must not break the write-back flow."""
    temp = tmp_path / 'leftover.gps.jpg'
    temp.write_bytes(b'x')
    with patch('app.utils.gps_writeback.os.remove', side_effect=OSError('locked')):
        gps_writeback._cleanup(str(temp))
    # still there, but no exception escaped
    assert temp.exists()


def test_cleanup_ignores_missing_path():
    gps_writeback._cleanup(None)
    gps_writeback._cleanup('/definitely/not/here.jpg')


# --------------------------------------------------------------------------- #
# write_image_gps failure branches
# --------------------------------------------------------------------------- #

def test_write_image_gps_without_piexif_is_unsupported(tmp_path):
    """Without piexif the module cannot write EXIF -> report as unsupported."""
    path = _make_image(tmp_path)
    with patch.object(gps_writeback, 'PIEXIF_AVAILABLE', False):
        with pytest.raises(gps_writeback.WriteBackUnsupported) as excinfo:
            gps_writeback.write_image_gps(path, 30.0, 120.0)
    assert 'piexif' in str(excinfo.value)


def test_write_image_gps_verification_failure_keeps_original(tmp_path):
    """A failed verification must not replace the original file."""
    path = _make_image(tmp_path, 'verify.jpg')
    original = open(path, 'rb').read()
    with patch('app.utils.gps_writeback._verify_image_gps',
               side_effect=ValueError('no GPS read back')):
        with pytest.raises(RuntimeError) as excinfo:
            gps_writeback.write_image_gps(path, 30.0, 120.0)
    assert 'Failed to write GPS' in str(excinfo.value)
    assert open(path, 'rb').read() == original
    assert [f for f in os.listdir(tmp_path) if '.gps' in f] == []


def test_write_image_gps_rejects_non_image_extension(tmp_path):
    path = tmp_path / 'clip.heic'
    path.write_bytes(b'\x00' * 32)
    with pytest.raises(gps_writeback.WriteBackUnsupported):
        gps_writeback.write_image_gps(str(path), 30.0, 120.0)


# --------------------------------------------------------------------------- #
# write_video_gps failure branches
# --------------------------------------------------------------------------- #

def test_write_video_gps_without_moov_box_is_unsupported(tmp_path):
    """A container without moov cannot receive a location atom."""
    path = _video_file(tmp_path, 'nomoov.mp4', with_moov=False)
    with pytest.raises(gps_writeback.WriteBackUnsupported) as excinfo:
        gps_writeback.write_video_gps(path, 30.0, 120.0)
    assert 'moov' in str(excinfo.value)


def test_write_video_gps_rejects_tiny_file(tmp_path):
    path = tmp_path / 'tiny.mp4'
    path.write_bytes(b'\x00' * 4)
    with pytest.raises(gps_writeback.WriteBackUnsupported) as excinfo:
        gps_writeback.write_video_gps(str(path), 30.0, 120.0)
    assert 'too small' in str(excinfo.value)


def test_write_video_gps_failure_cleans_temp_and_keeps_original(tmp_path):
    path = _video_file(tmp_path, 'boom.mp4')
    original = open(path, 'rb').read()
    with patch('app.utils.gps_writeback._verify_video_gps',
               side_effect=ValueError('boom')):
        with pytest.raises(RuntimeError):
            gps_writeback.write_video_gps(path, 1.0, 2.0)
    assert open(path, 'rb').read() == original
    assert [f for f in os.listdir(tmp_path) if '.gps' in f] == []


# --------------------------------------------------------------------------- #
# _patch_chunk_offsets overflow guards
# --------------------------------------------------------------------------- #

def test_patch_chunk_offsets_rejects_stco_overflow():
    """Pushing an stco entry past 32 bits must abort instead of truncating."""
    moov = _box(b'moov', _stco([0xFFFFFF00]))
    with pytest.raises(ValueError) as excinfo:
        gps_writeback._patch_chunk_offsets(moov, 0x1000)
    assert 'stco offset overflow' in str(excinfo.value)


def test_patch_chunk_offsets_rejects_negative_co64():
    """Pushing a co64 entry below zero must abort as well."""
    moov = _box(b'moov', _co64([16]))
    with pytest.raises(ValueError) as excinfo:
        gps_writeback._patch_chunk_offsets(moov, -32)
    assert 'co64 offset overflow' in str(excinfo.value)


def test_patch_chunk_offsets_shifts_entries_within_range():
    moov = _box(b'moov', _stco([100, 200]))
    patched = gps_writeback._patch_chunk_offsets(moov, 8)
    assert struct.unpack('>I', patched[8 + 8 + 8:8 + 8 + 12])[0] == 108


# --------------------------------------------------------------------------- #
# _verify_video_gps
# --------------------------------------------------------------------------- #

def test_verify_video_gps_requires_location_read_back(tmp_path):
    temp = tmp_path / 'out.mp4'
    temp.write_bytes(b'\x00' * 32)
    with patch('app.utils.gps_writeback.video_meta.extract_video_metadata',
               return_value={'duration': 1.0}):
        with pytest.raises(ValueError) as excinfo:
            gps_writeback._verify_video_gps(str(temp), 30.0, 120.0, str(temp))
    assert 'no location read back' in str(excinfo.value)


def test_verify_video_gps_detects_moved_coordinates(tmp_path):
    temp = tmp_path / 'out.mp4'
    temp.write_bytes(b'\x00' * 32)
    moved = {'location': {'latitude': 1.0, 'longitude': 2.0}}
    with patch('app.utils.gps_writeback.video_meta.extract_video_metadata',
               return_value=moved):
        with pytest.raises(ValueError) as excinfo:
            gps_writeback._verify_video_gps(str(temp), 30.0, 120.0, str(temp))
    assert 'GPS verification failed' in str(excinfo.value)


def test_verify_video_gps_detects_lost_structure_metadata(tmp_path):
    """Losing duration / width while writing is a hard failure, not a warning."""
    temp = tmp_path / 'out.mp4'
    temp.write_bytes(b'\x00' * 32)
    location = {'location': {'latitude': 30.0, 'longitude': 120.0}}
    original = {**location, 'duration': 10.0, 'width': 1920}
    rewritten = {**location, 'duration': None, 'width': 1920}
    with patch('app.utils.gps_writeback.video_meta.extract_video_metadata',
               side_effect=[rewritten, original]):
        with pytest.raises(ValueError) as excinfo:
            gps_writeback._verify_video_gps(str(temp), 30.0, 120.0, str(temp))
    assert 'Video structure verification failed' in str(excinfo.value)


# --------------------------------------------------------------------------- #
# _extract_data_box / meta helpers
# --------------------------------------------------------------------------- #

def test_extract_data_box_returns_none_for_garbage_body():
    value, indicator = gps_writeback._extract_data_box(b'\x00\x00\x00\x04garbage')
    assert value is None
    assert indicator == 0


def test_extract_data_box_returns_value_and_indicator():
    value = b'AB'
    body = struct.pack('>I', 16 + len(value)) + b'data' + struct.pack('>II', 1, 0) + value
    value, indicator = gps_writeback._extract_data_box(body)
    assert value == b'AB'
    assert indicator == 1


# --------------------------------------------------------------------------- #
# update_photo_md5 failure branches
# --------------------------------------------------------------------------- #

def test_update_photo_md5_returns_none_when_hash_fails(tmp_path):
    path = _make_image(tmp_path, 'md5.jpg')
    photo = SimpleNamespace(id='p1', file_path=path, md5='old', size=1)
    db = MagicMock()
    with patch('app.utils.hash.calculate_file_md5', side_effect=OSError('disk error')):
        assert gps_writeback.update_photo_md5(db, photo) is None
    db.add.assert_not_called()
    assert photo.md5 == 'old'


def test_update_photo_md5_ignores_empty_path(tmp_path):
    photo = SimpleNamespace(id='p1', file_path='', md5='old', size=1)
    db = MagicMock()
    assert gps_writeback.update_photo_md5(db, photo) is None
    db.add.assert_not_called()


def test_update_photo_md5_updates_size_after_write(tmp_path):
    path = _make_image(tmp_path, 'size.jpg')
    photo = SimpleNamespace(id='p1', file_path=path, md5='old', size=1)
    db = MagicMock()
    result = gps_writeback.update_photo_md5(db, photo)
    assert result == hashlib.md5(open(path, 'rb').read()).hexdigest()
    assert photo.size == os.path.getsize(path)



# --------------------------------------------------------------------------- #
# _verify_image_gps read-back guards
# --------------------------------------------------------------------------- #

def test_verify_image_gps_requires_a_read_back(tmp_path):
    """An image without GPS cannot pass the write-back verification."""
    path = _make_image(tmp_path, 'nogps.jpg')
    with pytest.raises(ValueError) as excinfo:
        gps_writeback._verify_image_gps(path, 30.0, 120.0)
    assert 'no GPS read back' in str(excinfo.value)


def test_verify_image_gps_detects_a_moved_coordinate(tmp_path):
    """A coordinate that does not survive the round-trip is a failure."""
    import piexif
    from PIL import Image
    path = tmp_path / 'moved.jpg'
    exif = piexif.dump({'0th': {piexif.ImageIFD.Make: b'Canon',
                                piexif.ImageIFD.Model: b'EOS'}})
    Image.new('RGB', (8, 8), 'red').save(path, format='JPEG', exif=exif)
    with patch('app.utils.exif.get_gps_info',
               return_value={'latitude': 1.0, 'longitude': 2.0}):
        with pytest.raises(ValueError) as excinfo:
            gps_writeback._verify_image_gps(path, 30.0, 120.0)
    assert 'GPS verification failed' in str(excinfo.value)


def test_write_image_gps_handles_webp_without_existing_exif(tmp_path):
    """A WebP without an EXIF segment starts from an empty EXIF block."""
    from PIL import Image
    path = tmp_path / 'plain.webp'
    Image.new('RGB', (8, 8), 'blue').save(path, format='WEBP')

    gps_writeback.write_image_gps(str(path), 30.5928, 114.3055)

    from app.utils.exif import get_exif_data, get_gps_info
    with Image.open(path) as image:
        exif = get_exif_data(image)
    read_back = get_gps_info(exif) if exif else None
    assert read_back is not None
    assert read_back['latitude'] == pytest.approx(30.5928, abs=1e-4)

