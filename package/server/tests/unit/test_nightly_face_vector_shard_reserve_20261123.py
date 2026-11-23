"""Nightly watch 2026-11-23 - app/service/face_vector_cache.py 的 _Shard._reserve 盲区。

_Shard 是 SQLite 后端的人脸向量缓存：一个 append-only 的
face_id -> 归一化 embedding 矩阵。_reserve 负责按需扩容缓冲区，
采用几何增长以保证重复增量追加的摊销复杂度是 O(1)。

本文件覆盖：

- 首次 reserve 固定维度并至少分配 _MIN_SHARD_CAPACITY 行（happy）
- 请求量大于下限时按请求量分配（edge）
- 容量足够时保持容量不变（happy）
- 扩容后保留已写入的行与 id（happy）
- 扩容遵循几何增长（edge）
"""

import pytest

from app.service.face_vector_cache import _MIN_SHARD_CAPACITY, _Shard

pytestmark = [pytest.mark.smoke]


def test_reserve_fixes_the_dimension_and_allocates_the_minimum():
    shard = _Shard()

    shard._reserve(3, 4)

    assert shard._dim == 4
    assert shard.capacity == _MIN_SHARD_CAPACITY
    assert shard.size == 0


def test_reserve_allocates_at_least_the_requested_rows():
    shard = _Shard()

    shard._reserve(_MIN_SHARD_CAPACITY + 20, 2)

    assert shard.capacity == _MIN_SHARD_CAPACITY + 20


def test_reserve_keeps_the_capacity_when_it_already_fits():
    shard = _Shard()
    shard._reserve(4, 3)
    capacity = shard.capacity

    shard._reserve(10, 3)

    assert shard.capacity == capacity


def test_reserve_grows_geometrically():
    shard = _Shard()
    shard._reserve(4, 3)
    capacity = shard.capacity

    shard._reserve(capacity + 1, 3)

    assert shard.capacity == max(capacity + 1, capacity * 2)


def test_reserve_preserves_rows_and_ids_when_it_grows():
    shard = _Shard()
    shard.append([7, 9], [[1.0, 0.0], [0.0, 1.0]])
    assert shard.size == 2

    shard._reserve(_MIN_SHARD_CAPACITY * 2, 2)

    assert shard.size == 2
    assert list(shard.ids) == [7, 9]
    assert shard.matrix.shape == (2, 2)


def test_reserve_ignores_a_conflicting_dimension():
    # 维度只在首次 reserve 时确定；后续传入不同维度不应改变已分配的缓冲区。
    shard = _Shard()
    shard._reserve(2, 4)

    shard._reserve(2, 8)

    assert shard._dim == 4
    assert shard.matrix.shape[1] == 4
