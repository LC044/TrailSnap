"""Nightly watch 2026-11-22 · app/crud/location.py::_rank_rows_for_reference 盲区。

_rank_rows_for_reference 决定「参考照片」模式下候选照片的排序：先按相似度/距离/
时间跨度打分，再按拍摄时间兜底排序。它还必须过滤掉朝向不一致的照片。

覆盖：
- 没有参考照片 -> 原样返回（edge）
- 朝向不一致的候选被剔除（edge）
- 距离更近的候选排在前面（happy）
"""

from datetime import datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.crud.location import _rank_rows_for_reference

pytestmark = [pytest.mark.smoke]


def _photo(hour, orientation=None):
    # 朝向由宽高比推导：横图 > 1.1，竖图 < 0.9。
    width, height = (200, 100) if orientation == "landscape" else (100, 200)
    return SimpleNamespace(
        id=uuid4(),
        photo_time=datetime(2024, 6, 1, hour, 0, 0),
        metadata_info={},
        width=width,
        height=height,
    )


def _metadata(latitude, longitude):
    return SimpleNamespace(latitude=latitude, longitude=longitude)


def test_rank_rows_without_a_reference_returns_the_rows(face_sqlite_session):
    rows = [(_photo(8), _metadata(30.0, 120.0))]

    assert _rank_rows_for_reference(face_sqlite_session, rows, None) == rows


def test_rank_rows_drops_incompatible_orientations(face_sqlite_session):
    reference = (_photo(8, "portrait"), _metadata(30.0, 120.0))
    same = (_photo(9, "portrait"), _metadata(30.0, 120.0))
    other = (_photo(9, "landscape"), _metadata(30.0, 120.0))

    ranked = _rank_rows_for_reference(face_sqlite_session, [other, same], reference)

    assert [row[0] for row in ranked] == [same[0]]


def test_rank_rows_prefers_the_closer_candidate(face_sqlite_session):
    reference = (_photo(8), _metadata(30.0, 120.0))
    near = (_photo(9), _metadata(30.0, 120.001))
    far = (_photo(9), _metadata(31.0, 121.0))

    ranked = _rank_rows_for_reference(face_sqlite_session, [far, near], reference)

    assert ranked[0][0] is near[0]


