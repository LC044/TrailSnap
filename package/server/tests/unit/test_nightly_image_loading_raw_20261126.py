"""Nightly watch 2026-11-26 · app/utils/image_loading.py 的 RAW 分支盲区。

定向覆盖显示 ``app/utils/image_loading.py`` 只有 65% 覆盖：既有测试
（``test_raw_images.py`` / ``test_large_images.py``）只覆盖了普通图片路径，
``open_image`` 里的相机 RAW 适配分支（嵌入缩略图 / 无缩略图回退 / EXIF 复用 /
方向标记 / 时间戳回填）从未被触达。

本文件用**假的 rawpy 模块**（``sys.modules`` 注入）驱动这些分支，
因此不依赖真实的 RAW 样本文件，CI 容器里也能跑。
"""

import io
import sys
from datetime import datetime
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from app.utils import image_loading


def jpeg_bytes(size=(64, 48)):
    buffer = io.BytesIO()
    Image.new("RGB", size, (10, 20, 30)).save(buffer, format="JPEG")
    return buffer.getvalue()


class FakeSizes:
    width = 4000
    height = 3000
    flip = 6


class FakeRawPy:
    """最小可用的 rawpy 替身，只实现 open_image 真正用到的那几个方法。"""

    def __init__(self, *, thumb=None, other=None, sizes=None, postprocess=None):
        self._thumb = thumb
        self._other = other
        self._sizes = sizes or FakeSizes()
        self._postprocess = postprocess
        self.opened = None
        self.unpacked = False

    # 上下文管理器
    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def open_file(self, path):
        self.opened = ("file", path)

    def open_buffer(self, buffer):
        self.opened = ("buffer", buffer)

    @property
    def sizes(self):
        return self._sizes

    @property
    def other(self):
        return self._other

    def extract_thumb(self):
        if isinstance(self._thumb, Exception):
            raise self._thumb
        return self._thumb

    def unpack(self):
        self.unpacked = True

    def postprocess(self, **_kwargs):
        if self._postprocess is not None:
            return self._postprocess
        return np.zeros((FakeSizes.height, FakeSizes.width, 3), dtype=np.uint8)


class LibRawNoThumbnailError(Exception):
    """与 fake rawpy 模块里的异常类保持同一个类型，才能被 open_image 捕获。"""


class LibRawUnsupportedThumbnailError(Exception):
    pass


class FakeThumbFormat:
    JPEG = "jpeg"
    BITMAP = "bitmap"


class FakeColorSpace:
    sRGB = "srgb"


def install_fake_rawpy(monkeypatch, factory):
    module = SimpleNamespace(
        RawPy=factory,
        ThumbFormat=FakeThumbFormat,
        ColorSpace=FakeColorSpace,
        LibRawNoThumbnailError=LibRawNoThumbnailError,
        LibRawUnsupportedThumbnailError=LibRawUnsupportedThumbnailError,
    )
    monkeypatch.setitem(sys.modules, "rawpy", module)


def embedded_thumb():
    return SimpleNamespace(format=FakeThumbFormat.JPEG, data=jpeg_bytes((32, 24)))


def test_raw_path_uses_the_embedded_thumbnail(monkeypatch):
    instance = FakeRawPy(thumb=embedded_thumb())
    install_fake_rawpy(monkeypatch, lambda: instance)

    image = image_loading.open_image("/photos/a.nef")

    assert instance.opened[0] == "file"
    assert image.size == (32, 24)
    assert image.info["raw_original_size"] == (4000, 3000)
    assert image.info["raw_preview_source"] == "embedded"
    # LibRaw flip=6 → EXIF orientation 6（保持像素不旋转）
    assert image.getexif().get(274) == 6


def test_raw_buffer_source_seeks_before_opening(monkeypatch):
    instance = FakeRawPy(thumb=embedded_thumb())
    install_fake_rawpy(monkeypatch, lambda: instance)
    stream = io.BytesIO(jpeg_bytes())

    image = image_loading.open_image(stream, filename="a.arw")

    assert instance.opened[0] == "buffer"
    assert image.info["raw_preview_source"] == "embedded"


def test_raw_without_thumbnail_falls_back_to_a_full_decode(monkeypatch):
    instance = FakeRawPy(thumb=LibRawNoThumbnailError("no thumbnail"))
    install_fake_rawpy(monkeypatch, lambda: instance)

    image = image_loading.open_image("/photos/a.nef")

    assert instance.unpacked is True
    assert image.info["raw_preview_source"] == "decoded"
    assert image.size == (4000, 3000)


def test_full_resolution_rebuilds_the_image_when_the_thumbnail_is_smaller(monkeypatch):
    instance = FakeRawPy(thumb=embedded_thumb())
    install_fake_rawpy(monkeypatch, lambda: instance)

    image = image_loading.open_image("/photos/a.nef", full_resolution=True)

    assert instance.unpacked is True
    assert image.info["raw_preview_source"] == "decoded"
    assert image.size == (4000, 3000)


def test_raw_above_the_pixel_limit_is_rejected(monkeypatch):
    sizes = SimpleNamespace(width=100000, height=100000, flip=0)
    instance = FakeRawPy(thumb=embedded_thumb(), sizes=sizes)
    install_fake_rawpy(monkeypatch, lambda: instance)

    with pytest.raises(Image.DecompressionBombError):
        image_loading.open_image("/photos/a.nef")


def test_raw_reuses_the_exif_header_and_fills_the_missing_fields(monkeypatch):
    exif = Image.Exif()
    exif[271] = "TrailSnap"
    buffer = io.BytesIO()
    Image.new("RGB", (64, 48), (1, 2, 3)).save(buffer, format="JPEG", exif=exif)
    stream = io.BytesIO(buffer.getvalue())
    other = SimpleNamespace(
        timestamp=datetime(2024, 5, 6, 7, 8, 9),
        iso_speed=400, shutter_speed=0.008, aperture=2.8, focal_length=35,
    )
    instance = FakeRawPy(thumb=embedded_thumb(), other=other)
    install_fake_rawpy(monkeypatch, lambda: instance)

    image = image_loading.open_image(stream, filename="a.nef")

    assert "exif" in image.info
    parsed = image.getexif()
    assert parsed.get(306) == "2024:05:06 07:08:09"
    photo_ifd = parsed.get(34665) or {}
    assert photo_ifd.get(36867) == "2024:05:06 07:08:09"
    assert photo_ifd.get(34855) == 400
    assert photo_ifd.get(33434) == 0.008
    assert photo_ifd.get(33437) == 2.8
    assert photo_ifd.get(37386) == 35


def test_non_raw_extensions_skip_the_raw_decoder(monkeypatch):
    def explode():
        raise AssertionError("rawpy must not be used for ordinary images")

    install_fake_rawpy(monkeypatch, explode)

    image = image_loading.open_image(io.BytesIO(jpeg_bytes()), filename="a.jpg")

    assert image.size == (64, 48)


