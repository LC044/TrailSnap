"""Nightly watch 2026-11-24 · app/service/face_appearance_clusters.py 的合并护栏盲区。

这是连续第 5 轮遗留的待办：_merge_compact_pair 的两条拒绝分支一直没被覆盖，
因为它们既要求真实 ClusterIndex（anchor / center 对齐），又要求真实的
Face + Photo 成员行来核对 face_count。

本文件用真实 SQLite 会话 + 真实 FaceCluster / Face / Photo 行补齐：

- set_identity(): 已经属于该身份且已有簇时直接返回，不做任何写入 (L309)
- _merge_compact_pair(): 两簇向量和为零 -> 合并中心为空 -> 拒绝 (L335)
- _merge_compact_pair(): 实际成员数与 face_count 之和对不上 -> 拒绝 (L350)

这三条都是「宁可不合，也不要把簇合坏」的护栏。
"""

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import numpy as np
import pytest

from app.db.models.face import Face, FaceCluster
from app.db.models.photo import FileType, Photo
from app.db.models.user import User
from app.service import face_appearance_clusters as clusters

pytestmark = [pytest.mark.smoke, pytest.mark.module_album]


def _anchor():
    vector = [0.0] * 512
    vector[0] = 1.0
    return vector


def _index(rows):
    index = clusters.ClusterIndex(rows)
    return index, {row["id"]: row for row in index.rows}


@pytest.fixture
def owner(face_sqlite_session):
    db = face_sqlite_session
    user = User(id=uuid4(), username="cluster-owner", hashed_password="x")
    db.add(user)
    db.flush()
    return user


def test_set_identity_is_a_noop_for_an_unchanged_assignment():
    identity_id = uuid4()
    face = SimpleNamespace(face_identity_id=identity_id, face_cluster_id=uuid4())
    db = MagicMock()

    assert clusters.set_identity(db, face, identity_id, uuid4()) is None
    db.query.assert_not_called()
    db.commit.assert_not_called()


def test_merge_compact_pair_rejects_a_degenerate_center():
    anchor = _anchor()
    owner_id = uuid4()
    source = SimpleNamespace(
        id=uuid4(), vector_sum=[0.0] * 512, center=anchor, face_count=2,
        identity_id=None, status="active", revision=1,
    )
    target = SimpleNamespace(
        id=uuid4(), vector_sum=[0.0] * 512, center=anchor, face_count=2,
        identity_id=None, status="active", revision=1,
    )
    index, records = _index([
        {"id": source.id, "identity": None, "center": np.asarray(anchor, dtype=np.float32),
         "anchor": np.asarray(anchor, dtype=np.float32), "revision": 1},
        {"id": target.id, "identity": None, "center": np.asarray(anchor, dtype=np.float32),
         "anchor": np.asarray(anchor, dtype=np.float32), "revision": 1},
    ])

    merged = clusters._merge_compact_pair(
        MagicMock(), owner_id, source, target, index, records, 0.5, 0.6
    )

    assert merged is False
    # 拒绝合并时不得改写任何一方的聚合量。
    assert source.face_count == 2 and target.face_count == 2


def test_merge_compact_pair_rejects_a_member_count_mismatch(face_sqlite_session, owner):
    db = face_sqlite_session
    anchor = _anchor()
    photo = Photo(
        id=uuid4(), owner_id=owner.id, filename="p.jpg", file_path="/p.jpg",
        file_type=FileType.image, is_deleted=False,
    )
    db.add(photo)
    db.flush()
    source = FaceCluster(
        id=uuid4(), owner_id=owner.id, identity_id=None,
        center=anchor, vector_sum=anchor, face_count=2, status="active", revision=1,
    )
    target = FaceCluster(
        id=uuid4(), owner_id=owner.id, identity_id=None,
        center=anchor, vector_sum=anchor, face_count=2, status="active", revision=1,
    )
    db.add_all([source, target])
    db.flush()
    # 只落一个成员：真实成员数(1) 与 face_count 之和(4) 对不上，必须拒绝。
    db.add(Face(
        photo_id=photo.id, face_cluster_id=source.id, face_feature=anchor, is_deleted=False,
    ))
    db.flush()

    index, records = _index([
        {"id": source.id, "identity": None, "center": np.asarray(anchor, dtype=np.float32),
         "anchor": np.asarray(anchor, dtype=np.float32), "revision": 1},
        {"id": target.id, "identity": None, "center": np.asarray(anchor, dtype=np.float32),
         "anchor": np.asarray(anchor, dtype=np.float32), "revision": 1},
    ])

    merged = clusters._merge_compact_pair(
        db, owner.id, source, target, index, records, 0.5, 0.6
    )

    assert merged is False
    assert source.face_count == 2
    assert target.face_count == 2
