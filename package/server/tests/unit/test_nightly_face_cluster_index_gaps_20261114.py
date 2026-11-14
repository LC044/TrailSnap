# -*- coding: utf-8 -*-
"""Nightly watch 2026-11-14 round2 · 覆盖盲区补测（app/service/face_appearance_clusters.py）。

相对 2026-11-13 覆盖率基线，此前完全未触达的分支：
- ClusterIndex.upsert：写入行数超过容量时按倍数扩容并搬迁中心/锚点矩阵。
- ClusterIndex.batch_candidates：命中数超过 64 时只保留相似度最高的 64 个。
- _representative_samples：命中缓存直接返回；跳过非法特征；同一照片保留最近的一次。
- _samples_support：任一侧代表样本不足 2 个时直接判定为不支持合并。
- _unclustered_batch：SQLite 分支返回尚未聚类且特征非空的人脸。
- _write_members：SQLite 分支按簇写回 face_cluster_id / face_identity_id。
- rebuild_cluster：中心向量退化时回退到第一条有效人脸向量。
"""

from __future__ import annotations

import uuid

import numpy as np
import pytest

from app.db.models.face import Face, FaceCluster, FaceIdentity
from app.db.models.photo import FileType, Photo
from app.db.models.user import User
from app.service import face_appearance_clusters as clusters

pytestmark = [pytest.mark.smoke, pytest.mark.module_agent]


def _vector(seed: float) -> list:
    """构造一个确定性的 512 维单位向量。"""
    raw = np.arange(512, dtype=np.float64) + seed
    return (raw / np.linalg.norm(raw)).tolist()


@pytest.fixture
def owner(face_sqlite_session):
    db = face_sqlite_session
    user = User(id=uuid.uuid4(), username="cluster-owner", hashed_password="x", is_active=True)
    db.add(user)
    db.commit()
    return user


def _add_photo(db, owner, name="p.jpg"):
    photo = Photo(id=uuid.uuid4(), owner_id=owner.id, filename=name, file_path=name,
                  file_type=FileType.image, is_deleted=False)
    db.add(photo)
    db.flush()
    return photo


def _add_cluster(db, owner, identity_id=None):
    cluster = FaceCluster(id=uuid.uuid4(), owner_id=owner.id, identity_id=identity_id,
                          center=_vector(0.0), vector_sum=_vector(0.0),
                          face_count=0, status="pending", revision=1)
    db.add(cluster)
    db.flush()
    return cluster


# --------------------------------------------------------------------------- #
# ClusterIndex
# --------------------------------------------------------------------------- #


def test_cluster_index_grows_when_the_row_count_exceeds_the_capacity():
    index = clusters.ClusterIndex([])
    initial_capacity = index.capacity
    for step in range(initial_capacity + 1):
        index.upsert({"id": uuid.uuid4(), "identity": None,
                      "center": np.asarray(_vector(float(step)), dtype=np.float32),
                      "anchor": np.asarray(_vector(float(step)), dtype=np.float32),
                      "revision": 1})

    assert index.capacity == initial_capacity * 2
    assert len(index.rows) == initial_capacity + 1
    # 扩容后的矩阵仍然能正确写入最后一行
    last = index.rows[-1]["index"]
    assert index.centers.shape == (index.capacity, 512)
    assert np.isfinite(index.centers[last]).all()


def test_batch_candidates_keeps_at_most_sixty_four_matches():
    rows = []
    for step in range(80):
        rows.append({"id": uuid.uuid4(), "identity": None,
                     "center": np.asarray(_vector(float(step)), dtype=np.float32),
                     "anchor": np.asarray(_vector(float(step)), dtype=np.float32),
                     "revision": 1})
    index = clusters.ClusterIndex(rows)
    query = np.asarray(_vector(0.0), dtype=np.float32)

    candidates = index.batch_candidates([query], 0.99)

    assert len(candidates) == 1
    assert len(candidates[0]) <= 64


def test_batch_candidates_returns_empty_results_for_an_empty_index():
    index = clusters.ClusterIndex([])
    query = np.asarray(_vector(0.0), dtype=np.float32)
    candidates = index.batch_candidates([query], 0.9)
    assert len(candidates[0]) == 0


# --------------------------------------------------------------------------- #
# _representative_samples / _samples_support
# --------------------------------------------------------------------------- #


def test_representative_samples_returns_the_cached_array(face_sqlite_session, owner):
    db = face_sqlite_session
    cluster = _add_cluster(db, owner)
    db.commit()
    cache = {cluster.id: np.zeros((1, 512))}

    result = clusters._representative_samples(db, owner.id, cluster.id, np.zeros(512), cache)

    assert result is cache[cluster.id]


def test_representative_samples_skips_invalid_features(face_sqlite_session, owner):
    db = face_sqlite_session
    photo = _add_photo(db, owner)
    cluster = _add_cluster(db, owner)
    db.add(Face(photo_id=photo.id, face_cluster_id=cluster.id, face_feature=[0.0] * 512, is_deleted=False))
    db.commit()

    samples = clusters._representative_samples(db, owner.id, cluster.id, np.zeros(512), {})

    assert len(samples) == 0


def test_representative_samples_keeps_the_closest_face_per_photo(face_sqlite_session, owner):
    db = face_sqlite_session
    photo = _add_photo(db, owner)
    cluster = _add_cluster(db, owner)
    center = np.asarray(_vector(0.0))
    far = np.asarray(_vector(50.0))
    near = np.asarray(_vector(0.5))
    db.add(Face(photo_id=photo.id, face_cluster_id=cluster.id, face_feature=near.tolist(), is_deleted=False))
    db.add(Face(photo_id=photo.id, face_cluster_id=cluster.id, face_feature=far.tolist(), is_deleted=False))
    db.commit()

    samples = clusters._representative_samples(db, owner.id, cluster.id, center, {})

    assert len(samples) == 1
    assert np.allclose(samples[0], near)


def test_samples_support_requires_two_representatives_per_side(face_sqlite_session, owner):
    db = face_sqlite_session
    photo = _add_photo(db, owner)
    first = _add_cluster(db, owner)
    second = _add_cluster(db, owner)
    db.add(Face(photo_id=photo.id, face_cluster_id=first.id, face_feature=_vector(0.0), is_deleted=False))
    db.commit()

    supported = clusters._samples_support(
        db, owner.id, first.id, np.asarray(_vector(0.0)),
        second.id, np.asarray(_vector(0.0)), 0.4, {})

    assert supported is False


def test_samples_support_accepts_two_matching_clusters(face_sqlite_session, owner):
    db = face_sqlite_session
    first = _add_cluster(db, owner)
    second = _add_cluster(db, owner)
    for index in range(2):
        photo = _add_photo(db, owner, f"p{index}.jpg")
        db.add(Face(photo_id=photo.id, face_cluster_id=first.id,
                    face_feature=_vector(0.0), is_deleted=False))
        db.add(Face(photo_id=photo.id, face_cluster_id=second.id,
                    face_feature=_vector(0.0), is_deleted=False))
    db.commit()

    supported = clusters._samples_support(
        db, owner.id, first.id, np.asarray(_vector(0.0)),
        second.id, np.asarray(_vector(0.0)), 0.4, {})

    assert supported is True


# --------------------------------------------------------------------------- #
# _unclustered_batch / _write_members
# --------------------------------------------------------------------------- #


def test_unclustered_batch_returns_the_pending_faces_on_sqlite(face_sqlite_session, owner):
    db = face_sqlite_session
    photo = _add_photo(db, owner)
    db.add(Face(photo_id=photo.id, face_feature=_vector(1.0), is_deleted=False))
    db.commit()

    rows = clusters._unclustered_batch(db, owner.id, 0)

    assert len(rows) == 1
    assert len(rows[0].face_feature) == 512
    assert rows[0].face_identity_id is None


def test_unclustered_batch_skips_faces_that_already_have_a_cluster(face_sqlite_session, owner):
    db = face_sqlite_session
    photo = _add_photo(db, owner)
    cluster = _add_cluster(db, owner)
    db.add(Face(photo_id=photo.id, face_cluster_id=cluster.id,
                face_feature=_vector(1.0), is_deleted=False))
    db.commit()

    assert clusters._unclustered_batch(db, owner.id, 0) == []


def test_write_members_assigns_the_cluster_and_identity_on_sqlite(face_sqlite_session, owner):
    db = face_sqlite_session
    photo = _add_photo(db, owner)
    identity = FaceIdentity(id=uuid.uuid4(), owner_id=owner.id, identity_name="小李", is_deleted=False)
    db.add(identity)
    db.flush()
    face = Face(photo_id=photo.id, face_feature=_vector(1.0), is_deleted=False)
    db.add(face)
    db.flush()
    cluster = FaceCluster(id=uuid.uuid4(), owner_id=owner.id, identity_id=identity.id,
                          center=_vector(1.0), vector_sum=_vector(1.0),
                          face_count=1, status="active", revision=1)
    db.add(cluster)
    db.commit()

    clusters._write_members(db, {cluster.id: [face.id]}, {cluster.id: cluster})
    db.commit()

    db.refresh(face)
    assert face.face_cluster_id == cluster.id
    assert face.face_identity_id == identity.id


def test_write_members_is_a_noop_without_members(face_sqlite_session):
    db = face_sqlite_session
    assert clusters._write_members(db, {}, {}) is None


# --------------------------------------------------------------------------- #
# rebuild_cluster
# --------------------------------------------------------------------------- #


def test_rebuild_cluster_falls_back_to_the_first_valid_vector(face_sqlite_session, owner):
    db = face_sqlite_session
    photo = _add_photo(db, owner)
    base = np.asarray(_vector(3.0))
    db.add(Face(photo_id=photo.id, face_feature=base.tolist(), is_deleted=False))
    db.add(Face(photo_id=photo.id, face_feature=(-base).tolist(), is_deleted=False))
    db.flush()
    cluster = FaceCluster(id=uuid.uuid4(), owner_id=owner.id, identity_id=None,
                          center=_vector(9.0), vector_sum=_vector(9.0),
                          face_count=2, status="pending", revision=1)
    db.add(cluster)
    db.commit()
    db.query(Face).filter(Face.photo_id == photo.id).update(
        {Face.face_cluster_id: cluster.id}, synchronize_session=False)
    db.commit()

    clusters.rebuild_cluster(db, cluster.id)
    db.commit()

    # 两个成员向量互相抵消 => unit(total) 为 None，回退到第一条有效向量
    assert cluster.face_count == 2
    assert np.allclose(np.asarray(cluster.center), base)
