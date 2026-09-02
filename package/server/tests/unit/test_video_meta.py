"""Unit coverage for app.utils.video_meta (视频容器元数据解析).

所有用例都用代码构造 ISO BMFF (MP4/MOV) 的 box 字节流，不依赖任何样本文件，
因此可在 CI / 无媒体资源环境下稳定运行。覆盖：

* Happy path: moov/udta ©day 与 moov/meta(keys+ilst) 的时间、机型、GPS 提取。
* 优先级: CreateDate（带时区）优先于 mvhd 的 1904 UTC epoch。
* 轨道解析: tkhd 宽高、旋转矩阵 90° 时交换宽高、mdhd 时长、stsd codec、stsz 帧率。
* Edge: 非 ISO BMFF 扩展名 / 无 moov / 空文件 / 畸形 size 都返回结构完整的空结果。
* 集成: exif.extract_metadata 对视频走容器分支，并复用文件名 / mtime 回退链路。
"""

from __future__ import annotations

import struct
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest


pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


# --------------------------------------------------------------------------- #
# box 构造辅助
# --------------------------------------------------------------------------- #

def box(box_type: bytes, payload: bytes = b'') -> bytes:
    """构造一个 32 位 size 的 box。"""
    return struct.pack('>I', len(payload) + 8) + box_type + payload


def large_box(box_type: bytes, payload: bytes) -> bytes:
    """构造一个 64 位 largesize 的 box（size 字段写 1）。"""
    return struct.pack('>I', 1) + box_type + struct.pack('>Q', len(payload) + 16) + payload


def udta_text(box_type: bytes, text: str) -> bytes:
    """QuickTime user-data 文本 atom: [text_size(2)][language(2)][text]."""
    raw = text.encode('utf-8')
    return box(box_type, struct.pack('>HH', len(raw), 0) + raw)


def keys_box(names: list[str]) -> bytes:
    """moov/meta/keys —— 按序声明 metadata key 名称。"""
    entries = b''.join(box(b'mdta', name.encode('utf-8')) for name in names)
    return box(b'keys', struct.pack('>II', 0, len(names)) + entries)


def data_box(value, type_indicator: int = 1) -> bytes:
    """ilst 条目内的 data box。"""
    if type_indicator == 1:
        raw = value.encode('utf-8')
    elif type_indicator in (21, 22):
        raw = struct.pack('>i', value)
    elif type_indicator == 23:
        raw = struct.pack('>f', value)
    else:
        raw = value
    return box(b'data', struct.pack('>II', type_indicator, 0) + raw)


def ilst_indexed(items: list[tuple[int, bytes]]) -> bytes:
    """mdta 风格 ilst：条目头是指向 keys 表的 1-based 索引。"""
    entries = b''.join(struct.pack('>I', len(body) + 8) + struct.pack('>I', idx) + body
                       for idx, body in items)
    return box(b'ilst', entries)


def meta_box(names: list[str], values: list, full_box: bool = True) -> bytes:
    """moov/meta = [version/flags?] hdlr + keys + ilst。"""
    hdlr = box(b'hdlr', b'\x00' * 8 + b'mdta' + b'\x00' * 12)
    items = [(i + 1, data_box(v)) for i, v in enumerate(values)]
    payload = hdlr + keys_box(names) + ilst_indexed(items)
    if full_box:
        payload = b'\x00\x00\x00\x00' + payload
    return box(b'meta', payload)


def mvhd_box(creation_seconds: int, timescale: int = 1000, duration: int = 12345,
             version: int = 0) -> bytes:
    """moov/mvhd。creation_seconds 是 1904-01-01 UTC 起的秒数。"""
    if version == 1:
        payload = (bytes([1]) + b'\x00\x00\x00'
                   + struct.pack('>Q', creation_seconds)
                   + struct.pack('>Q', creation_seconds)
                   + struct.pack('>I', timescale)
                   + struct.pack('>Q', duration))
    else:
        payload = (b'\x00\x00\x00\x00'
                   + struct.pack('>I', creation_seconds)
                   + struct.pack('>I', creation_seconds)
                   + struct.pack('>I', timescale)
                   + struct.pack('>I', duration))
    payload += b'\x00' * 80
    return box(b'mvhd', payload)


def _identity_matrix() -> bytes:
    return (struct.pack('>i', 1 << 16) + struct.pack('>i', 0) + struct.pack('>i', 0)
            + struct.pack('>i', 0) + struct.pack('>i', 1 << 16) + struct.pack('>i', 0)
            + struct.pack('>i', 0) + struct.pack('>i', 0) + struct.pack('>i', 1 << 30))


def _rotate90_matrix() -> bytes:
    """顺时针 90°: a=0 b=1 c=-1 d=0。"""
    return (struct.pack('>i', 0) + struct.pack('>i', 1 << 16) + struct.pack('>i', 0)
            + struct.pack('>i', -(1 << 16)) + struct.pack('>i', 0) + struct.pack('>i', 0)
            + struct.pack('>i', 0) + struct.pack('>i', 0) + struct.pack('>i', 1 << 30))


def tkhd_box(width: int, height: int, matrix: bytes | None = None) -> bytes:
    """moov/trak/tkhd（version 0）。"""
    payload = b'\x00\x00\x00\x00'          # version + flags
    payload += b'\x00' * 20                # creation/modification/track_id/reserved/duration
    payload += b'\x00' * 8                 # reserved
    payload += struct.pack('>hhhh', 0, 0, 0, 0)  # layer/alt_group/volume/reserved
    payload += matrix if matrix is not None else _identity_matrix()
    payload += struct.pack('>i', width << 16) + struct.pack('>i', height << 16)
    return box(b'tkhd', payload)


def mdhd_box(timescale: int, duration: int) -> bytes:
    payload = (b'\x00\x00\x00\x00' + b'\x00' * 8
               + struct.pack('>I', timescale) + struct.pack('>I', duration)
               + b'\x00' * 4)
    return box(b'mdhd', payload)


def hdlr_box(handler: bytes) -> bytes:
    return box(b'hdlr', b'\x00' * 8 + handler + b'\x00' * 12)


def stsd_box(codec: bytes) -> bytes:
    """stsd: [version/flags(4)][entry_count(4)][entry_size(4)][codec(4)]..."""
    entry = struct.pack('>I', 16) + codec + b'\x00' * 8
    return box(b'stsd', b'\x00\x00\x00\x00' + struct.pack('>I', 1) + entry)


def stsz_box(sample_count: int) -> bytes:
    return box(b'stsz', b'\x00\x00\x00\x00' + struct.pack('>I', 0)
               + struct.pack('>I', sample_count))


def video_trak(width: int = 1920, height: int = 1080, timescale: int = 600,
               duration: int = 6000, codec: bytes = b'avc1', samples: int = 300,
               matrix: bytes | None = None, handler: bytes = b'vide') -> bytes:
    stbl = box(b'stbl', stsd_box(codec) + stsz_box(samples))
    minf = box(b'minf', stbl)
    mdia = box(b'mdia', mdhd_box(timescale, duration) + hdlr_box(handler) + minf)
    return box(b'trak', tkhd_box(width, height, matrix) + mdia)


def write_mp4(tmp_path, name: str, *moov_children: bytes) -> str:
    """写出一个最小可解析的 MP4：ftyp + moov + mdat。"""
    ftyp = box(b'ftyp', b'isom' + struct.pack('>I', 512) + b'isomiso2')
    moov = box(b'moov', b''.join(moov_children))
    mdat = box(b'mdat', b'\x00' * 64)
    path = tmp_path / name
    path.write_bytes(ftyp + moov + mdat)
    return str(path)


def qt_seconds(dt_utc: datetime) -> int:
    """UTC datetime -> 1904 epoch 秒数。"""
    epoch = datetime(1904, 1, 1, tzinfo=timezone.utc)
    return int((dt_utc - epoch).total_seconds())


# --------------------------------------------------------------------------- #
# 标量解析
# --------------------------------------------------------------------------- #

def test_parse_datetime_string_keeps_wall_clock_and_drops_tzinfo():
    from app.utils.video_meta import parse_datetime_string

    # 带 +08:00 偏移时应保留该偏移下的墙钟读数（与图片 EXIF 语义一致），
    # 不能再转成 UTC，否则视频在时间线上会整体前移 8 小时。
    assert parse_datetime_string('2024-05-01T18:30:00+08:00') == datetime(2024, 5, 1, 18, 30, 0)
    assert parse_datetime_string('2024-05-01T18:30:00Z') == datetime(2024, 5, 1, 18, 30, 0)
    assert parse_datetime_string('2024-05-01T18:30:00') == datetime(2024, 5, 1, 18, 30, 0)
    assert parse_datetime_string('2024-05-01 18:30:00') == datetime(2024, 5, 1, 18, 30, 0)
    assert parse_datetime_string('2024:05:01 18:30:00') == datetime(2024, 5, 1, 18, 30, 0)


def test_parse_datetime_string_rejects_garbage_and_out_of_range_years():
    from app.utils.video_meta import parse_datetime_string

    assert parse_datetime_string('not-a-date') is None
    assert parse_datetime_string('') is None
    assert parse_datetime_string(None) is None
    assert parse_datetime_string(12345) is None
    # 1904 是 QuickTime 的哨兵基准年，落在合理拍摄年份区间之外
    assert parse_datetime_string('1904-01-01T00:00:00') is None
    assert parse_datetime_string('2099-01-01T00:00:00') is None


def test_parse_iso6709_handles_both_hemispheres():
    from app.utils.video_meta import parse_iso6709

    assert parse_iso6709('+34.0522-118.2437+000.000/') == {
        "latitude": pytest.approx(34.0522), "longitude": pytest.approx(-118.2437)}
    assert parse_iso6709('-33.8688+151.2093/') == {
        "latitude": pytest.approx(-33.8688), "longitude": pytest.approx(151.2093)}
    # 无高度段也应可解析
    assert parse_iso6709('+30.5+114.3') == {
        "latitude": pytest.approx(30.5), "longitude": pytest.approx(114.3)}


def test_parse_iso6709_rejects_invalid_and_null_island():
    from app.utils.video_meta import parse_iso6709

    assert parse_iso6709('') is None
    assert parse_iso6709(None) is None
    assert parse_iso6709('34.05,-118.24') is None       # 缺符号前缀
    assert parse_iso6709('+00.0000+000.0000/') is None   # (0,0) 视为无效占位
    assert parse_iso6709('+99.0000+200.0000/') is None   # 超出经纬度范围


def test_is_video_file_and_is_isobmff_file():
    from app.utils.video_meta import is_isobmff_file, is_video_file

    assert is_video_file('a.MP4') and is_video_file('a.mov') and is_video_file('a.mkv')
    assert not is_video_file('a.jpg')
    # MKV/WEBM 是视频但不是 ISO BMFF，本模块不解析
    assert is_isobmff_file('a.mp4') and is_isobmff_file('a.MOV')
    assert not is_isobmff_file('a.mkv') and not is_isobmff_file('a.webm')


# --------------------------------------------------------------------------- #
# udta 分支
# --------------------------------------------------------------------------- #

def test_extract_reads_creation_time_make_model_and_gps_from_udta(tmp_path):
    from app.utils.video_meta import extract_video_metadata

    udta = box(b'udta',
               udta_text(b'\xa9day', '2024-05-01T18:30:00+0800')
               + udta_text(b'\xa9mak', 'Apple')
               + udta_text(b'\xa9mod', 'iPhone 15 Pro')
               + udta_text(b'\xa9xyz', '+34.0522-118.2437+000.000/'))
    path = write_mp4(tmp_path, 'udta.mp4', mvhd_box(0), udta, video_trak())

    result = extract_video_metadata(path)

    assert result['video_time'] == datetime(2024, 5, 1, 18, 30, 0)
    assert result['location'] == {
        "latitude": pytest.approx(34.0522), "longitude": pytest.approx(-118.2437)}
    # 键名归一成 EXIF 风格，下游 update_photo_metadata_from_extract 可直接复用
    assert result['video_info']['Make'] == 'Apple'
    assert result['video_info']['Model'] == 'iPhone 15 Pro'
    assert result['video_info']['MediaType'] == 'video'


def test_extract_tolerates_udta_atoms_without_language_prefix(tmp_path):
    from app.utils.video_meta import extract_video_metadata

    # 部分写入器省略 text_size/language，直接跟裸文本
    udta = box(b'udta', box(b'\xa9mak', b'Xiaomi'))
    path = write_mp4(tmp_path, 'bare.mp4', mvhd_box(0), udta)

    assert extract_video_metadata(path)['video_info']['Make'] == 'Xiaomi'


# --------------------------------------------------------------------------- #
# meta(keys + ilst) 分支
# --------------------------------------------------------------------------- #

def test_extract_reads_apple_quicktime_keys_from_meta(tmp_path):
    from app.utils.video_meta import extract_video_metadata

    meta = meta_box(
        ['com.apple.quicktime.creationdate',
         'com.apple.quicktime.make',
         'com.apple.quicktime.model',
         'com.apple.quicktime.location.ISO6709'],
        ['2025-03-08T09:15:20+0800', 'Apple', 'iPhone 14 Pro', '-33.8688+151.2093+021.000/'],
    )
    path = write_mp4(tmp_path, 'apple.mp4', mvhd_box(0), meta, video_trak())

    result = extract_video_metadata(path)

    assert result['video_time'] == datetime(2025, 3, 8, 9, 15, 20)
    assert result['location']['latitude'] == pytest.approx(-33.8688)
    assert result['location']['longitude'] == pytest.approx(151.2093)
    assert result['video_info']['Model'] == 'iPhone 14 Pro'


def test_extract_reads_android_version_key_from_meta(tmp_path):
    from app.utils.video_meta import extract_video_metadata

    meta = meta_box(['com.android.version'], ['16'])
    path = write_mp4(tmp_path, 'android.mp4', mvhd_box(0), meta)

    assert extract_video_metadata(path)['video_info']['AndroidVersion'] == '16'


def test_extract_handles_quicktime_meta_without_version_flags(tmp_path):
    from app.utils.video_meta import extract_video_metadata

    # MOV 的 meta 不是 FullBox（没有前置 version/flags），需要能自动探测
    meta = meta_box(['com.apple.quicktime.make'], ['Apple'], full_box=False)
    path = write_mp4(tmp_path, 'mov_meta.mov', mvhd_box(0), meta)

    assert extract_video_metadata(path)['video_info']['Make'] == 'Apple'


def test_extract_reads_itunes_style_ilst_without_keys_table(tmp_path):
    from app.utils.video_meta import extract_video_metadata

    # iTunes 风格：ilst 条目头直接是 4 字符类型而非 keys 索引
    ilst = box(b'ilst', box(b'\xa9day', data_box('2023-11-02T07:00:00+0000')))
    meta = box(b'meta', b'\x00\x00\x00\x00' + hdlr_box(b'mdir') + ilst)
    path = write_mp4(tmp_path, 'itunes.mp4', mvhd_box(0), meta)

    assert extract_video_metadata(path)['video_time'] == datetime(2023, 11, 2, 7, 0, 0)


# --------------------------------------------------------------------------- #
# 时间优先级
# --------------------------------------------------------------------------- #

def test_create_date_takes_priority_over_mvhd_creation_time(tmp_path):
    from app.utils.video_meta import extract_video_metadata

    mvhd = mvhd_box(qt_seconds(datetime(2020, 1, 1, 0, 0, 0, tzinfo=timezone.utc)))
    meta = meta_box(['com.apple.quicktime.creationdate'], ['2024-05-01T18:30:00+0800'])
    path = write_mp4(tmp_path, 'priority.mp4', mvhd, meta)

    # 带显式时区的 CreateDate 语义更明确，必须压过 mvhd 的 1904 epoch
    assert extract_video_metadata(path)['video_time'] == datetime(2024, 5, 1, 18, 30, 0)


def test_falls_back_to_mvhd_creation_time_converted_to_local_zone(tmp_path):
    from app.utils.video_meta import extract_video_metadata

    moment = datetime(2024, 7, 15, 12, 0, 0, tzinfo=timezone.utc)
    path = write_mp4(tmp_path, 'mvhd_only.mp4', mvhd_box(qt_seconds(moment)))

    # mvhd 按规范是 1904 UTC epoch，需转成本机时区的墙钟时间
    expected = moment.astimezone().replace(tzinfo=None)
    assert extract_video_metadata(path)['video_time'] == expected


def test_mvhd_version1_uses_64bit_fields(tmp_path):
    from app.utils.video_meta import extract_video_metadata

    moment = datetime(2024, 2, 29, 6, 0, 0, tzinfo=timezone.utc)
    mvhd = mvhd_box(qt_seconds(moment), timescale=1000, duration=90000, version=1)
    path = write_mp4(tmp_path, 'v1.mp4', mvhd)

    result = extract_video_metadata(path)
    assert result['video_time'] == moment.astimezone().replace(tzinfo=None)
    assert result['duration'] == pytest.approx(90.0)


def test_zero_creation_time_does_not_produce_1904_timestamp(tmp_path):
    from app.utils.video_meta import extract_video_metadata

    # 大量设备把 creation_time 写 0；不能因此把拍摄时间定成 1904 年
    path = write_mp4(tmp_path, 'zero.mp4', mvhd_box(0))

    assert extract_video_metadata(path)['video_time'] is None


# --------------------------------------------------------------------------- #
# 轨道解析
# --------------------------------------------------------------------------- #

def test_extract_reads_dimensions_duration_codec_and_fps_from_video_track(tmp_path):
    from app.utils.video_meta import extract_video_metadata

    trak = video_trak(width=1920, height=1080, timescale=600, duration=6000,
                      codec=b'avc1', samples=300)
    path = write_mp4(tmp_path, 'track.mp4', mvhd_box(0), trak)

    result = extract_video_metadata(path)

    assert (result['width'], result['height']) == (1920, 1080)
    assert result['duration'] == pytest.approx(10.0)   # 6000 / 600
    assert result['codec'] == 'avc1'
    assert result['fps'] == pytest.approx(30.0)        # 300 samples / 10s
    assert result['rotation'] == 0


def test_rotated_track_swaps_width_and_height(tmp_path):
    from app.utils.video_meta import extract_video_metadata

    # 竖屏手机录像常见：tkhd 记录 1920x1080 + 90° 旋转矩阵，实际显示为 1080x1920
    trak = video_trak(width=1920, height=1080, matrix=_rotate90_matrix())
    path = write_mp4(tmp_path, 'rotated.mp4', mvhd_box(0), trak)

    result = extract_video_metadata(path)

    assert result['rotation'] == 90
    assert (result['width'], result['height']) == (1080, 1920)


def test_track_duration_overrides_mvhd_duration(tmp_path):
    from app.utils.video_meta import extract_video_metadata

    mvhd = mvhd_box(0, timescale=1000, duration=5000)          # 5s
    trak = video_trak(timescale=600, duration=6000)            # 10s
    path = write_mp4(tmp_path, 'dur.mp4', mvhd, trak)

    assert extract_video_metadata(path)['duration'] == pytest.approx(10.0)


def test_audio_only_track_is_ignored_for_dimensions(tmp_path):
    from app.utils.video_meta import extract_video_metadata

    audio = video_trak(width=0, height=0, handler=b'soun')
    path = write_mp4(tmp_path, 'audio.mp4', mvhd_box(0), audio)

    result = extract_video_metadata(path)
    assert result['width'] is None
    assert result['height'] is None


def test_unknown_duration_sentinel_is_not_reported(tmp_path):
    from app.utils.video_meta import extract_video_metadata

    # 0xFFFFFFFF 是"时长未知"的惯用哨兵，不能算成 4294967 秒
    path = write_mp4(tmp_path, 'sentinel.mp4',
                     mvhd_box(0, timescale=1000, duration=0xFFFFFFFF))

    assert extract_video_metadata(path)['duration'] is None


def test_extract_handles_64bit_largesize_moov(tmp_path):
    from app.utils.video_meta import extract_video_metadata

    ftyp = box(b'ftyp', b'isom' + b'\x00' * 8)
    moov = large_box(b'moov', mvhd_box(0) + box(
        b'udta', udta_text(b'\xa9mak', 'Sony')))
    path = tmp_path / 'large.mp4'
    path.write_bytes(ftyp + moov + box(b'mdat', b'\x00' * 16))

    assert extract_video_metadata(str(path))['video_info']['Make'] == 'Sony'


# --------------------------------------------------------------------------- #
# 边界与容错
# --------------------------------------------------------------------------- #

def test_non_isobmff_extension_returns_empty_structure(tmp_path):
    from app.utils.video_meta import extract_video_metadata

    path = tmp_path / 'clip.mkv'
    path.write_bytes(b'\x1a\x45\xdf\xa3' + b'\x00' * 64)

    result = extract_video_metadata(str(path))
    # 结构完整但全空，调用方据此回退到文件名 / mtime
    assert result['video_time'] is None
    assert result['video_info'] == {}
    assert result['width'] is None and result['duration'] is None


def test_missing_moov_returns_empty_structure(tmp_path):
    from app.utils.video_meta import extract_video_metadata

    path = tmp_path / 'nomoov.mp4'
    path.write_bytes(box(b'ftyp', b'isom' + b'\x00' * 8) + box(b'mdat', b'\x00' * 32))

    assert extract_video_metadata(str(path))['video_info'] == {}


def test_empty_and_missing_file_do_not_raise(tmp_path):
    from app.utils.video_meta import extract_video_metadata

    empty = tmp_path / 'empty.mp4'
    empty.write_bytes(b'')
    assert extract_video_metadata(str(empty))['video_time'] is None
    # 不存在的文件也必须静默返回，批处理任务不应被单个文件拖垮
    assert extract_video_metadata(str(tmp_path / 'ghost.mp4'))['video_time'] is None


def test_malformed_box_size_terminates_parsing_without_raising(tmp_path):
    from app.utils.video_meta import extract_video_metadata

    # moov 内塞一个 size=3（< header 8 字节）的畸形 box
    bad = struct.pack('>I', 3) + b'junk'
    path = write_mp4(tmp_path, 'bad.mp4', mvhd_box(0), bad,
                     box(b'udta', udta_text(b'\xa9mak', 'ShouldNotReach')))

    result = extract_video_metadata(path)
    # 遇到畸形 size 即停止遍历，已解析到的 mvhd 时长仍保留
    assert result['duration'] == pytest.approx(12.345)
    assert 'Make' not in result['video_info']


def test_truncated_moov_payload_is_tolerated(tmp_path):
    from app.utils.video_meta import extract_video_metadata

    # 声明 size 超出实际文件长度
    ftyp = box(b'ftyp', b'isom' + b'\x00' * 8)
    truncated = struct.pack('>I', 4096) + b'moov' + mvhd_box(0)[:12]
    path = tmp_path / 'trunc.mp4'
    path.write_bytes(ftyp + truncated)

    assert extract_video_metadata(str(path))['video_time'] is None


# --------------------------------------------------------------------------- #
# 与 exif.extract_metadata 的集成
# --------------------------------------------------------------------------- #

def test_extract_metadata_routes_video_to_container_parser(tmp_path):
    from app.utils.exif import extract_metadata

    meta = meta_box(
        ['com.apple.quicktime.creationdate', 'com.apple.quicktime.model'],
        ['2024-05-01T18:30:00+0800', 'iPhone 15'],
    )
    path = write_mp4(tmp_path, 'IMG_9999.mov', mvhd_box(0), meta,
                     video_trak(width=1920, height=1080, timescale=600, duration=6000))

    result = extract_metadata(path, 'IMG_9999.mov', extract_location_details=False)

    assert result['photo_time'] == datetime(2024, 5, 1, 18, 30, 0)
    assert result['width'] == 1920 and result['height'] == 1080
    assert result['duration'] == pytest.approx(10.0)
    assert result['exif_info']['Model'] == 'iPhone 15'
    assert result['exif_info']['MediaType'] == 'video'


def test_extract_metadata_video_falls_back_to_filename_when_no_container_time(tmp_path):
    from app.utils.exif import extract_metadata

    # 无 CreateDate、mvhd creation_time 为 0 —— 应复用图片分支已有的文件名回退
    path = write_mp4(tmp_path, 'VID_20240601_120000.mp4', mvhd_box(0), video_trak())

    result = extract_metadata(path, 'VID_20240601_120000.mp4', extract_location_details=False)

    assert result['photo_time'] == datetime(2024, 6, 1, 12, 0, 0)


def test_extract_metadata_video_falls_back_to_mtime_when_filename_unparsable(tmp_path):
    from app.utils.exif import extract_metadata

    path = write_mp4(tmp_path, 'clip.mp4', mvhd_box(0), video_trak())
    expected = datetime(2022, 9, 9, 9, 9, 9)
    with patch('app.utils.exif.get_file_time_form_system', return_value=expected):
        result = extract_metadata(path, 'clip.mp4', extract_location_details=False)

    assert result['photo_time'] == expected


def test_extract_metadata_video_runs_reverse_geocode_on_container_gps(tmp_path):
    from app.utils.exif import extract_metadata

    udta = box(b'udta', udta_text(b'\xa9xyz', '+30.5928+114.3055/'))
    path = write_mp4(tmp_path, 'geo.mp4', mvhd_box(0), udta)

    fake_loc = {"city": "武汉市", "province": "湖北省", "country": "CN",
                "district": "", "address": "湖北省武汉市"}
    with patch('app.utils.exif.reverse_geocode', return_value=dict(fake_loc)) as mocked:
        result = extract_metadata(path, 'geo.mp4', extract_location_details=True)

    mocked.assert_called_once()
    # 视频必须和图片一样进入 city/province/scene 链路
    assert result['location_details']['city'] == '武汉市'
    assert result['location_details']['latitude'] == pytest.approx(30.5928)


def test_extract_metadata_video_swallows_reverse_geocode_failure(tmp_path):
    from app.utils.exif import extract_metadata

    udta = box(b'udta', udta_text(b'\xa9xyz', '+30.5928+114.3055/'))
    path = write_mp4(tmp_path, 'geofail.mp4', mvhd_box(0), udta)

    with patch('app.utils.exif.reverse_geocode', side_effect=RuntimeError('rg down')):
        result = extract_metadata(path, 'geofail.mp4', extract_location_details=True)

    assert result['location']['latitude'] == pytest.approx(30.5928)
    assert 'location_details' not in result


def test_extract_metadata_non_isobmff_video_still_returns_photo_time(tmp_path):
    from app.utils.exif import extract_metadata

    path = tmp_path / 'VID_20230715_083000.mkv'
    path.write_bytes(b'\x1a\x45\xdf\xa3' + b'\x00' * 32)

    result = extract_metadata(str(path), 'VID_20230715_083000.mkv',
                              extract_location_details=False)

    assert result['photo_time'] == datetime(2023, 7, 15, 8, 30, 0)
    assert result['exif_info'] is None


def test_determine_image_type_returns_other_for_video_regardless_of_metadata():
    from app.db.models.photo import FileType, ImageType
    from app.service.tasks.metadata import determine_image_type

    # 屏录视频的分辨率会命中手机分辨率白名单，不加 file_type 守卫会被误判为截图
    assert determine_image_type('screen_rec.mp4', 1170, 2532, {},
                                FileType.video) is ImageType.OTHER
    assert determine_image_type('Screenshot_rec.mp4', 800, 600, {},
                                FileType.video) is ImageType.OTHER
    assert determine_image_type('clip.mp4', 4000, 3000, {"Make": "Apple"},
                                FileType.video) is ImageType.OTHER
    # 不传 file_type 时行为与改动前完全一致（存量调用方向后兼容）
    assert determine_image_type('photo.jpg', 1170, 2532, {}) is ImageType.SCREENSHOT
