"""Nightly watch 2026-11-09: video metadata parser guard gaps.

Targets uncovered branches reported by the 2026-11-09 coverage snapshot for
``app/utils/video_meta.py``:

* ``_iter_boxes`` - truncated box header, truncated 64-bit largesize and a
  box whose payload start lies beyond the container end.
* ``_qt_time_to_datetime`` - out-of-range QuickTime timestamps degrade to None.

Every test exercises already-implemented behaviour; no production code changes.
"""

from __future__ import annotations

import pytest

from app.utils import video_meta

pytestmark = [pytest.mark.smoke]


class _ChunkedFile:
    """Minimal seekable reader that never returns more than ``limit`` bytes."""

    def __init__(self, data: bytes, limit: int):
        self._data = data
        self._limit = limit
        self._pos = 0

    def seek(self, offset: int, whence: int = 0):
        self._pos = offset
        return self._pos

    def tell(self):
        return self._pos

    def read(self, size: int = -1) -> bytes:
        if size is None or size < 0:
            size = len(self._data) - self._pos
        size = min(size, self._limit)
        chunk = self._data[self._pos:self._pos + size]
        self._pos += len(chunk)
        return chunk


def test_iter_boxes_stops_on_truncated_header():
    data = b"\x00\x00\x00\x10moov"

    assert list(video_meta._iter_boxes(_ChunkedFile(data, limit=4), 0, len(data))) == []


def test_iter_boxes_stops_on_truncated_largesize():
    data = b"\x00\x00\x00\x01moov\x00\x00\x00\x00\x00\x00\x00\x10"

    assert list(video_meta._iter_boxes(_ChunkedFile(data, limit=4), 0, len(data))) == []


def test_iter_boxes_stops_when_payload_starts_beyond_container():
    # 64-bit largesize claims 100 bytes but the container only holds 12.
    data = b"\x00\x00\x00\x01moov" + (100).to_bytes(8, "big")

    assert list(video_meta._iter_boxes(_ChunkedFile(data, limit=64), 0, 12)) == []


def test_qt_time_to_datetime_returns_none_for_out_of_range_timestamp():
    assert video_meta._qt_time_to_datetime(10 ** 12) is None
