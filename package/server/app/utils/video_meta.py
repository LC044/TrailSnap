#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""视频元数据解析（纯 Python，无外部二进制依赖）。

设计约束
--------
服务端以 PyInstaller sidecar 形式随 Tauri 桌面端分发，引入 ffmpeg / exiftool
这类外部可执行文件需要跨三平台打包，体积与构建复杂度都不可接受。因此这里沿用
``app/utils/motion_photo.py`` 已有的做法：直接解析 ISO BMFF (MP4/MOV) 的 box
(atom) 结构，只读文件头与 ``moov``，不解码任何音视频数据。

覆盖范围
--------
* MP4 / MOV / M4V / 3GP —— 同一 ISO BMFF 容器，全覆盖。
* AVI / MKV / WEBM —— 不同容器，本模块不解析；调用方会回退到文件名 / mtime。

时间语义（关键）
----------------
``photos.photo_time`` 是 naive datetime，图片走 EXIF ``DateTimeOriginal``，存的是
**拍摄地墙钟时间**。视频侧三个时间源语义并不一致，若不统一会让视频在时间线上
整体偏移若干小时：

1. ``moov/meta`` 的 ``com.apple.quicktime.creationdate`` —— 带时区偏移的字符串，
   取其偏移下的墙钟时间并丢弃 tzinfo（与图片语义一致），优先级最高。
2. ``moov/udta`` 的 ``©day`` —— 同上。
3. ``moov/mvhd`` 的 ``creation_time`` —— 1904-01-01 UTC epoch，按规范转本机时区后
   取墙钟时间，优先级最低。

注意 ``mvhd`` 存在已知的厂商实现分歧：部分 Android 机型把本地时间当成 UTC 写入，
此时转换会引入一次额外偏移。这里遵循规范实现，并把它放在最低优先级，让带显式
时区的 1/2 优先生效。
"""

import logging
import math
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterator, Optional, Tuple

logger = logging.getLogger(__name__)

# 所有被系统视作视频的扩展名（与 storage/basic/scan 中的判断保持一致）
VIDEO_EXTENSIONS = {'.mp4', '.mov', '.m4v', '.avi', '.mkv', '.webm', '.3gp'}

# 本模块能真正解析元数据的扩展名（ISO BMFF 家族）
ISOBMFF_EXTENSIONS = {'.mp4', '.mov', '.m4v', '.3gp'}

# QuickTime / ISO BMFF 时间基准：1904-01-01 00:00:00 UTC
_QT_EPOCH = datetime(1904, 1, 1, tzinfo=timezone.utc)

# 合理的拍摄年份区间，与 app/utils/filename.py 的校验口径一致
_MIN_YEAR = 1990
_MAX_YEAR = 2045

# 单个 box payload 读入内存的上限，避免畸形文件把 size 写成天文数字
_MAX_PAYLOAD_BYTES = 8 * 1024 * 1024

# 原子键名 -> 归一化后的字段名。归一化成 EXIF 风格的键，
# 使下游 update_photo_metadata_from_extract 的 Make/Model 映射可直接复用。
_KEY_ALIASES = {
    'com.apple.quicktime.creationdate': 'CreateDate',
    'com.apple.quicktime.make': 'Make',
    'com.apple.quicktime.model': 'Model',
    'com.apple.quicktime.software': 'Software',
    'com.apple.quicktime.location.iso6709': 'GPSCoordinates',
    'com.apple.quicktime.location.accuracy.horizontal': 'GPSHorizontalAccuracy',
    'com.apple.quicktime.camera.lens_model': 'LensModel',
    'com.apple.quicktime.description': 'Description',
    'com.apple.quicktime.title': 'Title',
    'com.android.version': 'AndroidVersion',
    'com.android.capture.fps': 'CaptureFrameRate',
    '\xa9day': 'CreateDate',
    '\xa9dat': 'CreateDate',
    '\xa9mak': 'Make',
    '\xa9mod': 'Model',
    '\xa9swr': 'Software',
    '\xa9xyz': 'GPSCoordinates',
    '\xa9nam': 'Title',
    '\xa9cmt': 'Comment',
}

_DATE_FORMATS = (
    '%Y-%m-%dT%H:%M:%S%z',
    '%Y-%m-%dT%H:%M:%S.%f%z',
    '%Y-%m-%dT%H:%M:%S',
    '%Y-%m-%dT%H:%M:%S.%f',
    '%Y-%m-%d %H:%M:%S%z',
    '%Y-%m-%d %H:%M:%S',
    '%Y:%m:%d %H:%M:%S',
    '%Y-%m-%d',
)

# ISO 6709: +34.0522-118.2437+000.000/  （高度段可选）
_ISO6709_RE = re.compile(
    r'^\s*([+-]\d{1,3}(?:\.\d+)?)([+-]\d{1,3}(?:\.\d+)?)'
)


def is_video_file(file_path: str) -> bool:
    """扩展名是否属于视频。"""
    return os.path.splitext(file_path)[1].lower() in VIDEO_EXTENSIONS


def is_isobmff_file(file_path: str) -> bool:
    """扩展名是否属于本模块可解析的 ISO BMFF 容器。"""
    return os.path.splitext(file_path)[1].lower() in ISOBMFF_EXTENSIONS


# --------------------------------------------------------------------------- #
# box 遍历
# --------------------------------------------------------------------------- #

def _iter_boxes(f, start: int, end: int) -> Iterator[Tuple[bytes, int, int]]:
    """顺序遍历 [start, end) 区间内的同级 box。

    yield ``(box_type, payload_start, payload_end)``。只做 seek，不把 payload
    读入内存，因此对含大 ``stbl`` 的 moov 也是常量内存开销。
    """
    offset = start
    while offset + 8 <= end:
        f.seek(offset)
        header = f.read(8)
        if len(header) < 8:
            return
        size = int.from_bytes(header[0:4], 'big')
        box_type = header[4:8]
        header_size = 8

        if size == 1:
            # 64 位 largesize
            ext = f.read(8)
            if len(ext) < 8:
                return
            size = int.from_bytes(ext, 'big')
            header_size = 16
        elif size == 0:
            # size 为 0 表示该 box 延伸到容器末尾
            size = end - offset

        if size < header_size:
            return

        payload_start = offset + header_size
        payload_end = min(offset + size, end)
        if payload_start > payload_end:
            return

        yield box_type, payload_start, payload_end
        offset += size


def _find_box(f, start: int, end: int, path: Tuple[bytes, ...]) -> Optional[Tuple[int, int]]:
    """按 path 逐层向下查找 box，返回最内层的 ``(payload_start, payload_end)``。"""
    cur_start, cur_end = start, end
    for want in path:
        found = None
        for box_type, p_start, p_end in _iter_boxes(f, cur_start, cur_end):
            if box_type == want:
                found = (p_start, p_end)
                break
        if found is None:
            return None
        cur_start, cur_end = found
    return cur_start, cur_end


def _read_payload(f, start: int, end: int) -> bytes:
    """读取 box payload，带上限保护。"""
    length = max(0, min(end - start, _MAX_PAYLOAD_BYTES))
    if length == 0:
        return b''
    f.seek(start)
    return f.read(length)


# --------------------------------------------------------------------------- #
# 标量解析
# --------------------------------------------------------------------------- #

def _fixed16_16(raw: bytes) -> float:
    """16.16 定点数。"""
    return int.from_bytes(raw, 'big', signed=True) / 65536.0


def _fixed2_30(raw: bytes) -> float:
    """2.30 定点数（变换矩阵的第三列）。"""
    return int.from_bytes(raw, 'big', signed=True) / (1 << 30)


def _qt_time_to_datetime(seconds: int) -> Optional[datetime]:
    """1904 UTC epoch 秒 -> 本机时区墙钟时间（naive）。"""
    if not seconds or seconds <= 0:
        return None
    try:
        dt_utc = _QT_EPOCH + timedelta(seconds=int(seconds))
    except (OverflowError, OSError, ValueError):
        return None
    try:
        local = dt_utc.astimezone()
    except (OverflowError, OSError, ValueError):
        return None
    if not (_MIN_YEAR <= local.year <= _MAX_YEAR):
        return None
    return local.replace(tzinfo=None)


def parse_datetime_string(value: Any) -> Optional[datetime]:
    """解析 atom 里的时间字符串，返回 naive 墙钟时间。

    带时区偏移时保留该偏移下的墙钟读数并丢弃 tzinfo，从而与图片 EXIF
    ``DateTimeOriginal`` 的语义对齐。
    """
    if not isinstance(value, str):
        return None
    text = value.strip().replace('\x00', '')
    if not text:
        return None

    # Z -> +0000；+08:00 -> +0800（%z 在 3.7+ 支持冒号，但统一处理更稳）
    normalized = re.sub(r'[Zz]$', '+0000', text)
    normalized = re.sub(r'([+-]\d{2}):(\d{2})$', r'\1\2', normalized)

    for fmt in _DATE_FORMATS:
        try:
            dt = datetime.strptime(normalized, fmt)
        except ValueError:
            continue
        if dt.tzinfo is not None:
            dt = dt.replace(tzinfo=None)
        if _MIN_YEAR <= dt.year <= _MAX_YEAR:
            return dt
        return None
    return None


def parse_iso6709(value: Any) -> Optional[Dict[str, float]]:
    """解析 ISO 6709 坐标串（``©xyz`` / QuickTime location.ISO6709）。"""
    if not isinstance(value, str):
        return None
    match = _ISO6709_RE.match(value.replace('\x00', ''))
    if not match:
        return None
    try:
        lat = float(match.group(1))
        lng = float(match.group(2))
    except ValueError:
        return None
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0):
        return None
    if lat == 0.0 and lng == 0.0:
        return None
    return {"latitude": lat, "longitude": lng}


def _decode_text(raw: bytes) -> str:
    for encoding in ('utf-8', 'utf-16-be', 'latin-1'):
        try:
            return raw.decode(encoding).strip().replace('\x00', '')
        except UnicodeDecodeError:
            continue
    return ''


def _atom_type_to_key(raw: bytes) -> str:
    """4 字节 atom 类型转可读键名（``\\xa9day`` -> ``©day``）。"""
    return raw.decode('latin-1')


# --------------------------------------------------------------------------- #
# udta / meta 标签解析
# --------------------------------------------------------------------------- #

def _parse_udta(payload: bytes) -> Dict[str, Any]:
    """解析 ``udta`` 下的 QuickTime 文本型 user-data atom。

    经典布局：``[size][type][text_size(2)][language(2)][text]``；部分写入器会
    省略 text_size/language 直接跟裸文本，这里做兼容。
    """
    tags: Dict[str, Any] = {}
    offset = 0
    total = len(payload)
    while offset + 8 <= total:
        size = int.from_bytes(payload[offset:offset + 4], 'big')
        atom_type = payload[offset + 4:offset + 8]
        if size < 8 or offset + size > total:
            break
        body = payload[offset + 8:offset + size]
        offset += size

        if atom_type == b'meta':
            tags.update(_parse_meta(body))
            continue

        if len(body) >= 4:
            declared = int.from_bytes(body[0:2], 'big')
            if declared == len(body) - 4:
                body = body[4:]

        text = _decode_text(body)
        if text:
            tags[_atom_type_to_key(atom_type)] = text
    return tags


def _parse_keys(payload: bytes) -> list:
    """解析 ``meta/keys``，返回按序的 key 名称列表（1-based 由调用方处理）。"""
    keys: list = []
    if len(payload) < 8:
        return keys
    entry_count = int.from_bytes(payload[4:8], 'big')
    offset = 8
    total = len(payload)
    while offset + 8 <= total and len(keys) < entry_count:
        size = int.from_bytes(payload[offset:offset + 4], 'big')
        if size < 8 or offset + size > total:
            break
        # payload[offset+4:offset+8] 是 namespace（通常为 'mdta'）
        keys.append(_decode_text(payload[offset + 8:offset + size]))
        offset += size
    return keys


def _parse_data_box(body: bytes) -> Any:
    """解析 ilst 条目内的 ``data`` box，按 type indicator 还原值类型。"""
    offset = 0
    total = len(body)
    while offset + 8 <= total:
        size = int.from_bytes(body[offset:offset + 4], 'big')
        box_type = body[offset + 4:offset + 8]
        if size < 8 or offset + size > total:
            break
        inner = body[offset + 8:offset + size]
        offset += size
        if box_type != b'data' or len(inner) < 8:
            continue

        type_indicator = int.from_bytes(inner[0:4], 'big')
        value_bytes = inner[8:]
        if type_indicator == 1:  # UTF-8
            return _decode_text(value_bytes)
        if type_indicator == 2:  # UTF-16
            try:
                return value_bytes.decode('utf-16-be').strip().replace('\x00', '')
            except UnicodeDecodeError:
                return _decode_text(value_bytes)
        if type_indicator in (21, 22) and value_bytes:  # 有/无符号整数
            return int.from_bytes(value_bytes, 'big', signed=(type_indicator == 21))
        if type_indicator == 23 and len(value_bytes) >= 4:  # float32
            import struct
            return struct.unpack('>f', value_bytes[:4])[0]
        if type_indicator == 24 and len(value_bytes) >= 8:  # float64
            import struct
            return struct.unpack('>d', value_bytes[:8])[0]
        text = _decode_text(value_bytes)
        return text or None
    return None


def _parse_ilst(payload: bytes, keys: list) -> Dict[str, Any]:
    """解析 ``meta/ilst``。

    条目的 4 字节头既可能是指向 ``keys`` 表的 1-based 索引（QuickTime mdta 风格），
    也可能直接是 iTunes 风格的 4 字符类型（如 ``©day``）。两种都处理。
    """
    tags: Dict[str, Any] = {}
    offset = 0
    total = len(payload)
    while offset + 8 <= total:
        size = int.from_bytes(payload[offset:offset + 4], 'big')
        raw_key = payload[offset + 4:offset + 8]
        if size < 8 or offset + size > total:
            break
        body = payload[offset + 8:offset + size]
        offset += size

        index = int.from_bytes(raw_key, 'big')
        if keys and 1 <= index <= len(keys):
            name = keys[index - 1]
        else:
            name = _atom_type_to_key(raw_key)
        if not name:
            continue

        value = _parse_data_box(body)
        if value is not None and value != '':
            tags[name] = value
    return tags


def _parse_meta(payload: bytes) -> Dict[str, Any]:
    """解析 ``meta``。

    MP4 中 ``meta`` 是 FullBox（前置 4 字节 version/flags），而 QuickTime MOV 中
    不是。通过探测前 4..8 字节是否为已知子 box 类型来区分。
    """
    if len(payload) < 8:
        return {}

    body = payload
    if payload[4:8] not in (b'hdlr', b'keys', b'ilst', b'free', b'mdta'):
        body = payload[4:]  # FullBox，跳过 version/flags

    keys: list = []
    ilst_payload = b''
    nested: Dict[str, Any] = {}

    offset = 0
    total = len(body)
    while offset + 8 <= total:
        size = int.from_bytes(body[offset:offset + 4], 'big')
        box_type = body[offset + 4:offset + 8]
        if size < 8 or offset + size > total:
            break
        inner = body[offset + 8:offset + size]
        offset += size

        if box_type == b'keys':
            keys = _parse_keys(inner)
        elif box_type == b'ilst':
            ilst_payload = inner
        elif box_type == b'udta':
            nested.update(_parse_udta(inner))

    tags: Dict[str, Any] = {}
    if ilst_payload:
        tags.update(_parse_ilst(ilst_payload, keys))
    tags.update(nested)
    return tags


# --------------------------------------------------------------------------- #
# 轨道信息
# --------------------------------------------------------------------------- #

def _parse_mvhd(payload: bytes) -> Dict[str, Any]:
    """解析 ``mvhd``：创建时间与总时长。"""
    info: Dict[str, Any] = {}
    if len(payload) < 4:
        return info
    version = payload[0]
    if version == 1:
        if len(payload) < 32:
            return info
        creation = int.from_bytes(payload[4:12], 'big')
        timescale = int.from_bytes(payload[20:24], 'big')
        duration = int.from_bytes(payload[24:32], 'big')
    else:
        if len(payload) < 20:
            return info
        creation = int.from_bytes(payload[4:8], 'big')
        timescale = int.from_bytes(payload[12:16], 'big')
        duration = int.from_bytes(payload[16:20], 'big')

    info['creation_time'] = _qt_time_to_datetime(creation)
    if timescale > 0 and duration > 0:
        # 0xFFFFFFFF 是"时长未知"的惯用哨兵值
        if not (version == 0 and duration == 0xFFFFFFFF):
            info['duration'] = round(duration / timescale, 3)
    return info


def _parse_tkhd(payload: bytes) -> Dict[str, Any]:
    """解析 ``tkhd``：显示宽高与变换矩阵推导出的旋转角。"""
    info: Dict[str, Any] = {}
    if len(payload) < 4:
        return info
    version = payload[0]
    offset = 4 + (32 if version == 1 else 20)
    offset += 8 + 2 + 2 + 2 + 2  # reserved(8) layer(2) alt_group(2) volume(2) reserved(2)

    if len(payload) < offset + 36 + 8:
        return info

    matrix = [payload[offset + i * 4: offset + (i + 1) * 4] for i in range(9)]
    offset += 36

    width = _fixed16_16(payload[offset:offset + 4])
    height = _fixed16_16(payload[offset + 4:offset + 8])

    a = _fixed16_16(matrix[0])
    b = _fixed16_16(matrix[1])
    # matrix[2] / [5] / [8] 是 2.30 定点（u, v, w），此处仅用于健壮性校验
    _fixed2_30(matrix[2])

    rotation = 0
    if a or b:
        rotation = int(round(math.degrees(math.atan2(b, a)))) % 360
        # 归一到 0/90/180/270
        rotation = min((0, 90, 180, 270), key=lambda r: min(abs(rotation - r), 360 - abs(rotation - r)))

    if width > 0 and height > 0:
        w, h = int(round(width)), int(round(height))
        if rotation in (90, 270):
            w, h = h, w
        info['width'] = w
        info['height'] = h
    info['rotation'] = rotation
    return info


def _parse_mdhd(payload: bytes) -> Dict[str, Any]:
    """解析 ``mdhd``：媒体 timescale 与时长。"""
    info: Dict[str, Any] = {}
    if len(payload) < 4:
        return info
    version = payload[0]
    if version == 1:
        if len(payload) < 32:
            return info
        timescale = int.from_bytes(payload[20:24], 'big')
        duration = int.from_bytes(payload[24:32], 'big')
    else:
        if len(payload) < 20:
            return info
        timescale = int.from_bytes(payload[12:16], 'big')
        duration = int.from_bytes(payload[16:20], 'big')
    if timescale > 0 and duration > 0:
        info['duration'] = round(duration / timescale, 3)
    return info


def _parse_stsd_codec(payload: bytes) -> Optional[str]:
    """从 ``stsd`` 第一条 sample entry 取 codec 四字符码。"""
    if len(payload) < 16:
        return None
    codec = payload[12:16]
    text = _decode_text(codec)
    return text or None


def _parse_stsz_sample_count(payload: bytes) -> Optional[int]:
    """从 ``stsz`` 取样本数（用于估算帧率）。"""
    if len(payload) < 12:
        return None
    count = int.from_bytes(payload[8:12], 'big')
    return count or None


def _parse_video_track(f, moov_start: int, moov_end: int) -> Dict[str, Any]:
    """找到第一条 handler 为 ``vide`` 的轨道，抽取尺寸/时长/codec/帧率。"""
    info: Dict[str, Any] = {}
    for box_type, t_start, t_end in _iter_boxes(f, moov_start, moov_end):
        if box_type != b'trak':
            continue

        hdlr = _find_box(f, t_start, t_end, (b'mdia', b'hdlr'))
        if hdlr is None:
            continue
        hdlr_payload = _read_payload(f, *hdlr)
        if len(hdlr_payload) < 12 or hdlr_payload[8:12] != b'vide':
            continue

        tkhd = _find_box(f, t_start, t_end, (b'tkhd',))
        if tkhd is not None:
            info.update(_parse_tkhd(_read_payload(f, *tkhd)))

        mdhd = _find_box(f, t_start, t_end, (b'mdia', b'mdhd'))
        track_duration = None
        if mdhd is not None:
            track_duration = _parse_mdhd(_read_payload(f, *mdhd)).get('duration')
            if track_duration:
                info['duration'] = track_duration

        stsd = _find_box(f, t_start, t_end, (b'mdia', b'minf', b'stbl', b'stsd'))
        if stsd is not None:
            codec = _parse_stsd_codec(_read_payload(f, *stsd))
            if codec:
                info['codec'] = codec

        stsz = _find_box(f, t_start, t_end, (b'mdia', b'minf', b'stbl', b'stsz'))
        if stsz is not None and track_duration:
            sample_count = _parse_stsz_sample_count(_read_payload(f, *stsz))
            if sample_count and track_duration > 0:
                info['fps'] = round(sample_count / track_duration, 3)

        break
    return info


# --------------------------------------------------------------------------- #
# 对外入口
# --------------------------------------------------------------------------- #

def _empty_result() -> Dict[str, Any]:
    return {
        "video_time": None,
        "video_info": {},
        "location": None,
        "width": None,
        "height": None,
        "duration": None,
        "rotation": None,
        "fps": None,
        "codec": None,
    }


def extract_video_metadata(file_path: str) -> Dict[str, Any]:
    """解析视频文件元数据。

    只读文件头与 ``moov``，不解码媒体数据。任何解析失败都被吞掉并返回已取到的
    部分结果，绝不向上抛异常（调用链在批处理任务里，单文件不应拖垮整批）。
    """
    result = _empty_result()
    if not is_isobmff_file(file_path):
        return result

    try:
        file_size = os.path.getsize(file_path)
        if file_size <= 8:
            return result

        with open(file_path, 'rb') as f:
            moov = _find_box(f, 0, file_size, (b'moov',))
            if moov is None:
                return result
            moov_start, moov_end = moov

            tags: Dict[str, Any] = {}

            # 1. moov/udta（含其下嵌套的 meta）
            udta = _find_box(f, moov_start, moov_end, (b'udta',))
            if udta is not None:
                tags.update(_parse_udta(_read_payload(f, *udta)))

            # 2. moov/meta（Apple mdta keys+ilst / Android com.android.*）
            meta = _find_box(f, moov_start, moov_end, (b'meta',))
            if meta is not None:
                tags.update(_parse_meta(_read_payload(f, *meta)))

            # 3. mvhd：总时长 + 最低优先级的创建时间
            mvhd_time = None
            mvhd = _find_box(f, moov_start, moov_end, (b'mvhd',))
            if mvhd is not None:
                mvhd_info = _parse_mvhd(_read_payload(f, *mvhd))
                mvhd_time = mvhd_info.get('creation_time')
                if mvhd_info.get('duration'):
                    result['duration'] = mvhd_info['duration']

            # 4. 视频轨道：尺寸 / 旋转 / codec / 帧率（轨道时长优先于 mvhd）
            track_info = _parse_video_track(f, moov_start, moov_end)
            for key in ('width', 'height', 'rotation', 'codec', 'fps'):
                if track_info.get(key) is not None:
                    result[key] = track_info[key]
            if track_info.get('duration'):
                result['duration'] = track_info['duration']

        # 归一化标签键名
        normalized: Dict[str, Any] = {}
        for raw_key, value in tags.items():
            alias = _KEY_ALIASES.get(raw_key.lower(), _KEY_ALIASES.get(raw_key))
            normalized[alias or raw_key] = value

        # 拍摄时间：CreateDate（带时区）> mvhd（1904 UTC epoch）
        result['video_time'] = parse_datetime_string(normalized.get('CreateDate')) or mvhd_time

        # GPS：优先 ISO 6709 字符串
        result['location'] = parse_iso6709(normalized.get('GPSCoordinates'))

        # 补齐视频专属字段，便于前端 EXIF 面板与导出模板直接使用
        normalized['MediaType'] = 'video'
        for key, label in (('duration', 'Duration'), ('fps', 'FrameRate'),
                           ('codec', 'VideoCodec'), ('rotation', 'Rotation')):
            if result.get(key) is not None:
                normalized[label] = result[key]
        if result.get('width') and result.get('height'):
            normalized['ImageWidth'] = result['width']
            normalized['ImageHeight'] = result['height']

        result['video_info'] = normalized
    except Exception as e:
        logger.warning(f"extract_video_metadata failed for {file_path}: {e}")

    return result
