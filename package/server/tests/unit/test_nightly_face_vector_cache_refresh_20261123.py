"""Nightly watch 2026-11-23 - app/service/face_vector_cache.py 的 _refresh 盲区。

SQLite 没有 pgvector 的 HNSW 索引，人脸相似度只能把 embedding 读进内存。
FaceVectorCache._refresh 负责把某个 owner 的 face 行流式装进分片：

- 空库时返回空分片
- 有数据时把行装进分片并做 L2 归一化
- 增量水位（max_face_id）保证第二次刷新只补新行
- owner 之间的数据互不串台
- 单个 owner 超过上限时返回 None 并记住该 owner，避免反复抖动

本文件用真实 SQLite 会话覆盖以上 5 组行为。
"""

from uuid import uuid4

import numpy as np
import pytest

from app.db.models.face import Face
from app.db.models.photo import FileType, Photo
from app.db.models.user import User
from app.service.face_vector_cache import FaceVectorCache

pytestmark = [pytest.mark.smoke]


def _owner(db, name="owner"):
    user = User(id=uuid4(), username=f"{name}-{uuid4().hex[:8]}", hashed_password="x")
    db.add(user)
    db.flush()
    return user


def _photo(db, owner, name="p.jpg"):
    photo = Photo(id=uuid4(), owner_id=owner.id, filename=name, file_path=f"/{name}",
                  file_type=FileType.image, size=1)
    db.add(photo)
    db.flush()
    return photo


def _face(db, photo, vector):
    face = Face(photo_id=photo.id, face_feature=list(vector))
    db.add(face)
    db.flush()
    return face


def test_refresh_returns_an_empty_shard_for_an_empty_library(face_sqlite_session):
    db = face_sqlite_session
    owner = _owner(db)
    db.commit()
    cache = FaceVectorCache()

    shard = cache._refresh(db, owner.id)

    assert shard is not None
    assert shard.size == 0
    assert cache.stats()["rows"] == 0


def test_refresh_loads_rows_and_normalises_the_matrix(face_sqlite_session):
    db = face_sqlite_session
    owner = _owner(db)
    photo = _photo(db, owner)
    face = _face(db, photo, [3.0] + [0.0] * 511)
    db.commit()
    cache = FaceVectorCache()

    shard = cache._refresh(db, owner.id)

    assert shard is not None
    assert shard.size == 1
    assert list(shard.ids) == [face.id]
    assert np.allclose(shard.matrix[0][0], 1.0)


def test_refresh_is_incremental_and_keeps_earlier_rows(face_sqlite_session):
    db = face_sqlite_session
    owner = _owner(db)
    photo = _photo(db, owner)
    first = _face(db, photo, [1.0] + [0.0] * 511)
    db.commit()
    cache = FaceVectorCache()

    shard = cache._refresh(db, owner.id)
    assert shard.size == 1

    second = _face(db, photo, [0.0, 1.0] + [0.0] * 510)
    db.commit()

    shard = cache._refresh(db, owner.id)
    assert shard.size == 2
    assert list(shard.ids) == [first.id, second.id]


def test_refresh_never_leaks_another_owners_faces(face_sqlite_session):
    db = face_sqlite_session
    owner = _owner(db, "mine")
    other = _owner(db, "other")
    mine_photo = _photo(db, owner, "mine.jpg")
    other_photo = _photo(db, other, "other.jpg")
    mine = _face(db, mine_photo, [1.0] + [0.0] * 511)
    _face(db, other_photo, [0.0, 1.0] + [0.0] * 510)
    db.commit()
    cache = FaceVectorCache()

    shard = cache._refresh(db, owner.id)

    assert shard is not None
    assert list(shard.ids) == [mine.id]


def test_refresh_returns_none_and_remembers_an_oversized_owner(face_sqlite_session):
    db = face_sqlite_session
    owner = _owner(db)
    photo = _photo(db, owner)
    _face(db, photo, [1.0] + [0.0] * 511)
    _face(db, photo, [0.0, 1.0] + [0.0] * 510)
    db.commit()
    cache = FaceVectorCache(max_rows=1)

    assert cache._refresh(db, owner.id) is None
    assert cache.stats()["oversized"] == [str(owner.id)]

    # The oversized owner is remembered, so later calls short-circuit.
    assert cache._refresh(db, owner.id) is None
    assert cache.stats()["shards"] == 0
