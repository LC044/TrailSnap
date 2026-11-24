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
