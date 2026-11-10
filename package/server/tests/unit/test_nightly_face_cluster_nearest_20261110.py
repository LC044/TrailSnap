"""覆盖 app/service/face_cluster.py 的最近邻检索与空库分支。

`_sqlite_nearest_assigned_face` 是人脸归属时使用的向量化最近邻查询：
它从向量缓存里取相似度分块，按几何级数放大检索窗口，并在窗口内找出
**最近的、已归属身份的**人脸。窗口放大、跳过自身 id、全部候选都不合格
这几条分支此前完全没有覆盖，一旦写错会导致「明明有相似人脸却无法归并」。

`_sqlite_find_matching_face_ids` 在没有任何存活人脸时应直接返回空集合，
避免拿空矩阵做一次无意义的 matmul。
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

from app.service import face_cluster as fc
from app.service.face_vector_cache import face_vector_cache


pytestmark = [pytest.mark.smoke, pytest.mark.usefixtures("mock_appearance_for_fake_sessions")]


def _service():
    db = MagicMock(name="db")
    db.bind = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))
    return fc.FaceClusterService(db=db, user_id=None)


def _unit(dim=4, seed=0):
    rng = np.random.default_rng(seed)
    vec = rng.standard_normal(dim)
    return vec / np.linalg.norm(vec)


def _patch_similarities(monkeypatch, blocks):
    """让 face_vector_cache.similarities 返回给定的 (ids, scores) 分块。"""
    monkeypatch.setattr(
        face_vector_cache,
        "similarities",
        lambda _db, _owner, _queries: iter(blocks),
    )


def _patch_assigned(monkeypatch, service, mapping):
    monkeypatch.setattr(
        service,
        "_resolve_assigned_candidates",
        lambda _ids, _owner: dict(mapping),
    )


def test_returns_none_when_only_itself_is_assigned(monkeypatch):
    """除自己以外没有已归属人脸时直接返回 None。"""
    service = _service()
    chain = MagicMock()
    chain.first = MagicMock(return_value=None)
    monkeypatch.setattr(service, "_assigned_face_query", lambda _owner: chain)

    assert service._sqlite_nearest_assigned_face(_unit(), 7, None) is None


def test_skips_block_containing_only_self(monkeypatch):
    """候选分块里只有自己时被整块跳过，最终没有候选返回 None。"""
    service = _service()
    chain = MagicMock()
    chain.first = MagicMock(return_value=SimpleNamespace(id=7))
    monkeypatch.setattr(service, "_assigned_face_query", lambda _owner: chain)

    ids = np.array([7], dtype=np.int64)
    scores = np.array([[0.99]], dtype=np.float32)
    _patch_similarities(monkeypatch, [(ids, scores)])
    _patch_assigned(monkeypatch, service, {})

    assert service._sqlite_nearest_assigned_face(_unit(), 7, None) is None


def test_no_candidate_blocks_returns_none(monkeypatch):
    """缓存没有产出任何分块时返回 None。"""
    service = _service()
    chain = MagicMock()
    chain.first = MagicMock(return_value=SimpleNamespace(id=7))
    monkeypatch.setattr(service, "_assigned_face_query", lambda _owner: chain)

    _patch_similarities(monkeypatch, [])
    _patch_assigned(monkeypatch, service, {})

    assert service._sqlite_nearest_assigned_face(_unit(), 7, None) is None


def test_returns_nearest_assigned_candidate(monkeypatch):
    """窗口内第一个已归属候选即命中，距离按 1 - 相似度 计算。"""
    service = _service()
    chain = MagicMock()
    chain.first = MagicMock(return_value=SimpleNamespace(id=7))
    monkeypatch.setattr(service, "_assigned_face_query", lambda _owner: chain)

    ids = np.array([11, 12, 13], dtype=np.int64)
    scores = np.array([[0.90], [0.80], [0.70]], dtype=np.float32)
    _patch_similarities(monkeypatch, [(ids, scores)])
    _patch_assigned(monkeypatch, service, {12: "identity-b"})

    result = service._sqlite_nearest_assigned_face(_unit(), 7, None)

    assert result is not None
    face_id, identity_id, distance = result
    assert face_id == 12
    assert identity_id == "identity-b"
    assert distance == pytest.approx(0.2, abs=1e-6)


def test_grows_window_when_first_block_has_no_match(monkeypatch):
    """首批候选都不合格时按几何级数放大窗口，最终在扩大的窗口里命中。"""
    service = _service()
    chain = MagicMock()
    chain.first = MagicMock(return_value=SimpleNamespace(id=7))
    monkeypatch.setattr(service, "_assigned_face_query", lambda _owner: chain)

    total = fc._NEAREST_WINDOW + 5
    ids = np.arange(100, 100 + total, dtype=np.int64)
    scores = np.linspace(0.9, 0.1, total, dtype=np.float32).reshape(-1, 1)
    _patch_similarities(monkeypatch, [(ids, scores)])
    _patch_assigned(monkeypatch, service, {int(ids[-1]): "identity-late"})

    result = service._sqlite_nearest_assigned_face(_unit(), 7, None)

    assert result is not None
    assert result[0] == int(ids[-1])
    assert result[1] == "identity-late"


def test_returns_none_when_no_candidate_is_eligible(monkeypatch):
    """所有候选都无法归属时，窗口耗尽后返回 None。"""
    service = _service()
    chain = MagicMock()
    chain.first = MagicMock(return_value=SimpleNamespace(id=7))
    monkeypatch.setattr(service, "_assigned_face_query", lambda _owner: chain)

    ids = np.array([21, 22, 23], dtype=np.int64)
    scores = np.array([[0.9], [0.8], [0.7]], dtype=np.float32)
    _patch_similarities(monkeypatch, [(ids, scores)])
    _patch_assigned(monkeypatch, service, {})

    assert service._sqlite_nearest_assigned_face(_unit(), 7, None) is None


def test_find_matching_ids_returns_empty_without_live_faces(monkeypatch):
    """没有存活人脸时直接返回空集合，不做多余矩阵运算。"""
    service = _service()
    monkeypatch.setattr(service, "_live_face_ids", lambda _owner: np.array([], dtype=np.int64))

    def _boom(*_args, **_kwargs):
        raise AssertionError("similarities 不应被调用")

    monkeypatch.setattr(face_vector_cache, "similarities", _boom)

    assert service._sqlite_find_matching_face_ids([_unit()], None, 0.4) == set()

