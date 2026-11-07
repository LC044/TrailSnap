#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""把数据库中的 GPS 坐标写回媒体原文件（REQ-223 / issue #445）。

设计约束
--------
与 ``app/utils/video_meta.py`` 相同：服务端以 PyInstaller sidecar 形式随桌面端
分发，不能引入 ffmpeg / exiftool。图片侧复用已在依赖中的 piexif；视频侧沿用
``video_meta`` 的纯 Python ISO BMFF box 解析，写回与读取共用同一套结构定义。

写回目标格式（通用标准，主流相册均可读）：

* 图片：EXIF GPS IFD（度分秒有理数 + 半球 Ref），与读取端
  ``app/utils/exif.py::get_gps_info`` 互逆。
* 视频：``moov/udta`` 下的 ``©xyz``（QuickTime 文本 atom）与 ``moov/meta``
  的 mdta 键 ``com.apple.quicktime.location.ISO6709``，均用 ISO 6709 ASCII 串，
  与读取端 ``video_meta._KEY_ALIASES`` 对齐。

格式支持矩阵（以实测为准）：

* JPEG —— piexif.insert 原地插段，无损；
* WebP —— piexif.insert 走 RIFF 重写，无损；
* TIFF —— piexif 不支持（InvalidImageDataError），走 Pillow 重编码；
* HEIC/HEIF 及其他图片格式 —— 不支持，抛 WriteBackUnsupported；
* MP4/MOV/M4V/3GP —— ISO BMFF 原子注入；
* AVI/MKV/WEBM —— 不支持，抛 WriteBackUnsupported。

安全模型
--------
所有写回都走"临时文件 → 校验 → ``os.replace`` 原子替换"：

* 图片写临时文件后重新加载，GPS 读回值与写入值一致才替换；
* 视频写临时文件后用 ``video_meta.extract_video_metadata`` 完整重解析，
  读回同一坐标且 duration/尺寸等关键元数据不丢失才替换；
* 任何一步失败都清理临时文件，原文件字节不变。

视频布局
--------
``moov`` 在 ``mdat`` 之后（手机直录常见布局）时插入 ``udta`` 不影响任何
chunk offset，仅重写 moov 区段。``moov`` 在 ``mdat`` 之前（faststart，流媒体
优化布局）时插入会把 ``mdat`` 整体后移 delta 字节，必须把全部 ``stco`` /
``co64`` 表项加 delta，否则文件直接损坏——这是写回实现里最关键的一步。

md5 联动
--------
写回改变文件内容后必须重算 ``photos.md5``（上传去重 / 重复检测依赖它）。
调用方（API 层）负责在写回成功后调用 :func:`update_photo_md5`。
"""

import logging
import math
import os
import struct
import tempfile
from typing import Optional, Tuple

from app.service.disk_budget import disk_budget
from app.utils import video_meta

logger = logging.getLogger(__name__)

try:
    import piexif
    PIEXIF_AVAILABLE = True
except ImportError:
    PIEXIF_AVAILABLE = False

# piexif.insert 可写的图片格式（JPEG/WebP）
_PIEXIF_WRITE_EXTENSIONS = {'.jpg', '.jpeg', '.webp'}
# Pillow 重编码可写 EXIF 的格式（TIFF）
_PILLOW_WRITE_EXTENSIONS = {'.tiff', '.tif'}
_IMAGE_WRITE_EXTENSIONS = _PIEXIF_WRITE_EXTENSIONS | _PILLOW_WRITE_EXTENSIONS

# ISO BMFF 家族（写入范围等同 video_meta 的读取范围）
_VIDEO_WRITE_EXTENSIONS = video_meta.ISOBMFF_EXTENSIONS

# chunk offset 表所在的 box 类型（faststart 重写时需修正）
_OFFSET_BOXES = (b'stco', b'co64')

# 遍历 stco/co64 时允许下钻的容器 box（与 video_meta 的解析范围一致）
_CONTAINER_BOXES = {b'moov', b'trak', b'mdia', b'minf', b'stbl', b'udta', b'meta',
                    b'edts', b'dinf'}


class WriteBackUnsupported(Exception):
    """该文件 / 格式不支持 GPS 写回，调用方应计为 skipped 而非 failed。"""


def _is_supported_image(file_path: str) -> bool:
    return os.path.splitext(file_path)[1].lower() in _IMAGE_WRITE_EXTENSIONS


def _validate_coordinates(latitude: float, longitude: float) -> Tuple[float, float]:
    lat, lng = float(latitude), float(longitude)
    if not (math.isfinite(lat) and math.isfinite(lng)
            and -90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0):
        raise ValueError(f"Invalid GPS coordinates: ({latitude}, {longitude})")
    return lat, lng


def _make_temp_path(file_path: str) -> str:
    """在原目录创建临时文件路径，以原扩展名收尾。

    后续校验会用扩展名识别格式（video_meta.is_isobmff_file / piexif /
    Pillow 的 format 探测都依赖扩展名），临时文件必须保持可识别的后缀。
    `.gps.tmp` 中缀不影响 splitext（它只取最后一个后缀）。
    """
    directory = os.path.dirname(file_path) or '.'
    base, ext = os.path.splitext(os.path.basename(file_path))
    fd, temp_path = tempfile.mkstemp(
        suffix=f'.gps{ext}', prefix=base + '.tmp', dir=directory)
    os.close(fd)
    return os.path.abspath(temp_path)


def _atomic_replace(temp_path: str, target_path: str) -> None:
    with disk_budget.slots(temp_path, target_path):
        os.replace(temp_path, target_path)


def _cleanup(temp_path: Optional[str]) -> None:
    if temp_path and os.path.exists(temp_path):
        try:
            os.remove(temp_path)
        except OSError:
            logger.warning("Failed to remove temporary file %s", temp_path)


# --------------------------------------------------------------------------- #
# 图片：EXIF GPS IFD
# --------------------------------------------------------------------------- #

def _to_dms(value: float) -> Tuple[Tuple[int, int], Tuple[int, int], Tuple[int, int]]:
    """十进制角度 -> (度, 分, 秒) 有理数元组，秒保留 4 位小数避免精度损失。

    入参取绝对值（南/西半球由 GPSLatitudeRef / GPSLongitudeRef 表达，
    EXIF 的有理数本身必须非负）。
    """
    value = abs(value)
    degrees = int(value)
    minutes_float = (value - degrees) * 60
    minutes = int(minutes_float)
    seconds = round((minutes_float - minutes) * 60 * 10000)
    return ((degrees, 1), (minutes, 1), (seconds, 10000))


def _build_gps_ifd(lat: float, lng: float) -> dict:
    return {
        piexif.GPSIFD.GPSVersionID: struct.pack('>BBBB', 2, 3, 0, 0),
        piexif.GPSIFD.GPSLatitudeRef: b'N' if lat >= 0 else b'S',
        piexif.GPSIFD.GPSLatitude: _to_dms(lat),
        piexif.GPSIFD.GPSLongitudeRef: b'E' if lng >= 0 else b'W',
        piexif.GPSIFD.GPSLongitude: _to_dms(lng),
    }


def _verify_image_gps(temp_path: str, lat: float, lng: float) -> None:
    """写后校验：重新加载临时文件，GPS 读回值必须与写入值一致。"""
    from app.utils.exif import get_exif_data, get_gps_info
    from app.utils.image_loading import Image
    from app.service.disk_budget import budgeted_open

    with budgeted_open(temp_path) as source:
        with Image.open(source) as img:
            exif = get_exif_data(img)
    read_back = get_gps_info(exif) if exif else None
    if not read_back:
        raise ValueError("GPS verification failed: no GPS read back from written image")
    if abs(read_back["latitude"] - lat) > 1e-4 or abs(read_back["longitude"] - lng) > 1e-4:
        raise ValueError(
            f"GPS verification failed: wrote ({lat}, {lng}), read back "
            f"({read_back['latitude']}, {read_back['longitude']})")


def write_image_gps(file_path: str, latitude: float, longitude: float) -> None:
    """把 GPS 写入图片 EXIF，校验后原子替换原文件。

    JPEG/WebP 走 piexif.insert（无损插段）；TIFF 走 Pillow 重编码。
    HEIC 等不支持的格式抛 :class:`WriteBackUnsupported`（调用方计为
    skipped，数据库照常更新）。
    """
    if not PIEXIF_AVAILABLE:
        raise WriteBackUnsupported("piexif is not available")
    if not _is_supported_image(file_path):
        raise WriteBackUnsupported(f"Unsupported image format for GPS write-back: {file_path}")
    if not os.path.exists(file_path):
        raise WriteBackUnsupported(f"File not found: {file_path}")

    lat, lng = _validate_coordinates(latitude, longitude)
    temp_path = _make_temp_path(file_path)
    try:
        ext = os.path.splitext(file_path)[1].lower()
        if ext in _PIEXIF_WRITE_EXTENSIONS:
            try:
                exif_dict = piexif.load(file_path)
            except ValueError:
                # WebP 无既有 EXIF 时 piexif.load 抛 ValueError，从空段开始
                exif_dict = {'0th': {}, 'Exif': {}, 'GPS': {}, '1st': {}}
            exif_dict["GPS"] = _build_gps_ifd(lat, lng)
            # new_file: 写出到临时文件，不动原文件（校验通过后再替换）
            with disk_budget.slots(file_path, temp_path):
                piexif.insert(piexif.dump(exif_dict), file_path, temp_path)
        else:
            # TIFF: piexif 不支持，走 Pillow 重编码（tiff 本身无损格式，质量无损）
            from app.utils.image_loading import Image
            from app.service.disk_budget import budgeted_open
            with disk_budget.slots(file_path, temp_path):
                with budgeted_open(file_path) as source:
                    with Image.open(source) as img:
                        img.save(temp_path, format='TIFF', exif=piexif.dump(
                            {"GPS": _build_gps_ifd(lat, lng)}))
        _verify_image_gps(temp_path, lat, lng)
        _atomic_replace(temp_path, file_path)
    except WriteBackUnsupported:
        _cleanup(temp_path)
        raise
    except Exception as e:
        _cleanup(temp_path)
        raise RuntimeError(f"Failed to write GPS into {file_path}: {e}") from e
    finally:
        # 成功路径 replace 后 temp 已不存在；失败路径上面已清理。幂等兜底。
        _cleanup(temp_path)


# --------------------------------------------------------------------------- #
# 视频：ISO BMFF 原子注入
# --------------------------------------------------------------------------- #

def _format_iso6709(lat: float, lng: float) -> str:
    """坐标 -> ISO 6709 ASCII（QuickTime 惯用：±dd.dddddd±ddd.dddddd±sss.s/）。"""
    return f"{lat:+.6f}{lng:+.6f}{0.0:+07.1f}/"


def _udta_text_atom(atom_type: bytes, text: str) -> bytes:
    """构造 QuickTime 文本 atom：[size][type][text_size(2)][language(2)][text]。"""
    raw = text.encode('utf-8')
    return struct.pack('>I', len(raw) + 12) + atom_type + struct.pack('>HH', len(raw), 0) + raw


def _mdta_ilst_entry(key_index: int, value_bytes: bytes, type_indicator: int = 1) -> bytes:
    """构造 ilst 条目：[size][key_index(4)][data box]。

    data box: [size][b'data'][type_indicator(4)][locale(4)][value]。
    """
    data = (struct.pack('>I', len(value_bytes) + 16) + b'data'
            + struct.pack('>II', type_indicator, 0) + value_bytes)
    return struct.pack('>I', len(data) + 8) + struct.pack('>I', key_index) + data


def _extract_data_box(body: bytes) -> Tuple[Optional[bytes], int]:
    """从 ilst 条目取 data box 的原始值与 type indicator（保留原类型重写）。"""
    offset, total = 0, len(body)
    while offset + 8 <= total:
        size = int.from_bytes(body[offset:offset + 4], 'big')
        box_type = body[offset + 4:offset + 8]
        if size < 8 or offset + size > total:
            break
        inner = body[offset + 8:offset + size]
        offset += size
        if box_type == b'data' and len(inner) >= 8:
            return inner[8:], int.from_bytes(inner[0:4], 'big')
    return None, 0


def _build_location_udta(existing: Optional[bytes], iso_string: str) -> bytes:
    """构造新 udta payload：保留既有原子，原位替换或追加 ``©xyz``。

    原位替换避免反复写回时 udta 无限膨胀。
    """
    xyz = _udta_text_atom(b'\xa9xyz', iso_string)
    if existing is None:
        return xyz

    parts, offset, total = [], 0, len(existing)
    replaced = False
    while offset + 8 <= total:
        size = int.from_bytes(existing[offset:offset + 4], 'big')
        atom_type = existing[offset + 4:offset + 8]
        if size < 8 or offset + size > total:
            break
        if atom_type == b'\xa9xyz':
            parts.append(xyz)
            replaced = True
        else:
            parts.append(existing[offset:offset + size])
        offset += size
    if not replaced:
        parts.append(xyz)
    return b''.join(parts)


def _build_location_meta(existing: Optional[bytes], iso_string: str) -> bytes:
    """构造新 meta payload：keys + ilst 重建成对，含 location.ISO6709。

    既有键值先解析收集再重新编码，保证重建后原值不丢。
    """
    location_key = 'com.apple.quicktime.location.ISO6709'
    entries: list = []  # [(name, raw_value, type_indicator)]
    was_full_box = True

    if existing:
        payload = existing
        if payload[4:8] not in (b'hdlr', b'keys', b'ilst', b'free', b'mdta'):
            payload = payload[4:]
        else:
            was_full_box = False  # QuickTime MOV 风格 meta（非 FullBox）
        keys: list = []
        ilst_payload = b''
        offset, total = 0, len(payload)
        while offset + 8 <= total:
            size = int.from_bytes(payload[offset:offset + 4], 'big')
            box_type = payload[offset + 4:offset + 8]
            if size < 8 or offset + size > total:
                break
            inner = payload[offset + 8:offset + size]
            offset += size
            if box_type == b'keys':
                keys = video_meta._parse_keys(inner)
            elif box_type == b'ilst':
                ilst_payload = inner

        if ilst_payload:
            offset, total = 0, len(ilst_payload)
            while offset + 8 <= total:
                size = int.from_bytes(ilst_payload[offset:offset + 4], 'big')
                raw_key = ilst_payload[offset + 4:offset + 8]
                if size < 8 or offset + size > total:
                    break
                body = ilst_payload[offset + 8:offset + size]
                offset += size
                index = int.from_bytes(raw_key, 'big')
                if keys and 1 <= index <= len(keys):
                    name = keys[index - 1]
                else:
                    name = raw_key.decode('latin-1')
                value, indicator = _extract_data_box(body)
                if name and value is not None:
                    entries.append((name, value, indicator))

    # 丢弃已有 location 条目（无论大小写），追加新值；其余保留
    filtered = [(n, v, i) for (n, v, i) in entries if n.lower() != location_key]
    filtered.append((location_key, iso_string.encode('utf-8'), 1))

    names = [n for n, _, _ in filtered]
    keys_box = (struct.pack('>II', 0, len(names))
                + b''.join(struct.pack('>I', len(n) + 12) + b'mdta' + n.encode('utf-8')
                           for n in names))
    ilst = b''.join(_mdta_ilst_entry(i + 1, v, t) for i, (_, v, t) in enumerate(filtered))
    hdlr = (struct.pack('>I', 33) + b'hdlr' + b'\x00' * 8 + b'mdta' + b'\x00' * 12)

    body = (hdlr
            + struct.pack('>I', len(keys_box) + 8) + b'keys' + keys_box
            + struct.pack('>I', len(ilst) + 8) + b'ilst' + ilst)
    if was_full_box:
        body = b'\x00\x00\x00\x00' + body
    return body


def _read_range(f, start: int, end: int) -> bytes:
    f.seek(start)
    return f.read(end - start)


def _rebuild_moov(f, moov_start: int, moov_end: int, iso_string: str) -> bytes:
    """重建 moov 完整字节流（含 box 头），在其中注入位置原子。

    遍历 moov 的直接子 box：udta / meta 被替换为注入后的新 payload，
    其余（mvhd/trak/...）原样字节拷贝；缺失则新建 udta（含 ©xyz）与
    meta（含 location.ISO6709）。返回的 box 总以 32 位 size 描述——
    原 moov 为 64 位 largesize 时重建会降级为 32 位 size，写入侧只需
    保证文件总长一致即可（moov 重建前后文件级偏移由 delta 统一处理）。
    """
    children = []  # [(box_type, payload_bytes)]
    for box_type, p_start, p_end in video_meta._iter_boxes(f, moov_start, moov_end):
        if box_type == b'udta':
            children.append((b'udta', _build_location_udta(
                _read_range(f, p_start, p_end), iso_string)))
        elif box_type == b'meta':
            children.append((b'meta', _build_location_meta(
                _read_range(f, p_start, p_end), iso_string)))
        else:
            children.append((box_type, _read_range(f, p_start, p_end)))

    if not any(t == b'udta' for t, _ in children):
        children.append((b'udta', _build_location_udta(None, iso_string)))
    if not any(t == b'meta' for t, _ in children):
        children.append((b'meta', _build_location_meta(None, iso_string)))

    payload = b''
    for box_type, body in children:
        payload += struct.pack('>I', len(body) + 8) + box_type + body
    return struct.pack('>I', len(payload) + 8) + b'moov' + payload


def _copy_stream(src, dst, length: int) -> None:
    remaining = length
    while remaining > 0:
        chunk = src.read(min(1024 * 1024, remaining))
        if not chunk:
            break
        dst.write(chunk)
        remaining -= len(chunk)


def _patch_chunk_offsets(moov_bytes: bytes, delta: int) -> bytes:
    """把 moov 内所有 stco/co64 表项 +delta。

    前提（faststart 重写路径下恒成立）：moov 前缀字节不动、moov 自身起点
    不变仅长度变化。表项是文件绝对偏移，chunk 数据只存在于 mdat（其后整体
    后移 delta），且指向 moov 内部的 chunk offset 不存在，因此全表 +delta。
    """
    data = bytearray(moov_bytes)
    for box_type, payload_start in _walk_offset_boxes(data):
        entry_count = int.from_bytes(data[payload_start + 4:payload_start + 8], 'big')
        field_size = 4 if box_type == b'stco' else 8
        table_start = payload_start + 8
        for i in range(entry_count):
            pos = table_start + i * field_size
            if box_type == b'stco':
                value = int.from_bytes(data[pos:pos + 4], 'big') + delta
                if not 0 <= value <= 0xFFFFFFFF:
                    raise ValueError(f"stco offset overflow after patching: {value}")
                data[pos:pos + 4] = struct.pack('>I', value)
            else:
                value = int.from_bytes(data[pos:pos + 8], 'big') + delta
                if value < 0:
                    raise ValueError(f"co64 offset overflow after patching: {value}")
                data[pos:pos + 8] = struct.pack('>Q', value)
    return bytes(data)


def _walk_offset_boxes(data: bytearray, start: int = 0, end: Optional[int] = None):
    """深度优先遍历容器 box，yield ``(box_type, payload_start)``（只找 stco/co64）。

    只下钻容器型 box，避免把样本数据当 box 解析；meta 的 FullBox 前缀
    用与 video_meta._parse_meta 相同的探测逻辑跳过。
    """
    if end is None:
        end = len(data)
    offset = start
    while offset + 8 <= end:
        size = int.from_bytes(data[offset:offset + 4], 'big')
        # bytearray 切片不可哈希，转 bytes 再做 set 成员判断
        box_type = bytes(data[offset + 4:offset + 8])
        header_size = 8
        if size == 1:
            if offset + 16 > end:
                return
            size = int.from_bytes(data[offset + 8:offset + 16], 'big')
            header_size = 16
        elif size == 0:
            size = end - offset
        if size < header_size or offset + size > end:
            return
        payload_start, payload_end = offset + header_size, offset + size
        if box_type in _OFFSET_BOXES:
            yield box_type, payload_start
        if box_type in _CONTAINER_BOXES:
            nested_start = payload_start
            if box_type == b'meta' and bytes(data[payload_start + 4:payload_start + 8]) \
                    not in (b'hdlr', b'keys', b'ilst', b'free', b'mdta'):
                nested_start = payload_start + 4
            yield from _walk_offset_boxes(data, nested_start, payload_end)
        offset += size


def _verify_video_gps(temp_path: str, lat: float, lng: float, original_path: str) -> None:
    """写后校验：完整重解析临时文件，位置读回一致且关键元数据不丢失。"""
    new_meta = video_meta.extract_video_metadata(temp_path)
    location = new_meta.get('location')
    if not location:
        raise ValueError("GPS verification failed: no location read back from written video")
    if abs(location['latitude'] - lat) > 1e-4 or abs(location['longitude'] - lng) > 1e-4:
        raise ValueError(
            f"GPS verification failed: wrote ({lat}, {lng}), read back "
            f"({location['latitude']}, {location['longitude']})")

    # 关键元数据必须与原文件一致（防止 stco 修正或重建过程破坏结构）
    old_meta = video_meta.extract_video_metadata(original_path)
    for key in ('duration', 'width', 'height', 'fps', 'codec'):
        old_value, new_value = old_meta.get(key), new_meta.get(key)
        if old_value is not None and old_value != new_value:
            raise ValueError(
                f"Video structure verification failed for {key}: "
                f"original={old_value}, rewritten={new_value}")


def write_video_gps(file_path: str, latitude: float, longitude: float) -> None:
    """把 GPS 注入视频 ISO BMFF 容器，校验后原子替换原文件。

    仅支持 MP4/MOV/M4V/3GP；AVI/MKV/WEBM 抛 :class:`WriteBackUnsupported`。
    moov 在 mdat 之前（faststart）时同步修正全部 stco/co64 chunk offset。
    """
    if not video_meta.is_isobmff_file(file_path):
        raise WriteBackUnsupported(f"Unsupported video format for GPS write-back: {file_path}")
    if not os.path.exists(file_path):
        raise WriteBackUnsupported(f"File not found: {file_path}")

    lat, lng = _validate_coordinates(latitude, longitude)
    iso_string = _format_iso6709(lat, lng)

    file_size = os.path.getsize(file_path)
    if file_size <= 8:
        raise WriteBackUnsupported(f"File too small to be a valid container: {file_path}")

    temp_path = _make_temp_path(file_path)
    try:
        with disk_budget.slots(file_path, temp_path):
            with open(file_path, 'rb') as f:
                layout = {}
                # 记录 box 起点（含 8 字节头）而非 payload 起点，布局判定需要
                for box_type, p_start, p_end in video_meta._iter_boxes(f, 0, file_size):
                    layout.setdefault(box_type, (p_start - 8, p_end))
                if b'moov' not in layout:
                    raise WriteBackUnsupported(f"No moov box in {file_path}")
                moov_start, moov_end = layout[b'moov']

                new_moov = _rebuild_moov(f, moov_start + 8, moov_end, iso_string)
                old_moov_len = moov_end - moov_start
                delta = len(new_moov) - old_moov_len

                # moov 长度变化（delta≠0）时，moov 之后的字节整体后移 delta。
                # stco/co64 表项是文件绝对偏移、指向 mdat 中的样本数据：
                # * mdat 在 moov 之后（faststart：moov 前置以便流播放）——
                #   mdat 后移，全表项必须 +delta，否则视频损坏；
                # * mdat 在 moov 之前（手机直录布局，moov 在文件尾）——
                #   后移的只有 moov 之后的 box（不含 offset 表），无需修正。
                mdat_after_moov = b'mdat' not in layout or layout[b'mdat'][0] > moov_start
                if mdat_after_moov and delta != 0:
                    new_moov = _patch_chunk_offsets(new_moov, delta)

                with open(temp_path, 'wb') as out:
                    f.seek(0)
                    _copy_stream(f, out, moov_start)      # moov 前的前缀（ftyp 等）
                    out.write(new_moov)
                    f.seek(moov_end)
                    _copy_stream(f, out, file_size - moov_end)

        _verify_video_gps(temp_path, lat, lng, file_path)
        _atomic_replace(temp_path, file_path)
    except WriteBackUnsupported:
        _cleanup(temp_path)
        raise
    except Exception as e:
        _cleanup(temp_path)
        raise RuntimeError(f"Failed to write GPS into {file_path}: {e}") from e
    finally:
        _cleanup(temp_path)


# --------------------------------------------------------------------------- #
# 对外统一入口
# --------------------------------------------------------------------------- #

def write_gps_to_file(file_path: str, latitude: float, longitude: float) -> None:
    """按文件类型分派写回。不支持的格式抛 WriteBackUnsupported。"""
    ext = os.path.splitext(file_path)[1].lower()
    if ext in _IMAGE_WRITE_EXTENSIONS:
        write_image_gps(file_path, latitude, longitude)
    elif ext in _VIDEO_WRITE_EXTENSIONS:
        write_video_gps(file_path, latitude, longitude)
    else:
        raise WriteBackUnsupported(f"Unsupported file type for GPS write-back: {ext}")


def update_photo_md5(db, photo) -> Optional[str]:
    """写回成功后重算并更新 ``photos.md5`` 与 ``size``。

    返回新 md5；文件不存在等 IO 失败返回 None（不抛异常，避免影响主流程）。
    调用方负责 commit。
    """
    from app.utils.hash import calculate_file_md5
    try:
        file_path = photo.file_path
    except ValueError:
        # portable 模式下存储引用损坏时 file_path 取值会抛 ValueError
        logger.warning("Failed to resolve file path for md5 update of photo %s", photo.id)
        return None
    if not file_path or not os.path.exists(file_path):
        return None
    try:
        new_md5 = calculate_file_md5(file_path)
    except Exception:
        logger.warning("Failed to recalculate md5 for %s", photo.id, exc_info=True)
        return None
    if new_md5:
        photo.md5 = new_md5
        photo.size = os.path.getsize(file_path)
        db.add(photo)
    return new_md5 or None
