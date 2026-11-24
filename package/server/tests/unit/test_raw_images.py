"""RAW loading shares the ordinary metadata and thumbnail image contract."""
import io
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest
from PIL import Image, ImageOps

from app.utils.image_loading import open_image, RAW_EXTENSIONS, IMAGE_EXTENSIONS
from app.utils.image_orientation import display_image_size

pytestmark = pytest.mark.smoke


def test_regular_image_keeps_lazy_pillow_contract():
    source = io.BytesIO()
    Image.new('RGB', (20, 10)).save(source, 'PNG')
    source.seek(0)
    with open_image(source, 'photo.png') as image:
        assert image.size == (20, 10)
        assert image.format == 'PNG'
    assert set(RAW_EXTENSIONS) <= set(IMAGE_EXTENSIONS)


@pytest.mark.parametrize('embedded', [True, False])
def test_raw_preview_and_decode_share_orientation_and_dimensions(embedded):
    import rawpy
    jpeg = io.BytesIO()
    Image.new('RGB', (30, 20), 'red').save(jpeg, 'JPEG')
    with patch.object(rawpy, 'RawPy') as factory:
        raw = factory.return_value.__enter__.return_value
        raw.sizes = SimpleNamespace(width=6000, height=4000, flip=6)
        if embedded:
            raw.extract_thumb.return_value = SimpleNamespace(format=rawpy.ThumbFormat.JPEG, data=jpeg.getvalue())
        else:
            raw.extract_thumb.side_effect = rawpy.LibRawNoThumbnailError()
            raw.postprocess.return_value = np.zeros((20, 30, 3), dtype=np.uint8)
        with open_image(io.BytesIO(b'raw'), 'photo.RAF') as image:
            assert display_image_size(image) == (4000, 6000)
            assert ImageOps.exif_transpose(image).size == (20, 30)
            assert image.info['raw_preview_source'] == ('embedded' if embedded else 'decoded')
        assert raw.unpack.call_count == (0 if embedded else 1)


def test_real_raw_samples(tmp_path):
    directory = os.getenv('TS_TEST_RAW_DIR')
    if not directory:
        pytest.skip('Set TS_TEST_RAW_DIR to exercise private camera originals')
    from app.service.tasks.basic import process_basic_cpu_job
    from app.core.config_manager import ImageSettings
    from uuid import uuid4
    files = [p for p in Path(directory).iterdir() if p.suffix.lower() in RAW_EXTENSIONS]
    assert files
    for path in files:
        result = process_basic_cpu_job(str(path), uuid4(), str(tmp_path), str(uuid4()), ImageSettings())
        assert result['success'], result
        assert result['width'] > 0 and result['height'] > 0
        assert result['meta']['photo_time']
        with Image.open(result['thumb_path']) as image:
            assert image.format == 'WEBP'


@pytest.mark.parametrize('extension', ['RAF', 'NEF'])
def test_real_raw_high_resolution_cache(tmp_path, extension):
    directory = os.getenv('TS_TEST_RAW_DIR')
    if not directory:
        pytest.skip('Set TS_TEST_RAW_DIR for real RAW decoding')
    from app.service import storage
    from uuid import uuid4
    import hashlib
    path = next(Path(directory).glob('*.' + extension))
    original_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    owner, photo = uuid4(), uuid4()
    storage.update_storage_root_cache(str(owner), str(tmp_path))
    result = storage.get_raw_high_resolution_path(owner, photo, str(path))
    with open_image(path, full_resolution=True) as decoded:
        expected = ImageOps.exif_transpose(decoded).size
        assert decoded.info['raw_preview_source'] == 'decoded'
        assert decoded.getexif().get(272)  # Camera model survives full decoding.
    with Image.open(result) as high:
        assert high.size == expected
        assert high.getexif().get(274, 1) == 1
    with patch('app.service.storage.open_image', side_effect=AssertionError('cache miss')):
        assert storage.get_raw_high_resolution_path(owner, photo, str(path)) == result
    assert hashlib.sha256(path.read_bytes()).hexdigest() == original_hash
    storage.delete_thumbnails(owner, photo)
    assert not Path(result).exists()


def test_raw_high_resolution_failure_leaves_no_cache(tmp_path):
    from app.service import storage
    from uuid import uuid4
    owner, photo = uuid4(), uuid4()
    storage.update_storage_root_cache(str(owner), str(tmp_path))
    original = tmp_path / 'broken.RAF'
    original.write_bytes(b'broken RAW')
    with pytest.raises(Exception):
        storage.get_raw_high_resolution_path(owner, photo, str(original))
    assert not list(tmp_path.rglob('*.tmp'))
    assert not list(tmp_path.rglob('*-raw-high-*.jpg'))


@pytest.mark.asyncio
async def test_raw_file_route_distinguishes_high_view_and_download(tmp_path):
    from unittest.mock import MagicMock
    from app.api.media import get_media_file
    from uuid import uuid4
    from fastapi import HTTPException
    original = tmp_path / 'camera.RAF'
    original.write_bytes(b'original RAW')
    high = tmp_path / 'high.jpg'
    Image.new('RGB', (60, 40)).save(high)
    photo = SimpleNamespace(id=uuid4(), owner_id=uuid4(), file_path=str(original))
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = photo
    with patch('app.api.media.storage.get_raw_high_resolution_path', return_value=str(high)) as generate:
        response = await get_media_file(photo.id, None, range=None, original=False, db=db)
        assert response.path == str(high)
        assert response.media_type == 'image/jpeg'
        generate.assert_called_once()
        generate.reset_mock()
        response = await get_media_file(photo.id, None, range=None, original=True, db=db)
        assert response.path == str(original)
        assert response.media_type == 'application/octet-stream'
        generate.assert_not_called()
    with patch('app.api.media.storage.get_raw_high_resolution_path', side_effect=ValueError('broken')):
        with pytest.raises(HTTPException) as failure:
            await get_media_file(photo.id, None, range=None, original=False, db=db)
        assert failure.value.status_code == 422


def test_raw_high_cache_invalidates_when_source_changes(tmp_path):
    from app.service import storage
    from uuid import uuid4
    owner, photo = uuid4(), uuid4()
    storage.update_storage_root_cache(str(owner), str(tmp_path))
    original = tmp_path / 'source.RAF'
    original.write_bytes(b'v1')
    with patch('app.service.storage.open_image', side_effect=lambda *a, **kw: Image.new('RGB', (80, 60))) as decode:
        first = storage.get_raw_high_resolution_path(owner, photo, str(original))
        original.write_bytes(b'version two')
        second = storage.get_raw_high_resolution_path(owner, photo, str(original))
        assert first != second
        assert decode.call_count == 2
    assert Image.open(second).size == (80, 60)


def test_raw_high_encoding_failure_cleans_temporary_file(tmp_path):
    from app.service import storage
    from uuid import uuid4
    owner, photo = uuid4(), uuid4()
    storage.update_storage_root_cache(str(owner), str(tmp_path))
    original = tmp_path / 'source.RAF'
    original.write_bytes(b'original')
    with patch('app.service.storage.open_image', side_effect=lambda *a, **kw: Image.new('RGB', (80, 60))):
        with patch.object(Image.Image, 'save', side_effect=OSError('disk full')):
            with pytest.raises(OSError, match='disk full'):
                storage.get_raw_high_resolution_path(owner, photo, str(original))
    assert not list(tmp_path.rglob('*.tmp'))
    assert not list(tmp_path.rglob('*-raw-high-*.jpg'))


def test_linux_sidecar_collects_rawpy_sibling_libraries(tmp_path):
    import ast
    import sys
    package = tmp_path / 'rawpy'
    package.mkdir()
    libs = tmp_path / 'rawpy.libs'
    libs.mkdir()
    dependency = libs / 'liblcms2-ff8c4a65.so.2.0.10'
    dependency.write_bytes(b'ELF fixture')
    spec_path = Path(__file__).resolve().parents[2] / 'desktop_server.spec'
    tree = ast.parse(spec_path.read_text(encoding='utf-8'))
    block = next(node for node in tree.body if isinstance(node, ast.If)
                 and "sys.platform.startswith('linux')" in ast.unparse(node.test))
    namespace = {'sys': SimpleNamespace(platform='linux'), 'Path': Path, 'binaries': []}
    with patch('importlib.util.find_spec', return_value=SimpleNamespace(origin=str(package / '__init__.py'))):
        exec(compile(ast.Module(body=[block], type_ignores=[]), str(spec_path), 'exec'), namespace)
    assert namespace['binaries'] == [(str(dependency), '.')]


def test_linux_workflow_repairs_flattened_raw_library_rpath():
    workflow = Path(__file__).resolve().parents[4] / '.github/workflows/build-desktop.yml'
    source = workflow.read_text(encoding='utf-8')
    step = source.split('- name: Ensure sidecar .libs RPATHs include $ORIGIN (Linux only)', 1)[1].split('- name:', 1)[0]
    assert "-type f -name '*.so*' -print0" in step
    assert "-type d -name '*.libs'" not in step
    assert 'patchelf --set-rpath' in step
    assert "-name 'libraw_r.so*'" in step
    assert "grep -q 'not found'" in step
