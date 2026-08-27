"""Unit tests covering 2026-08-27 nightly coverage gap scan.

Targets uncovered branches in app.utils.motion_photo (66 percent covered,
18 of 62 lines missed). The earlier test_motion_photo_utils.py (2026-08-04
round) only exercises the happy paths for get_video_offset and extract_video;
this file complements it by driving the remaining branches:
  * XMP tag-style MicroVideoOffset (line 35)
  * Empty file fallback (line 42)
  * ftyp atom at start (line 50) and ftyp with out-of-range size (line 54)
  * ftyp inside the size window at file start (line 62)
  * mmap ValueError fallback (lines 64-66)
  * generic exception swallowed by get_video_offset (lines 70-71)
  * extract_video auto-detects offset (lines 81-83)
  * extract_video defaults to .mp4 sibling (line 89)
  * extract_video reuses an existing .mp4 file without rewriting (line 92)
  * extract_video rejection of bad offsets (line 103) and exception cleanup
    path that removes a partial output file (lines 112-119)
"""
import builtins
import os
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.utils import motion_photo
from app.utils.motion_photo import extract_video, get_video_offset


pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


def test_get_video_offset_reads_tag_style_microvideo(tmp_path):
    path = tmp_path / 'motion.jpg'
    path.write_bytes(b'<rdf:GCamera:MicroVideoOffset>12345</rdf:GCamera:MicroVideoOffset>')
    assert get_video_offset(str(path)) == 12345

def test_get_video_offset_returns_none_for_empty_file(tmp_path):
    path = tmp_path / 'empty.jpg'
    path.write_bytes(b'')
    assert get_video_offset(str(path)) is None

def test_get_video_offset_skips_ftyp_within_first_four_bytes(tmp_path):
    # ftyp at file byte 0..3 has no preceding size header; pos < 4 skips it.
    path = tmp_path / 'motion.jpg'
    path.write_bytes(b'ftyp-prefix' + b'x' * 32)
    assert get_video_offset(str(path)) is None

def test_get_video_offset_skips_ftyp_with_size_outside_window(tmp_path):
    # An ftyp atom whose declared size is outside 8..128 is ignored.
    payload = (256).to_bytes(4, 'big') + b'ftyp' + b'x' * 128
    path = tmp_path / 'motion.jpg'
    path.write_bytes(b'prefix' + payload)
    assert get_video_offset(str(path)) is None

def test_get_video_offset_returns_none_for_ftyp_at_file_start(tmp_path):
    # ftyp at byte 0 is dropped by the atom_start > 0 guard.
    payload = (16).to_bytes(4, 'big') + b'ftyp' + b'x' * 8
    path = tmp_path / 'edge.jpg'
    path.write_bytes(payload)
    assert get_video_offset(str(path)) is None

def test_get_video_offset_swallows_value_error_from_mmap(tmp_path):
    # mmap raises ValueError for an empty stream; we return None (lines 64-66).
    path = tmp_path / 'boom.jpg'
    path.write_bytes(b'x' * 16)

    def fake_mmap(_fd, _length, access):
        raise ValueError('simulated mmap error')

    original = motion_photo.mmap.mmap
    motion_photo.mmap.mmap = fake_mmap
    try:
        result = motion_photo.get_video_offset(str(path))
    finally:
        motion_photo.mmap.mmap = original
    assert result is None

def test_get_video_offset_swallows_generic_exception(tmp_path):
    # Anything raised inside the try block is swallowed by line 70-71.
    path = tmp_path / 'any.jpg'
    path.write_bytes(b'some')
    bad_os = SimpleNamespace(getsize=lambda _p: 1 // 0)
    with patch.object(motion_photo, 'os', bad_os):
        assert motion_photo.get_video_offset(str(path)) is None

def test_extract_video_auto_detects_offset_when_missing(tmp_path):
    # extract_video(file) without offset auto-detects via get_video_offset.
    src = tmp_path / 'clip.jpg'
    image = b'image-bytes'
    atom = (24).to_bytes(4, 'big') + b'ftyp' + b'isom' + (b'x' * 16)
    src.write_bytes(image + atom)
    expected_mp4 = tmp_path / 'clip.mp4'
    with patch.object(motion_photo, 'get_video_offset', return_value=len(atom)):
        result = extract_video(str(src))
    assert result == str(expected_mp4)
    assert expected_mp4.read_bytes() == atom

def test_extract_video_returns_existing_mp4_without_rewriting(tmp_path):
    # If target .mp4 exists, extract_video returns it without rewriting (line 91-92).
    src = tmp_path / 'still.jpg'
    src.write_bytes(b'image' + b'video-tail')
    target = tmp_path / 'still.mp4'
    target.write_bytes(b'PRE-EXISTING')
    with patch.object(motion_photo, 'get_video_offset', return_value=11):
        result = extract_video(str(src))
    assert result == str(target)
    assert target.read_bytes() == b'PRE-EXISTING'

def test_extract_video_rejects_offset_at_file_size(tmp_path):
    # video_start <= 0 returns None without touching the target file.
    src = tmp_path / 'bad.jpg'
    src.write_bytes(b'abcdef')
    target = tmp_path / 'bad.mp4'
    with patch.object(motion_photo, 'get_video_offset', return_value=os.path.getsize(str(src))):
        assert extract_video(str(src), video_path=str(target)) is None
    assert not target.exists()

def test_extract_video_rejects_oversized_offset(tmp_path):
    # Offset larger than file size makes video_start negative; rejected.
    src = tmp_path / 'neg.jpg'
    src.write_bytes(b'abc')
    target = tmp_path / 'neg.mp4'
    assert extract_video(str(src), offset=100, video_path=str(target)) is None
    assert not target.exists()

def test_extract_video_cleans_up_partial_output_on_open_failure(tmp_path):
    # If writing the .mp4 raises, the partial output is removed (lines 112-119).
    src = tmp_path / 'crash.jpg'
    src.write_bytes(b'image' + b'video')
    target = tmp_path / 'crash.mp4'
    real_open = builtins.open

    def _open_failing_on_write(file, mode='r', *args, **kwargs):
        # Mode is positional in motion_photo (open(path, 'wb')), so check args
        # too -- the previous version only inspected kwargs and never triggered
        # the cleanup branch.
        if 'w' in mode:
            f = real_open(file, mode, *args, **kwargs)
            real_write = f.write

            def failing_write(data):
                real_write(b'X')  # create the file on disk so cleanup has work
                raise OSError('disk full after first byte')

            f.write = failing_write
            return f
        return real_open(file, mode, *args, **kwargs)

    with patch('builtins.open', side_effect=_open_failing_on_write):
        result = extract_video(str(src), offset=5, video_path=str(target))
    assert result is None
    assert not target.exists()
