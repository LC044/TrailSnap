"""Nightly watch 2026-11-23 - app/service/face_appearance_clusters.py 的 ClusterIndex ANN 盲区。

人脸聚类的候选检索在库变大后必须走 HNSW 近似最近邻，否则每个候选都要和
全库做一次矩阵乘法。ClusterIndex._enable_ann 在行数达到 256 时才建索引，
upsert 负责把新增/改锚点的行同步进索引。

本文件覆盖：

- 行数不足 256 时不建 ANN 索引（edge）
- 达到 256 行时建立索引且条目数与行数一致（happy）
- 索引建立后 select 仍能命中正确的人物（happy）
- upsert 新增一行后索引条目数同步增加（happy）
- upsert 改写已有行的锚点不会重复计数（edge）
"""

import numpy as np
import pytest

from app.service.face_appearance_clusters import ClusterIndex

pytestmark = [pytest.mark.smoke]

_DIM = 512
_ANN_THRESHOLD = 256


def _vector(position: int) -> list[float]:
    vector = [0.0] * _DIM
    vector[position] = 1.0
    return vector


def _rows(count: int) -> list[dict]:
    return [
        {"id": f"cluster-{index}", "identity": f"identity-{index}",
         "center": _vector(index), "anchor": _vector(index), "revision": 0}
        for index in range(count)
    ]


def test_small_index_does_not_build_an_ann_index():
    index = ClusterIndex(_rows(_ANN_THRESHOLD - 1))

    assert index.ann is None
    assert len(index.rows) == _ANN_THRESHOLD - 1


def test_ann_index_is_built_once_the_threshold_is_reached():
    index = ClusterIndex(_rows(_ANN_THRESHOLD))

    assert index.ann is not None
    assert index.ann.get_current_count() == _ANN_THRESHOLD


def test_select_finds_the_matching_identity_through_the_ann_index():
    index = ClusterIndex(_rows(_ANN_THRESHOLD))

    best = index.select(np.asarray(_vector(7), dtype=np.float32), 0.1)

    assert best is not None
    assert best["identity"] == "identity-7"


def test_upsert_adds_the_new_row_to_the_ann_index():
    index = ClusterIndex(_rows(_ANN_THRESHOLD))

    index.upsert({"id": "cluster-new", "identity": "identity-new",
                  "center": _vector(_ANN_THRESHOLD), "anchor": _vector(_ANN_THRESHOLD),
                  "revision": 0})

    assert index.ann.get_current_count() == _ANN_THRESHOLD + 1
    assert len(index.rows) == _ANN_THRESHOLD + 1


def test_upsert_of_an_existing_row_does_not_duplicate_the_anchor():
    index = ClusterIndex(_rows(_ANN_THRESHOLD))
    row = index.rows[3]

    index.upsert({"id": row["id"], "identity": row["identity"], "index": row["index"],
                  "center": _vector(3), "anchor": _vector(3), "revision": 1})

    assert index.ann.get_current_count() == _ANN_THRESHOLD
    assert len(index.rows) == _ANN_THRESHOLD
