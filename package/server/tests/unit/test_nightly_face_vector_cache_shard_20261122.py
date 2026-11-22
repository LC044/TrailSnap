"""Nightly watch 2026-11-22 · app/service/face_vector_cache.py 分片键与内存预算盲区。

FaceVectorCache 以「owner 分片」缓存人脸向量：
- ``_shard_key(None)`` 使用全局分片键（非全局查询走这条路）；
- ``_allocated_rows`` 统计的是**已分配内存**的行数而不是逻辑行数，
  因为每个分片至少预留 _MIN_SHARD_CAPACITY 行，几十个小 owner 就能把
  内存钉死。淘汰逻辑据此计算预算。

本文件覆盖：
- 全局分片键与 per-owner 分片键互不混淆（happy）
- allocated_rows 按 capacity 而非 size 统计（edge）
- 淘汰保留正在使用的分片，把其它分片挤出预算（edge）
"""

from uuid import uuid4

import pytest

from app.service import face_vector_cache as cache_module
from app.service.face_vector_cache import FaceVectorCache

pytestmark = [pytest.mark.smoke]


def test_shard_key_uses_a_global_bucket_for_a_missing_owner():
    cache = FaceVectorCache()

    assert cache._shard_key(None) == cache_module._GLOBAL_KEY


def test_shard_key_is_stable_and_owner_specific():
    cache = FaceVectorCache()
    owner = uuid4()

    assert cache._shard_key(owner) == str(owner)
    assert cache._shard_key(owner) == cache._shard_key(owner)
    assert cache._shard_key(owner) != cache._shard_key(uuid4())


def test_allocated_rows_counts_reserved_capacity_not_logical_rows():
    cache = FaceVectorCache(max_rows=1000)
    shard = cache_module._Shard()
    # 逻辑上只有 1 行，但底层缓冲预留了多行
    shard._buffer = pytest.importorskip("numpy").zeros((128, 4), dtype="float32")
    shard._size = 1
    cache._shards["owner"] = shard

    assert shard.size == 1
    assert shard.capacity == 128
    assert cache._allocated_rows() == 128


def test_eviction_drops_the_least_recently_used_shard_first():
    cache = FaceVectorCache(max_rows=256)
    first = cache_module._Shard()
    second = cache_module._Shard()
    for shard in (first, second):
        shard._buffer = pytest.importorskip("numpy").zeros((128, 4), dtype="float32")
    cache._shards["a"] = first
    cache._shards["b"] = second

    # 预算是 256 行，再进一个新分片就超了 -> 必须淘汰一个旧分片。
    # 淘汰顺序是插入顺序（最久未用的先走），"a" 比 "b" 更早插入。
    cache._evict_until_fits(cache_module._MIN_SHARD_CAPACITY, "c")

    assert "c" not in cache._shards
    assert len(cache._shards) == 1
    assert "a" not in cache._shards
    assert "b" in cache._shards


def test_eviction_never_drops_the_shard_being_filled():
    cache = FaceVectorCache(max_rows=256)
    shard = cache_module._Shard()
    shard._buffer = pytest.importorskip("numpy").zeros((128, 4), dtype="float32")
    cache._shards["a"] = shard

    cache._evict_until_fits(cache_module._MIN_SHARD_CAPACITY, "a")

    assert "a" in cache._shards

