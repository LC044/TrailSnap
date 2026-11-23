"""Nightly watch 2026-11-22 · app/utils/video_meta.py::_parse_video_track 盲区。

_parse_video_track 从 moov 中找出第一条 handler 为 ``vide`` 的轨道，解析
尺寸 / 旋转角 / 时长 / codec / 帧率。这是纯 Python 的 ISO BMFF 解析，
需要真实的 box 嵌套结构才能验证；这里用手工构造的最小 MP4 fixture 覆盖：

- happy：完整轨道 -> 宽高 / codec / 时长 / 帧率
- edge：tkhd 里的 90 度旋转矩阵 -> 宽高互换
- edge：非视频轨道（soun）被跳过 -> 空结果
- error：没有 trak -> 空结果
"""

import io
import struct

import pytest

from app.utils import video_meta

pytestmark = [pytest.mark.smoke]


def _box(box_type: bytes, payload: bytes) -> bytes:
    """构造一个 ISO BMFF box（size 含 8 字节头）。"""
    return struct.pack(">I", len(payload) + 8) + box_type + payload


def _tkhd(width: int, height: int, rotation_deg: int = 0) -> bytes:
    """构造 tkhd payload：矩阵首元素决定旋转角，宽高为 16.16 定点。"""
    import math

    radians = math.radians(rotation_deg)
    a = int(round(math.cos(radians) * 65536))
    b = int(round(math.sin(radians) * 65536))
    matrix = [a, b, 0, 0, 0, 0x00010000, 0, 0, 0x40000000]
    payload = bytearray()
    payload += bytes([0]) + b"\x00\x00\x00"          # version 0 + flags
    payload += b"\x00" * 8                            # creation / modification
    payload += struct.pack(">I", 1)                   # track_id
    payload += b"\x00" * 4                            # reserved
    payload += b"\x00" * 4                            # duration
    payload += b"\x00" * 8                            # reserved
    payload += struct.pack(">h", 0)                   # layer
    payload += struct.pack(">h", 0)                   # alternate_group
    payload += struct.pack(">h", 0)                   # volume
    payload += struct.pack(">h", 0)                   # reserved
    for value in matrix:
        payload += struct.pack(">i", value)
    payload += struct.pack(">I", width << 16)
    payload += struct.pack(">I", height << 16)
    return bytes(payload)


def _mdhd(timescale: int, duration: int) -> bytes:
    payload = bytearray()
    payload += bytes([0]) + b"\x00\x00\x00"
    payload += b"\x00" * 8                            # creation / modification
    payload += struct.pack(">I", timescale)
    payload += struct.pack(">I", duration)
    payload += b"\x00" * 4
    return bytes(payload)


def _hdlr(handler: bytes) -> bytes:
    payload = bytearray()
    payload += bytes([0]) + b"\x00\x00\x00"
    payload += b"\x00" * 4                            # pre_defined
    payload += handler                                # handler_type
    payload += b"\x00" * 12
    return bytes(payload)


def _stsd(codec: bytes) -> bytes:
    payload = bytearray()
    payload += bytes([0]) + b"\x00\x00\x00"
    payload += struct.pack(">I", 1)                   # entry_count
    payload += b"\x00" * 4                            # sample entry size
    payload += codec                                  # format
    payload += b"\x00" * 8
    return bytes(payload)


def _stsz(sample_count: int) -> bytes:
    payload = bytearray()
    payload += bytes([0]) + b"\x00\x00\x00"
    payload += struct.pack(">I", 0)                   # sample_size
    payload += struct.pack(">I", sample_count)
    return bytes(payload)


def _video_track(width=1920, height=1080, rotation=0, timescale=1000,
                 duration=4000, codec=b"avc1", samples=120) -> bytes:
    mdia = _box(b"mdia", b"".join([
        _box(b"hdlr", _hdlr(b"vide")),
        _box(b"mdhd", _mdhd(timescale, duration)),
        _box(b"minf", _box(b"stbl", b"".join([
            _box(b"stsd", _stsd(codec)),
            _box(b"stsz", _stsz(samples)),
        ]))),
    ]))
    return _box(b"trak", b"".join([
        _box(b"tkhd", _tkhd(width, height, rotation)),
        mdia,
    ]))


def _parse(moov_payload: bytes) -> dict:
    """把 moov payload 塞进一个文件流，返回 _parse_video_track 的结果。"""
    stream = io.BytesIO(_box(b"moov", moov_payload))
    stream.seek(0)
    size = len(stream.getvalue())
    moov_start, moov_end = video_meta._find_box(stream, 0, size, (b"moov",))
    return video_meta._parse_video_track(stream, moov_start, moov_end)


def test_parse_video_track_reads_dimensions_codec_duration_and_fps():
    info = _parse(_video_track())

    assert info["width"] == 1920
    assert info["height"] == 1080
    assert info["codec"] == "avc1"
    # 4000 / timescale 1000 = 4 秒
    assert info["duration"] == pytest.approx(4.0)
    # 120 帧 / 4 秒 = 30 fps
    assert info["fps"] == pytest.approx(30.0)


def test_parse_video_track_swaps_width_and_height_for_a_90_degree_rotation():
    info = _parse(_video_track(rotation=90))

    assert info["rotation"] == 90
    assert info["width"] == 1080
    assert info["height"] == 1920


def test_parse_video_track_ignores_a_non_video_track():
    audio_mdia = _box(b"mdia", _box(b"hdlr", _hdlr(b"soun")))
    audio_trak = _box(b"trak", audio_mdia)

    info = _parse(audio_trak)

    assert info == {}


def test_parse_video_track_returns_nothing_when_the_moov_has_no_track():
    assert _parse(_box(b"mvhd", b"\x00" * 20)) == {}


def test_parse_video_track_omits_fps_when_the_sample_count_is_zero():
    info = _parse(_video_track(samples=0))

    assert "fps" not in info
    assert info["width"] == 1920

