"""Nightly watch 2026-11-23 · app/service/face_appearance_clusters.py 的 _promote_batch 盲区。

_promote_batch 负责把「成员足够多、且没有跨外观冲突」的未命名聚类提升为
可识别人物身份。本文件用真实 SQLite（face_sqlite_session）构造聚类 / 照片 / 人脸，
向量索引用桩对象替代，覆盖：

- 没有待提升聚类时直接返回，不写库（edge）
- 成员数量不足 minimum 时不提升（edge）
- 索引里存在跨外观冲突时不提升（error）
- 满足条件时创建身份并回写聚类与人脸（happy）
"""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.db.models.face import Face, FaceCluster, FaceIdentity
from app.db.models.photo import Photo
from app.db.models.user import User
from app.service import face_appearance_clusters as clusters

pytestmark = [pytest.mark.smoke]

_VECTOR = [0.0] * 512


class _StubIndex:
    """最小向量索引桩：只提供 _promote_batch 用到的三个成员。"""

    def __init__(self, rows, selected=None):
        self.rows = rows
        self.identities = set()
        self.selected = selected

    def select(self, vector, threshold, **kwargs):
        return self.selected


def _owner(db):
    user = User(id=uuid4(), username=f"owner-{uuid4().hex[:8]}", hashed_password="x")
    db.add(user)
    db.flush()
    return user


def _cluster(db, owner, faces=1):
    photo = Photo(id=uuid4(), filename="a.jpg", file_path="a.jpg", file_type="image",
                  owner_id=owner.id, width=10, height=10)
    db.add(photo)
    db.flush()
    cluster = FaceCluster(id=uuid4(), owner_id=owner.id, center=list(_VECTOR),
                          vector_sum=list(_VECTOR), face_count=faces, status="pending",
                          revision=1)
    db.add(cluster)
    db.flush()
    face = Face(photo_id=photo.id, face_cluster_id=cluster.id, face_feature=list(_VECTOR))
    db.add(face)
    db.flush()
    return cluster, face


def _stub_config(monkeypatch):
    monkeypatch.setattr(clusters.config_manager, "get_user_config", lambda *args: SimpleNamespace(
        ai=SimpleNamespace(face_identity_match_threshold=0.5, face_cluster_threshold=0.6)))


def test_promote_batch_ignores_clusters_that_already_have_an_identity(face_sqlite_session, monkeypatch):
    _stub_config(monkeypatch)
    owner = _owner(face_sqlite_session)
    cluster, face = _cluster(face_sqlite_session, owner)
    cluster.identity_id = uuid4()
    face_sqlite_session.flush()
    index = _StubIndex([{"id": cluster.id, "identity": None, "revision": 1}])

    clusters._promote_batch(face_sqlite_session, owner.id, {cluster.id: cluster},
                            {face.id: face}, 1, index)

    assert face_sqlite_session.query(FaceIdentity).count() == 0
    assert index.identities == set()


def test_promote_batch_skips_a_cluster_with_too_few_members(face_sqlite_session, monkeypatch):
    _stub_config(monkeypatch)
    owner = _owner(face_sqlite_session)
    cluster, face = _cluster(face_sqlite_session, owner)
    index = _StubIndex([{"id": cluster.id, "identity": None, "revision": 1}])

    clusters._promote_batch(face_sqlite_session, owner.id, {cluster.id: cluster},
                            {face.id: face}, 2, index)

    assert face_sqlite_session.query(FaceIdentity).count() == 0
    assert cluster.identity_id is None
    assert cluster.status == "pending"


def test_promote_batch_skips_a_cluster_that_links_to_another_appearance(face_sqlite_session, monkeypatch):
    """索引里已有同一外观时不能直接发布身份，避免把两个外观合并成一个。"""
    _stub_config(monkeypatch)
    owner = _owner(face_sqlite_session)
    cluster, face = _cluster(face_sqlite_session, owner)
    index = _StubIndex([{"id": cluster.id, "identity": None, "revision": 1}], selected=object())

    clusters._promote_batch(face_sqlite_session, owner.id, {cluster.id: cluster},
                            {face.id: face}, 1, index)

    assert face_sqlite_session.query(FaceIdentity).count() == 0
    assert cluster.identity_id is None


def test_promote_batch_publishes_an_identity_and_writes_it_back(face_sqlite_session, monkeypatch):
    _stub_config(monkeypatch)
    owner = _owner(face_sqlite_session)
    cluster, face = _cluster(face_sqlite_session, owner)
    index = _StubIndex([{"id": cluster.id, "identity": None, "revision": 1}])

    clusters._promote_batch(face_sqlite_session, owner.id, {cluster.id: cluster},
                            {face.id: face}, 1, index)

    identity = face_sqlite_session.query(FaceIdentity).one()
    assert identity.owner_id == owner.id
    assert identity.identity_name == "未命名"
    assert cluster.identity_id == identity.id
    assert cluster.status == "active"
    assert cluster.revision == 2
    assert index.identities == {identity.id}
    assert index.rows[0]["identity"] == identity.id
    assert index.rows[0]["revision"] == 2
    face_sqlite_session.refresh(face)
    assert face.face_identity_id == identity.id
