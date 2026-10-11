"""High-resolution JPEG headers and thumbnail decoding regression coverage."""

from datetime import datetime
from uuid import uuid4

import pytest

from app.core.config_manager import ImageSettings
from app.service import storage
from app.utils.exif import extract_metadata
from app.utils.image_loading import Image

pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


def jpeg_header(tmp_path, width, height):
    """Change only SOF dimensions: test lazy opening without allocating 200 MP."""
    path = tmp_path / 'camera.jpg'
    exif = Image.Exif()
    exif[274] = 6
    exif[306] = '2026:10:07 15:29:30'
    Image.new('RGB', (32, 24)).save(path, exif=exif)
    data = bytearray(path.read_bytes())
    sof = data.index(b'\xff\xc0')
    data[sof + 5:sof + 7] = height.to_bytes(2, 'big')
    data[sof + 7:sof + 9] = width.to_bytes(2, 'big')
    path.write_bytes(data)
    return path


def test_200mp_metadata_and_dimensions(tmp_path):
    path = jpeg_header(tmp_path, 16384, 12240)
    with Image.open(path) as image:
        assert image.width * image.height == 200_540_160
        assert image._im is None  # Opening/metadata must not decode full pixels.
    result = extract_metadata(str(path), 'IMG_20261007_152930.jpg', extract_location_details=False)
    assert (result['width'], result['height']) == (12240, 16384)
    assert result['exif_info']['Orientation'] == 6
    assert result['exif_info']['DateTime'] == '2026:10:07 15:29:30'
    assert result['photo_time'] == datetime(2026, 10, 7, 15, 29, 30)
    assert storage.get_image_dimensions(str(path)) == (12240, 16384, None)


def test_extreme_image_still_rejected(tmp_path):
    path = jpeg_header(tmp_path, 30000, 20000)
    with pytest.raises(Image.DecompressionBombError):
        Image.open(path)


def test_large_image_warning_retained(tmp_path):
    path = jpeg_header(tmp_path, 20000, 15000)
    with pytest.warns(Image.DecompressionBombWarning), Image.open(path):
        pass


@pytest.mark.parametrize('extension,format', [('heic', 'HEIF'), ('heif', 'HEIF'), ('tif', 'TIFF'), ('gif', 'GIF')])
def test_supported_image_formats_keep_original_bytes(tmp_path, monkeypatch, extension, format):
    path = tmp_path / f'photo.{extension}'
    Image.new('RGB', (64, 48), 'blue').save(path, format=format)
    original = path.read_bytes()
    monkeypatch.setattr(storage, '_get_storage_root', lambda *args: str(tmp_path / 'output'))
    preview = storage.generate_thumbnail(uuid4(), str(path), uuid4(), config=ImageSettings())
    assert preview is not None
    assert storage.get_image_dimensions(str(path)) == (64, 48, None)
    metadata = extract_metadata(str(path), path.name, extract_location_details=False)
    assert (metadata['width'], metadata['height']) == (64, 48)
    assert path.read_bytes() == original


@pytest.mark.parametrize('shared', [False, True])
def test_jpeg_draft_preserves_original_metadata(tmp_path, monkeypatch, shared):
    path = tmp_path / 'camera.jpg'
    exif = Image.Exif()
    exif[274] = 6
    Image.new('RGB', (800, 600), 'red').save(path, exif=exif)
    monkeypatch.setattr(storage, 'LARGE_IMAGE_PIXELS', 1)
    monkeypatch.setattr(storage, '_get_storage_root', lambda *args: str(tmp_path / 'output'))
    sizes = []
    transpose = storage.ImageOps.exif_transpose

    def capture_transpose(image):
        sizes.append(image.size)
        return transpose(image)

    monkeypatch.setattr(storage.ImageOps, 'exif_transpose', capture_transpose)
    with Image.open(path) as original:
        preview = storage.generate_thumbnail(
            uuid4(), str(path), uuid4(), image_obj=original if shared else None,
            config=ImageSettings(preview_size=100, thumbnail_size=50),
        )
        assert preview is not None
        assert sizes[0][0] < 800 and sizes[0][1] < 600
        assert original.size == (800, 600)
        assert original.getexif()[274] == 6
        assert original._im is None
        metadata = extract_metadata(str(path), path.name, image_obj=original, extract_location_details=False)
        assert (metadata['width'], metadata['height']) == (600, 800)
    with Image.open(preview) as image:
        assert image.size == (75, 100)
    with Image.open(preview.replace('.webp', '-thumb.webp')) as image:
        assert image.size == (37, 50)
