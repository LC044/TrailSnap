"""Nightly watch 2026-11-24 — app/utils/video_meta.py 边界分支补测。

覆盖既有测试未触达的畸形输入分支：
* 各 atom 解析器遇到 size < 8 的畸形 box 时应立即停止而不是抛异常。
* mdhd / mvhd / tkhd / stsd 的版本与长度校验分支。
* ilst data box 的 UTF-16 解码失败、控制字符与 float64 类型。
* meta 下的 udta 嵌套 atom。

全部使用代码构造字节流，不依赖媒体样本文件。
"""

from __future__ import annotations

import struct

import pytest

from app.utils import video_meta as vm


pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


def _box(box_type: bytes, payload: bytes = b"") -> bytes:
    return (len(payload) + 8).to_bytes(4, "big") + box_type + payload


def _data_box(type_indicator: int, value: bytes) -> bytes:
    """ilst 条目内部的 data box（4 字节类型 + 4 字节保留 + 值）。"""
    inner = type_indicator.to_bytes(4, "big") + b"\x00\x00\x00\x00" + value
    return _box(b"data", inner)


# --------------------------------------------------------------------------- #
# 畸形 size：解析器必须停止而不是抛异常
# --------------------------------------------------------------------------- #

def test_parse_udta_stops_on_malformed_box_size():
    """udta 里出现 size < 8 的原子时立刻停止解析。"""
    payload = (2).to_bytes(4, "big") + b"udta"
    assert vm._parse_udta(payload) == {}


def test_parse_keys_stops_on_malformed_box_size():
    """meta/keys 表里出现 size < 8 的条目时立刻停止解析。"""
    payload = (
        (8).to_bytes(4, "big")
        + b"keys"
        + (1).to_bytes(4, "big")
        + (2).to_bytes(4, "big")
        + b"mdta"
    )
    assert vm._parse_keys(payload) == []


def test_parse_data_box_stops_on_malformed_box_size():
    """ilst 的 data box 尺寸非法时返回 None。"""
    body = (2).to_bytes(4, "big") + b"data"
    assert vm._parse_data_box(body) is None


def test_parse_ilst_stops_on_malformed_box_size():
    """ilst 条目尺寸非法时返回空字典。"""
    payload = (2).to_bytes(4, "big") + b"xxxx"
    assert vm._parse_ilst(payload, []) == {}


# --------------------------------------------------------------------------- #
# data box 的值类型
# --------------------------------------------------------------------------- #

def test_parse_data_box_reads_float64_values():
    """type indicator 24（float64）应还原成 float。"""
    assert vm._parse_data_box(_data_box(24, struct.pack(">d", 1.5))) == pytest.approx(1.5)


def test_parse_data_box_rejects_broken_utf16_payload():
    """UTF-16 负载字节数为奇数时解码失败，返回 None。"""
    assert vm._parse_data_box(_data_box(2, b"\x00")) is None


def test_parse_data_box_rejects_utf16_with_control_chars():
    """UTF-16 文本里含控制字符时视为二进制，返回 None。"""
    assert vm._parse_data_box(_data_box(2, b"\x00\x07")) is None


def test_decode_text_drops_oversized_payload():
    """超过上限的文本负载直接丢弃，不会读进内存。"""
    assert vm._decode_text(b"a" * (vm._MAX_TEXT_BYTES + 1)) == ""


# --------------------------------------------------------------------------- #
# 头部 box 的版本与长度校验
# --------------------------------------------------------------------------- #

def test_parse_mvhd_rejects_short_version1_payload():
    """version=1 的 mvhd 至少需要 32 字节，否则返回空字典。"""
    assert vm._parse_mvhd(b"\x01" + b"\x00" * 10) == {}


def test_parse_tkhd_rejects_truncated_payload():
    """tkhd 少于 4 字节时返回空字典。"""
    assert vm._parse_tkhd(b"") == {}


def test_parse_mdhd_rejects_truncated_payload():
    """mdhd 少于 4 字节时返回空字典。"""
    assert vm._parse_mdhd(b"") == {}


def test_parse_mdhd_rejects_short_version1_payload():
    """version=1 的 mdhd 至少需要 32 字节。"""
    assert vm._parse_mdhd(b"\x01" + b"\x00" * 10) == {}


def test_parse_mdhd_rejects_short_version0_payload():
    """version=0 的 mdhd 至少需要 20 字节。"""
    assert vm._parse_mdhd(b"\x00" + b"\x00" * 10) == {}


def test_parse_stsd_codec_rejects_short_payload():
    """stsd 少于 16 字节时没有可用的 codec 四字符码。"""
    assert vm._parse_stsd_codec(b"x" * 10) is None


# --------------------------------------------------------------------------- #
# meta 嵌套
# --------------------------------------------------------------------------- #

def test_parse_meta_reads_nested_udta_atom():
    """meta 下的 udta 原子应被合并进结果。"""
    udta_body = _box(b"\xa9day", b"2026-11-24T10:00:00+08:00")
    payload = b"\x00\x00\x00\x00" + _box(b"udta", udta_body)
    tags = vm._parse_meta(payload)
    # udta 里保留原子原名，CreateDate 归一化由下游元数据映射完成。
    assert tags["\xa9day"] == "2026-11-24T10:00:00+08:00"

