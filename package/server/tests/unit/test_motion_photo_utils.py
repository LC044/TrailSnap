"""Tests for Motion Photo detection and embedded video extraction."""
import pytest
from app.utils.motion_photo import extract_video, get_video_offset

pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]

def test_get_video_offset_reads_xmp_attribute(tmp_path):
    path = tmp_path / "motion.jpg"
    path.write_bytes(b'<xmp GCamera:MicroVideoOffset="12">image-data')
    assert get_video_offset(str(path)) == 12

def test_get_video_offset_finds_valid_embedded_ftyp_atom(tmp_path):
    prefix = b"jpeg-prefix"
    atom = (24).to_bytes(4, "big") + b"ftyp" + b"isom" + (b"x" * 12)
    path = tmp_path / "motion.jpg"
    path.write_bytes(prefix + atom)
    assert get_video_offset(str(path)) == len(atom)

def test_extract_video_writes_tail_and_rejects_invalid_offset(tmp_path):
    path = tmp_path / "motion.jpg"
    path.write_bytes(b"jpeg" + b"video-tail")
    target = tmp_path / "clip.mp4"
    assert extract_video(str(path), offset=10, video_path=str(target)) == str(target)
    assert target.read_bytes() == b"video-tail"
    assert extract_video(str(path), offset=path.stat().st_size) is None
