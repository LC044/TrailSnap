"""Unit coverage for app.utils.gps_writeback（GPS 写回原文件，REQ-223）。

所有用例都用代码构造 ISO BMFF box 字节流 / Pillow 图片，不依赖样本文件，
可在 CI / 无媒体资源环境下稳定运行。覆盖：

* 图片: JPEG/WebP/TIFF 写入后读回一致（含负纬度、既有 EXIF 保留）；
  HEIC / 缺文件 → WriteBackUnsupported。
* 视频: moov 尾部（直录）与 faststart（moov 在 mdat 前）两种布局注入后
  读回一致；faststart 的 stco/co64 按 delta 修正；二次写回原位替换不膨胀。
* 安全: 校验失败保持原文件字节不变、无临时文件残留。
* md5: update_photo_md5 重算并更新 photo.md5 / size。
* 分派: write_gps_to_file 按扩展名路由；不支持的格式抛 WriteBackUnsupported。
"""

from __future__ import annotations

import hashlib
import os
import struct
import tempfile
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


# --------------------------------------------------------------------------- #
# 构造辅助（与 test_video_meta.py 同一风格）
# --------------------------------------------------------------------------- #

def box(box_type: bytes, payload: bytes = b'') -> bytes:
    return struct.pack('>I', len(payload) + 8) + box_type + payload


def udta_text(atom_type: bytes, text: str) -> bytes:
    raw = text.encode('utf-8')
    return box(atom_type, struct.pack('>HH', len(raw), 0) + raw)


def make_image(tmp_path, name: str, fmt: str = 'JPEG', exif: bytes | None = None):
    from PIL import Image
    path = tmp_path / name
    img = Image.new('RGB', (8, 8), 'red')
    kwargs = {'exif': exif} if exif is not None else {}
    img.save(path, format=fmt, **kwargs)
    return str(path)


def read_image_gps(path: str):
    from PIL import Image
    from app.utils.exif import get_exif_data, get_gps_info
    with Image.open(path) as img:
        exif = get_exif_data(img)
    return get_gps_info(exif) if exif else None


def moov_box(*children: bytes) -> bytes:
    return box(b'moov', b''.join(children))


def mvhd() -> bytes:
    return box(b'mvhd', b'\x00' * 100)


def video_file(tmp_path, name: str, *, faststart: bool = False,
               offset_box: bytes | None = None, extra_moov: bytes = b'') -> str:
    """构造最小 MP4。

    faststart=True 时 moov 在 mdat 之前（流媒体优化布局），含 stco/co64
    表项指向 mdat 内偏移；否则 moov 在文件尾部（手机直录常见布局）。
    """
    ftyp = box(b'ftyp', b'isom' + b'\x00' * 8)
    mdat = box(b'mdat', b'X' * 64)
    if offset_box is None:
        trak_children = offset_box
        moov = moov_box(mvhd(), extra_moov) if extra_moov else moov_box(mvhd())
    if offset_box is not None:
        stbl = box(b'stbl', offset_box)
        minf = box(b'minf', stbl)
        mdia = box(b'mdia', minf)
        trak = box(b'trak', mdia)
        moov = moov_box(mvhd(), trak, extra_moov) if extra_moov else moov_box(mvhd(), trak)
    path = tmp_path / name
    if faststart:
        path.write_bytes(ftyp + moov + mdat)
    else:
        path.write_bytes(ftyp + mdat + moov)
    return str(path)


def stco_with(entries: list[int]) -> bytes:
    payload = struct.pack('>II', 0, len(entries)) + b''.join(
        struct.pack('>I', e) for e in entries)
    return box(b'stco', payload)


def co64_with(entries: list[int]) -> bytes:
    payload = struct.pack('>II', 0, len(entries)) + b''.join(
        struct.pack('>Q', e) for e in entries)
    return box(b'co64', payload)


# --------------------------------------------------------------------------- #
# 图片写回
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize('filename,fmt', [
    ('a.jpg', 'JPEG'), ('a.webp', 'WEBP'), ('a.tiff', 'TIFF'),
])
def test_write_image_gps_roundtrip_all_supported_formats(tmp_path, filename, fmt):
    from app.utils.gps_writeback import write_image_gps

    path = make_image(tmp_path, filename, fmt=fmt)
    write_image_gps(path, 30.5928, 114.3055)

    gps = read_image_gps(path)
    assert gps is not None
    assert gps['latitude'] == pytest.approx(30.5928, abs=1e-4)
    assert gps['longitude'] == pytest.approx(114.3055, abs=1e-4)


def test_write_image_gps_handles_southwest_hemispheres(tmp_path):
    from app.utils.gps_writeback import write_image_gps

    path = make_image(tmp_path, 'sw.jpg')
    write_image_gps(path, -33.8688, -70.6693)

    gps = read_image_gps(path)
    assert gps['latitude'] == pytest.approx(-33.8688, abs=1e-4)
    assert gps['longitude'] == pytest.approx(-70.6693, abs=1e-4)


def test_write_image_gps_preserves_existing_exif_fields(tmp_path):
    import piexif
    from app.utils.gps_writeback import write_image_gps

    exif = piexif.dump({'0th': {piexif.ImageIFD.Make: b'Canon',
                                piexif.ImageIFD.Model: b'EOS R5'}})
    path = make_image(tmp_path, 'cam.jpg', exif=exif)
    write_image_gps(path, 35.6762, 139.6503)

    from PIL import Image
    from app.utils.exif import get_exif_data
    with Image.open(path) as img:
        ex = get_exif_data(img)
    assert ex.get('Make') == 'Canon'
    assert ex.get('Model') == 'EOS R5'


def test_write_image_gps_skips_heic_and_missing_files(tmp_path):
    from app.utils.gps_writeback import WriteBackUnsupported, write_image_gps

    heic = tmp_path / 'a.heic'
    heic.write_bytes(b'ftypheic-not-really-supported')
    with pytest.raises(WriteBackUnsupported):
        write_image_gps(str(heic), 1.0, 2.0)

    with pytest.raises(WriteBackUnsupported):
        write_image_gps(str(tmp_path / 'ghost.jpg'), 1.0, 2.0)


def test_write_image_gps_failure_keeps_original_bytes(tmp_path):
    from app.utils.gps_writeback import write_image_gps

    path = make_image(tmp_path, 'orig.jpg')
    original = open(path, 'rb').read()
    with patch('app.utils.gps_writeback._verify_image_gps',
               side_effect=ValueError('boom')):
        with pytest.raises(RuntimeError):
            write_image_gps(path, 10.0, 20.0)

    assert open(path, 'rb').read() == original
    # 临时文件必须清理干净
    leftovers = [f for f in os.listdir(tmp_path) if 'gps' in f]
    assert leftovers == []


def test_write_image_gps_replaces_twice_without_bloating(tmp_path):
    from app.utils.gps_writeback import write_image_gps

    path = make_image(tmp_path, 'twice.jpg')
    write_image_gps(path, 10.0, 20.0)
    size_once = os.path.getsize(path)
    write_image_gps(path, 30.0, 120.0)

    assert os.path.getsize(path) == size_once
    gps = read_image_gps(path)
    assert gps['latitude'] == pytest.approx(30.0, abs=1e-4)


# --------------------------------------------------------------------------- #
# 视频写回
# --------------------------------------------------------------------------- #

def test_write_video_gps_tail_moov_layout(tmp_path):
    from app.utils import video_meta
    from app.utils.gps_writeback import write_video_gps

    # 手机直录常见布局：ftyp + mdat + moov（moov 在最后）
    path = video_file(tmp_path, 'recording.mp4', faststart=False)
    original_duration = video_meta.extract_video_metadata(path).get('duration')

    write_video_gps(path, 30.5928, 114.3055)

    result = video_meta.extract_video_metadata(path)
    assert result['location'] == {
        'latitude': pytest.approx(30.5928, abs=1e-4),
        'longitude': pytest.approx(114.3055, abs=1e-4)}
    # mvhd 无 duration 时原值就是 None；结构完整即可
    assert result.get('duration') == original_duration


def test_write_video_gps_faststart_patches_stco_offsets(tmp_path):
    import io
    from app.utils import video_meta
    from app.utils.gps_writeback import write_video_gps

    # faststart：moov 在 mdat 之前，stco 表项指向 mdat 内偏移
    path = video_file(tmp_path, 'fast.mp4', faststart=True,
                      offset_box=stco_with([200, 260]))
    original_size = os.path.getsize(path)

    write_video_gps(path, 30.5928, 114.3055)

    delta = os.path.getsize(path) - original_size
    assert delta > 0  # 注入了 udta + meta

    # 位置读回
    result = video_meta.extract_video_metadata(path)
    assert result['location']['latitude'] == pytest.approx(30.5928, abs=1e-4)

    # stco 表项必须 +delta（mdat 整体后移）
    data = open(path, 'rb').read()
    f = io.BytesIO(data)
    stco = video_meta._find_box(
        f, 0, len(data), (b'moov', b'trak', b'mdia', b'minf', b'stbl', b'stco'))
    assert stco is not None
    f.seek(stco[0])
    payload = f.read(stco[1] - stco[0])
    count = int.from_bytes(payload[4:8], 'big')
    entries = [int.from_bytes(payload[8 + i * 4:12 + i * 4], 'big')
               for i in range(count)]
    assert entries == [200 + delta, 260 + delta]


def test_write_video_gps_faststart_patches_co64_offsets(tmp_path):
    import io
    from app.utils import video_meta
    from app.utils.gps_writeback import write_video_gps

    path = video_file(tmp_path, 'fast64.mp4', faststart=True,
                      offset_box=co64_with([200, 260]))
    original_size = os.path.getsize(path)

    write_video_gps(path, 30.5928, 114.3055)
    delta = os.path.getsize(path) - original_size

    data = open(path, 'rb').read()
    f = io.BytesIO(data)
    co64 = video_meta._find_box(
        f, 0, len(data), (b'moov', b'trak', b'mdia', b'minf', b'stbl', b'co64'))
    f.seek(co64[0])
    payload = f.read(co64[1] - co64[0])
    count = int.from_bytes(payload[4:8], 'big')
    entries = [int.from_bytes(payload[8 + i * 8:16 + i * 8], 'big')
               for i in range(count)]
    assert entries == [200 + delta, 260 + delta]


def test_write_video_gps_replaces_existing_xyz_in_place(tmp_path):
    from app.utils import video_meta
    from app.utils.gps_writeback import write_video_gps

    # 已有 ©xyz：原位替换。等长坐标（±dd.dddddd±ddd.dddddd 格式固定 24 字符）
    # 反复写回文件大小不变——验证替换而非追加。
    existing_udta = box(b'udta', udta_text(b'\xa9xyz', '+10.000000+020.000000+000.0/'))
    path = video_file(tmp_path, 'existing.mp4', extra_moov=existing_udta)

    write_video_gps(path, 55.755800, 137.617300)
    size_once = os.path.getsize(path)
    result = video_meta.extract_video_metadata(path)
    assert result['location']['latitude'] == pytest.approx(55.7558, abs=1e-4)

    # 等长的负半球坐标：大小必须不变
    write_video_gps(path, -33.868800, 151.209300)
    assert os.path.getsize(path) == size_once
    result = video_meta.extract_video_metadata(path)
    assert result['location'] == {
        'latitude': pytest.approx(-33.8688, abs=1e-4),
        'longitude': pytest.approx(151.2093, abs=1e-4)}


def test_write_video_gps_preserves_track_metadata(tmp_path):
    from app.utils import video_meta
    from app.utils.gps_writeback import write_video_gps

    # 带真实 trak 结构：尺寸 / 时长 / codec / fps 必须原样保留
    def tkhd(w, h):
        payload = b'\x00' * 4 + b'\x00' * 20 + b'\x00' * 8 + struct.pack('>hhhh', 0, 0, 0, 0)
        identity = (struct.pack('>i', 1 << 16) + struct.pack('>i', 0) + struct.pack('>i', 0)
                    + struct.pack('>i', 0) + struct.pack('>i', 1 << 16) + struct.pack('>i', 0)
                    + struct.pack('>i', 0) + struct.pack('>i', 0) + struct.pack('>i', 1 << 30))
        payload += identity + struct.pack('>i', w << 16) + struct.pack('>i', h << 16)
        return box(b'tkhd', payload)

    def mdhd(timescale, duration):
        return box(b'mdhd', b'\x00' * 4 + b'\x00' * 8 + struct.pack('>I', timescale)
                   + struct.pack('>I', duration) + b'\x00' * 4)

    hdlr = box(b'hdlr', b'\x00' * 8 + b'vide' + b'\x00' * 12)
    stsd = box(b'stsd', b'\x00\x00\x00\x00' + struct.pack('>I', 1)
               + struct.pack('>I', 16) + b'avc1' + b'\x00' * 8)
    stsz = box(b'stsz', b'\x00\x00\x00\x00' + struct.pack('>I', 0) + struct.pack('>I', 300))
    stbl = box(b'stbl', stsd + stsz)
    mdia = box(b'mdia', mdhd(600, 6000) + hdlr + box(b'minf', stbl))
    trak = box(b'trak', tkhd(1920, 1080) + mdia)
    moov = moov_box(mvhd(), trak)

    ftyp = box(b'ftyp', b'isom' + b'\x00' * 8)
    mdat = box(b'mdat', b'X' * 64)
    path = tmp_path / 'track.mp4'
    path.write_bytes(ftyp + mdat + moov)

    before = video_meta.extract_video_metadata(str(path))
    write_video_gps(str(path), 30.5928, 114.3055)
    after = video_meta.extract_video_metadata(str(path))

    assert after['location']['latitude'] == pytest.approx(30.5928, abs=1e-4)
    for key in ('duration', 'width', 'height', 'fps', 'codec'):
        assert after.get(key) == before.get(key), f"{key} lost after write-back"


def test_write_video_gps_skips_avi_and_missing_files(tmp_path):
    from app.utils.gps_writeback import WriteBackUnsupported, write_video_gps

    avi = tmp_path / 'clip.avi'
    avi.write_bytes(b'RIFF' + b'\x00' * 64)
    with pytest.raises(WriteBackUnsupported):
        write_video_gps(str(avi), 1.0, 2.0)
    with pytest.raises(WriteBackUnsupported):
        write_video_gps(str(tmp_path / 'ghost.mp4'), 1.0, 2.0)


def test_write_video_gps_failure_keeps_original_and_cleans_temp(tmp_path):
    from app.utils.gps_writeback import write_video_gps

    path = video_file(tmp_path, 'fail.mp4')
    original = open(path, 'rb').read()
    with patch('app.utils.gps_writeback._verify_video_gps',
               side_effect=ValueError('boom')):
        with pytest.raises(RuntimeError):
            write_video_gps(path, 1.0, 2.0)

    assert open(path, 'rb').read() == original
    leftovers = [f for f in os.listdir(tmp_path) if 'gps' in f]
    assert leftovers == []


def test_write_video_gps_rejects_invalid_coordinates(tmp_path):
    from app.utils.gps_writeback import write_video_gps

    path = video_file(tmp_path, 'invalid.mp4')
    # 坐标校验直接抛 ValueError（crud 层统一按 failed 计数并吞掉）
    with pytest.raises(ValueError):
        write_video_gps(path, 200.0, 999.0)


# --------------------------------------------------------------------------- #
# 统一入口 / md5 联动
# --------------------------------------------------------------------------- #

def test_write_gps_to_file_dispatches_by_extension(tmp_path):
    from app.utils.gps_writeback import WriteBackUnsupported, write_gps_to_file

    path = make_image(tmp_path, 'd.jpg')
    with patch('app.utils.gps_writeback.write_image_gps') as img_write:
        write_gps_to_file(path, 1.0, 2.0)
    img_write.assert_called_once_with(path, 1.0, 2.0)

    vpath = video_file(tmp_path, 'd.mp4')
    with patch('app.utils.gps_writeback.write_video_gps') as vid_write:
        write_gps_to_file(vpath, 1.0, 2.0)
    vid_write.assert_called_once_with(vpath, 1.0, 2.0)

    other = tmp_path / 'doc.pdf'
    other.write_bytes(b'%PDF')
    with pytest.raises(WriteBackUnsupported):
        write_gps_to_file(str(other), 1.0, 2.0)


def test_update_photo_md5_recalculates_after_write(tmp_path):
    from app.utils.gps_writeback import update_photo_md5, write_image_gps

    path = make_image(tmp_path, 'md5.jpg')
    original_md5 = hashlib.md5(open(path, 'rb').read()).hexdigest()
    photo = SimpleNamespace(id='p1', file_path=path, md5=original_md5, size=os.path.getsize(path))
    db = MagicMock()

    write_image_gps(path, 30.0, 120.0)
    result = update_photo_md5(db, photo)

    expected = hashlib.md5(open(path, 'rb').read()).hexdigest()
    assert result == expected
    assert photo.md5 == expected
    assert photo.md5 != original_md5
    assert photo.size == os.path.getsize(path)
    db.add.assert_called_once_with(photo)


def test_update_photo_md5_returns_none_for_missing_file(tmp_path):
    from app.utils.gps_writeback import update_photo_md5

    photo = SimpleNamespace(id='p1', file_path=str(tmp_path / 'ghost.jpg'))
    db = MagicMock()
    assert update_photo_md5(db, photo) is None
    db.add.assert_not_called()


def test_update_photo_md5_tolerates_unresolvable_path():
    from app.utils.gps_writeback import update_photo_md5

    # portable 模式下损坏引用的 photo.file_path 会抛 ValueError
    class BrokenPhoto:
        id = 'p1'
        @property
        def file_path(self):
            raise ValueError("Incomplete photo storage reference")

    db = MagicMock()
    assert update_photo_md5(db, BrokenPhoto()) is None
