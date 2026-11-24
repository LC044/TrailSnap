"""Nightly watch 2026-11-24: ``app/service/cleanup_index.py`` sync / matches 盲区。

2026-11-24 的后端覆盖率报告里 ``service/cleanup_index.py`` 只有 82.8%，
是全仓库最低的模块（204 条语句里 35 条从未执行）。未覆盖的分支集中在两处：

* ``sync()`` 的向量校验与增量更新：维度不对 / 非有限值 / 归一化 / revision 未变
  / revision 变化 / 照片被软删除后的条目清理，全部没有断言；
* ``matches()`` 的四条路径：向量缺失直接返回、``complete=True`` 的全量精确扫描、
  磁盘上的 HNSW 索引缺失或损坏后的重建、以及分片行数超过 32 时真正走 ANN 检索
  （行数不超过 32 时命中的是 fallback 精确扫描分支）。

这些分支决定了「相似照片」分组会不会漏图或错配，因此这里用真实 SQLite 会话
和真实的 hnswlib 索引来验证行为，而不是验证 mock 的形状。
"""

from __future__ import annotations

import json
from uuid import uuid4

import numpy as np
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.db.models.image_vector import ImageVector
from app.db.models.photo import FileType, Photo
from app.service.cleanup_index import CleanupIndex


pytestmark = [pytest.mark.smoke]


MODEL = "clip-ViT-B-32"


@pytest.fixture()
def db(tmp_path):
    import app.db.models  # noqa: F401
    from app.db.base import Base

    engine = create_engine(
        f"sqlite:///{(tmp_path / 'cleanup-index.sqlite').as_posix()}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _embedding(seed: int, dim: int = 512):
    rng = np.random.default_rng(seed)
    return rng.standard_normal(dim).tolist()


def _add_photo(db, owner, embedding=None, revision="rev-1", model=MODEL, name="photo.jpg"):
    photo = Photo(
        id=uuid4(),
        owner_id=owner,
        filename=name,
        _file_path=f"/library/{name}",
        file_type=FileType.image,
        is_deleted=False,
    )
    db.add(photo)
    db.flush()
    if embedding is not None:
        db.add(ImageVector(
            photo_id=photo.id,
            embedding=embedding,
            model_name=model,
            content_revision=revision,
        ))
    db.commit()
    return photo


def _insert_raw_vector(db, photo_id, raw_embedding, revision="rev-1", model=MODEL):
    """绕过 ORM 的 512 维校验，直接写一条维度不合法的向量。"""
    db.execute(
        text("INSERT INTO image_vectors (photo_id, embedding, model_name, content_revision)"
             " VALUES (:pid, :emb, :model, :rev)"),
        {"pid": str(photo_id), "emb": json.dumps(raw_embedding), "model": model, "rev": revision},
    )
    db.commit()


# --------------------------------------------------------------------------- #
# sync(): 向量校验与增量更新
# --------------------------------------------------------------------------- #

def test_sync_stores_a_normalised_vector_for_every_photo(db, tmp_path):
    owner = uuid4()
    photo = _add_photo(db, owner, _embedding(1))

    with CleanupIndex(db, owner, MODEL, root=tmp_path) as index:
        index.sync()

        vector = index.vector(photo.id)
        assert vector is not None
        assert vector.shape == (512,)
        assert float(np.linalg.norm(vector)) == pytest.approx(1.0, abs=1e-5)
        assert index.changed == 1
        assert index.invalid == 0


def test_sync_rejects_a_vector_with_the_wrong_dimension(db, tmp_path):
    owner = uuid4()
    photo = _add_photo(db, owner)
    _insert_raw_vector(db, photo.id, [0.1, 0.2, 0.3])

    with CleanupIndex(db, owner, MODEL, root=tmp_path) as index:
        index.sync()

        assert index.invalid == 1
        assert index.changed == 0
        assert index.vector(photo.id) is None


def test_sync_rejects_a_zero_vector(db, tmp_path):
    owner = uuid4()
    photo = _add_photo(db, owner)
    _insert_raw_vector(db, photo.id, [0.0] * 512)

    with CleanupIndex(db, owner, MODEL, root=tmp_path) as index:
        index.sync()

        assert index.invalid == 1
        assert index.vector(photo.id) is None


def test_sync_keeps_an_unchanged_revision_without_rebuilding_it(db, tmp_path):
    owner = uuid4()
    photo = _add_photo(db, owner, _embedding(2))

    with CleanupIndex(db, owner, MODEL, root=tmp_path) as index:
        index.sync()
        first = index.vector(photo.id).copy()
        changed_before, decoded_before = index.changed, index.decoded

        index.sync()

        assert index.changed == changed_before, "revision 未变时不应该重建向量"
        assert index.decoded == decoded_before, "revision 未变时不应该重新解码向量"
        assert np.array_equal(index.vector(photo.id), first)


def test_sync_updates_the_vector_when_the_revision_changed(db, tmp_path):
    owner = uuid4()
    photo = _add_photo(db, owner, _embedding(3), revision="rev-1")

    with CleanupIndex(db, owner, MODEL, root=tmp_path) as index:
        index.sync()
        changed_before, decoded_before = index.changed, index.decoded
        db.query(ImageVector).filter(ImageVector.photo_id == photo.id).update(
            {"embedding": _embedding(4), "content_revision": "rev-2"})
        db.commit()

        index.sync()

        assert index.changed == changed_before + 1
        assert index.decoded == decoded_before + 1
        expected = np.asarray(_embedding(4), dtype=np.float32)
        expected = expected / np.linalg.norm(expected)
        assert np.allclose(index.vector(photo.id), expected, atol=1e-5)


def test_sync_drops_the_entry_of_a_deleted_photo(db, tmp_path):
    owner = uuid4()
    photo = _add_photo(db, owner, _embedding(5))

    with CleanupIndex(db, owner, MODEL, root=tmp_path) as index:
        index.sync()
        assert index.vector(photo.id) is not None

        db.query(Photo).filter(Photo.id == photo.id).update({"is_deleted": True})
        db.commit()

        index.sync()

        assert index.vector(photo.id) is None


def test_sync_ignores_the_vectors_of_another_model(db, tmp_path):
    owner = uuid4()
    photo = _add_photo(db, owner, _embedding(6), model="other-model")

    with CleanupIndex(db, owner, MODEL, root=tmp_path) as index:
        index.sync()

        assert index.vector(photo.id) is None
        assert index.changed == 0


# --------------------------------------------------------------------------- #
# matches(): 检索的四条路径
# --------------------------------------------------------------------------- #

def test_matches_returns_nothing_for_a_photo_without_a_vector(db, tmp_path):
    owner = uuid4()
    with CleanupIndex(db, owner, MODEL, root=tmp_path) as index:
        assert list(index.matches(uuid4(), 0.9)) == []


def test_matches_finds_a_near_duplicate_photo(db, tmp_path):
    owner = uuid4()
    embedding = _embedding(7)
    first = _add_photo(db, owner, embedding, name="a.jpg")
    second = _add_photo(db, owner, list(embedding), name="b.jpg")

    with CleanupIndex(db, owner, MODEL, root=tmp_path) as index:
        index.sync()
        index.prepare()

        found = list(index.matches(first.id, 0.99))

        assert str(second.id) in found
        assert str(first.id) in found, "同向量也算相似"


def test_matches_complete_scans_every_vector_without_the_index(db, tmp_path):
    owner = uuid4()
    embedding = _embedding(8)
    first = _add_photo(db, owner, embedding, name="a.jpg")
    second = _add_photo(db, owner, list(embedding), name="b.jpg")

    with CleanupIndex(db, owner, MODEL, root=tmp_path) as index:
        index.sync()

        found = list(index.matches(first.id, 0.99, complete=True))

        assert str(second.id) in found
        assert str(first.id) in found


def test_matches_rebuilds_the_index_when_the_file_is_missing(db, tmp_path):
    owner = uuid4()
    embedding = _embedding(9)
    first = _add_photo(db, owner, embedding, name="a.jpg")
    second = _add_photo(db, owner, list(embedding), name="b.jpg")

    with CleanupIndex(db, owner, MODEL, root=tmp_path) as index:
        index.sync()
        index.prepare()
        index.loaded.clear()
        for shard in index.shards():
            (tmp_path / f"{shard}.hnsw").unlink(missing_ok=True)

        found = list(index.matches(first.id, 0.99))

        assert str(second.id) in found
        assert index.rebuilt >= 1, "索引文件缺失后必须重建"


def test_matches_uses_the_ann_index_for_a_large_shard(db, tmp_path):
    """分片超过 32 行时才会真正走 hnswlib 的 ANN 检索分支。"""
    owner = uuid4()
    base = _embedding(10)
    first = _add_photo(db, owner, base, name="base.jpg")
    neighbours = []
    for index_offset in range(40):
        seed = np.random.default_rng(1000 + index_offset)
        variant = np.asarray(base, dtype=np.float32) + seed.standard_normal(512).astype(np.float32) * 0.01
        variant = variant / np.linalg.norm(variant)
        photo = _add_photo(db, owner, variant.tolist(), name=f"n{index_offset}.jpg")
        neighbours.append(photo)

    with CleanupIndex(db, owner, MODEL, root=tmp_path) as index:
        index.sync()
        index.prepare()

        found = list(index.matches(first.id, 0.9))

        assert str(first.id) in found
        assert str(neighbours[0].id) in found
        assert len(found) > 1
