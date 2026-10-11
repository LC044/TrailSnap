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


@pytest.mark.parametrize('brand', [b'heic', b'heix', b'mif1', b'avif', b'avis'])
def test_auxiliary_image_is_not_a_motion_video(tmp_path, brand):
    # Reproduces IMG_20261008_184743.jpg: a JPEG followed by streamdata
    # and a HEIF image. The old detector extracted this as an MP4.
    atom = (28).to_bytes(4, 'big') + b'ftyp' + brand + bytes(4) + b'mif1heictmap'
    path = tmp_path / 'ordinary.jpg'
    path.write_bytes(b'jpeg\xff\xd9streamdata' + atom + b'image-data')
    target = tmp_path / 'false-video.mp4'
    assert get_video_offset(str(path)) is None
    assert extract_video(str(path), video_path=str(target)) is None
    assert not target.exists()


def test_image_compatible_brand_overrides_generic_isom(tmp_path):
    atom = (20).to_bytes(4, 'big') + b'ftypisom' + bytes(4) + b'heic'
    path = tmp_path / 'ordinary.jpg'
    path.write_bytes(b'jpeg' + atom)
    assert get_video_offset(str(path)) is None


@pytest.mark.parametrize('brand', [b'isom', b'mp42', b'qt  ', b'3gp6'])
def test_motion_video_brands_are_preserved(tmp_path, brand):
    atom = (20).to_bytes(4, 'big') + b'ftyp' + brand + bytes(4) + brand
    path = tmp_path / 'motion.jpg'
    path.write_bytes(b'jpeg\xff\xd9' + atom)
    assert get_video_offset(str(path)) == len(atom)


def test_image_payload_does_not_hide_a_later_motion_clip(tmp_path):
    image = (20).to_bytes(4, 'big') + b'ftypheic' + bytes(4) + b'mif1'
    video = (20).to_bytes(4, 'big') + b'ftypisom' + bytes(4) + b'mp42'
    path = tmp_path / 'motion.jpg'
    path.write_bytes(b'jpeg' + image + video)
    assert get_video_offset(str(path)) == len(video)


def test_truncated_ftyp_is_rejected(tmp_path):
    path = tmp_path / 'truncated.jpg'
    path.write_bytes(b'jpeg' + (28).to_bytes(4, 'big') + b'ftypisom' + bytes(4))
    assert get_video_offset(str(path)) is None
