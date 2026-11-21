"""夜间盲区补测：GPS 写回时 moov 重建与位置原子注入。

覆盖 app/utils/gps_writeback.py 的 ``_rebuild_moov``（此前未被任何单测按名引用）。
调用约定与真实写入路径一致：传入的是 moov **payload** 区间 [header+8, moov_end)。
"""
import io
import struct

import pytest

from app.utils import gps_writeback

pytestmark = [pytest.mark.smoke, pytest.mark.regression]

ISO = "+39.90420+116.40740/"


def _box(box_type: bytes, body: bytes) -> bytes:
    return struct.pack(">I", len(body) + 8) + box_type + body


def _iter_child_types(moov_bytes: bytes):
    """遍历重建后 moov 的直接子 box 类型（跳过 8 字节 moov 头）。"""
    offset = 8
    while offset + 8 <= len(moov_bytes):
        size = struct.unpack(">I", moov_bytes[offset:offset + 4])[0]
        yield moov_bytes[offset + 4:offset + 8]
        offset += size


def test_rebuild_moov_replaces_udta_and_keeps_other_atoms():
    """既有 udta 必须原位替换出 ©xyz，其余既有原子保留；meta 被换成含 ISO6709 的新盒。"""
    mvhd = _box(b"mvhd", b"\x00" * 20)
    udta = _box(b"udta", _box(b"\xa9nam", b"legacy"))
    meta = _box(b"meta", b"\x00" * 16)
    moov = _box(b"moov", mvhd + udta + meta)

    rebuilt = gps_writeback._rebuild_moov(io.BytesIO(moov), 8, len(moov), ISO)

    assert struct.unpack(">I", rebuilt[:4])[0] == len(rebuilt)
    assert rebuilt[4:8] == b"moov"
    assert list(_iter_child_types(rebuilt)) == [b"mvhd", b"udta", b"meta"]
    # 既有非位置原子保留，位置原子以 ISO6709 字符串写入
    assert b"legacy" in rebuilt
    assert b"\xa9xyz" in rebuilt
    assert ISO.encode("ascii") in rebuilt


def test_rebuild_moov_creates_missing_udta_and_meta():
    """没有 udta / meta 时必须新建两个子 box 并注入位置原子。"""
    mvhd = _box(b"mvhd", b"\x00" * 20)
    moov = _box(b"moov", mvhd)

    rebuilt = gps_writeback._rebuild_moov(io.BytesIO(moov), 8, len(moov), ISO)

    assert list(_iter_child_types(rebuilt)) == [b"mvhd", b"udta", b"meta"]
    assert ISO.encode("ascii") in rebuilt
    assert b"xyz" in rebuilt


def test_rebuild_moov_is_stable_when_applied_twice():
    """对重建结果再重建一次，子 box 顺序与数量必须保持一致（不重复嵌套）。"""
    moov = _box(b"moov", _box(b"mvhd", b"\x00" * 20) + _box(b"udta", b"\x00" * 8))

    first = gps_writeback._rebuild_moov(io.BytesIO(moov), 8, len(moov), ISO)
    second = gps_writeback._rebuild_moov(io.BytesIO(first), 8, len(first), ISO)

    assert list(_iter_child_types(first)) == list(_iter_child_types(second))
    assert list(_iter_child_types(second)) == [b"mvhd", b"udta", b"meta"]
