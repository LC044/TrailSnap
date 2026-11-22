"""Nightly watch 2026-11-22: ``app/service/cleanup_index.py``::CleanupIndex.shard_rows 盲区。

清理扫描把向量按 label 分片（每片 SHARD_SIZE 行）存进本地 sqlite 缓存，
``shard_rows`` 负责把某一片的行原样读回来，用于重建 HNSW 索引。
分片边界一旦算错，重建的索引就会漏行或重复行，导致「相似照片」分组出错。

本文件覆盖：
- 落在同一分片内的行被完整读出（happy）
- 结果按 label 升序返回（happy）
- 分片边界上的 label（SHARD_SIZE / SHARD_SIZE+1）归属正确（edge）
- 空分片返回空列表（edge）
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.service.cleanup_index import SHARD_SIZE, CleanupIndex


pytestmark = [pytest.mark.smoke]


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _insert(index, label, photo_id):
    index.cache.execute(
        "INSERT INTO vectors (label, photo, digest, vector, generation) VALUES (?,?,?,?,1)",
        (label, str(photo_id), None, b"\x00" * 8),
    )
    index.cache.commit()


def test_shard_rows_returns_every_row_inside_the_shard(db, tmp_path):
    with CleanupIndex(db, uuid4(), "test-model", root=tmp_path) as index:
        first, second = uuid4(), uuid4()
        _insert(index, 1, first)
        _insert(index, 2, second)

        rows = index.shard_rows(0)

        assert [row[1] for row in rows] == [str(first), str(second)]


def test_shard_rows_returns_rows_in_label_order(db, tmp_path):
    with CleanupIndex(db, uuid4(), "test-model", root=tmp_path) as index:
        ordered = [uuid4() for _ in range(3)]
        for offset, photo_id in enumerate(reversed(ordered), start=1):
            _insert(index, offset, photo_id)

        rows = index.shard_rows(0)

        assert [row[0] for row in rows] == [1, 2, 3]


def test_shard_rows_respects_the_shard_boundary(db, tmp_path):
    with CleanupIndex(db, uuid4(), "test-model", root=tmp_path) as index:
        last_of_first = uuid4()
        first_of_second = uuid4()
        _insert(index, SHARD_SIZE, last_of_first)
        _insert(index, SHARD_SIZE + 1, first_of_second)

        assert [row[1] for row in index.shard_rows(0)] == [str(last_of_first)]
        assert [row[1] for row in index.shard_rows(1)] == [str(first_of_second)]


def test_shard_rows_returns_an_empty_list_for_an_unused_shard(db, tmp_path):
    with CleanupIndex(db, uuid4(), "test-model", root=tmp_path) as index:
        _insert(index, 1, uuid4())

        assert index.shard_rows(7) == []
