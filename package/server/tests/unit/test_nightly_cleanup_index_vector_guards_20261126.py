"""Nightly watch 2026-11-26 · app/service/cleanup_index.py 的向量校验与分片检索盲区。

覆盖率报告里 ``cleanup_index.py`` 仍有若干分支没有断言：

- ``sync()`` 对「无法转换成 float32 的向量」「含 NaN / 无穷大的向量」的处理
  （第 114-120 行）。ORM 侧的 ``Vector(512)`` 会拒绝这两类脏数据，但历史库里
  仍然可能存在，一旦漏过校验就会污染相似度分组。
- ``sync()`` 在「向量内容没变、只有 revision 变了」时的更新分支（第 131-132 行）：
  此时不应把照片算作「内容已改」，但必须把 revision 推进，否则下次同步还会
  重复处理同一张照片。
- ``matches()`` 的两条 ANN 路径：ANN 查询抛错时必须退化成精确扫描（第 218-223 行），
  以及常驻分片超出内存预算时必须淘汰旧分片（第 195-196 行）。

ANN 相关的两条用假的 hnswlib 驱动，精确扫描与向量校验用真实的 SQLite 缓存验证。
"""

from __future__ import annotations

import json
import sys
import types
from uuid import uuid4

import numpy as np
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.db.models.image_vector import ImageVector
from app.db.models.photo import FileType, Photo
from app.service import cleanup_index as cleanup_index_module
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


def _insert_raw_vector(db, photo_id, raw_json, revision="rev-1", model=MODEL):
    """绕过 ORM 的维度 / 有限值校验，直接写一条脏向量。"""
    db.execute(
        text("INSERT INTO image_vectors (photo_id, embedding, model_name, content_revision)"
             " VALUES (:pid, :emb, :model, :rev)"),
        {"pid": str(photo_id), "emb": raw_json, "model": model, "rev": revision},
    )
    db.commit()


# --- sync(): 脏向量 ---------------------------------------------------------

def test_sync_rejects_a_vector_that_cannot_be_read_as_numbers(db, tmp_path):
    owner = uuid4()
    photo = _add_photo(db, owner)
    _insert_raw_vector(db, photo.id, json.dumps("not-a-vector"))

    with CleanupIndex(db, owner, MODEL, root=tmp_path) as index:
        index.sync()

        assert index.invalid == 1
        assert index.decoded == 1
        assert index.cache.execute("SELECT count(*) FROM vectors").fetchone()[0] == 0


def test_sync_rejects_a_vector_containing_nan(db, tmp_path):
    owner = uuid4()
    photo = _add_photo(db, owner)
    _insert_raw_vector(db, photo.id, json.dumps([float("nan")] * 512))

    with CleanupIndex(db, owner, MODEL, root=tmp_path) as index:
        index.sync()

        assert index.invalid == 1
        assert index.cache.execute("SELECT count(*) FROM vectors").fetchone()[0] == 0


def test_sync_rejects_a_vector_containing_infinity(db, tmp_path):
    owner = uuid4()
    photo = _add_photo(db, owner)
    _insert_raw_vector(db, photo.id, json.dumps([float("inf")] + [0.0] * 511))

    with CleanupIndex(db, owner, MODEL, root=tmp_path) as index:
        index.sync()

        assert index.invalid == 1
        assert index.cache.execute("SELECT count(*) FROM vectors").fetchone()[0] == 0


def test_sync_only_bumps_the_revision_when_the_vector_content_is_unchanged(db, tmp_path):
    owner = uuid4()
    photo = _add_photo(db, owner, embedding=_embedding(7), revision="rev-1")

    with CleanupIndex(db, owner, MODEL, root=tmp_path) as index:
        index.sync()
        first_generation = index.cache.execute(
            "SELECT generation FROM vectors WHERE photo=?", (str(photo.id),)).fetchone()[0]

        db.execute(
            text("UPDATE image_vectors SET content_revision='rev-2' WHERE photo_id=:pid"),
            {"pid": str(photo.id)},
        )
        db.commit()

        index.sync()

        row = index.cache.execute(
            "SELECT generation, revision FROM vectors WHERE photo=?", (str(photo.id),)).fetchone()
        assert row[1] == "rev-2"
        assert row[0] > first_generation
        # 向量内容没有变化，不应被算作「内容已改」。
        assert index.changed == 1
        assert index.decoded == 2


# --- matches(): ANN 与常驻分片 -----------------------------------------------

class _FakeIndex:
    """最小可用的 hnswlib 替身：可配置 knn_query 是否抛错。"""

    queries = 0
    fail_query = True

    def __init__(self, space=None, dim=None):
        self.labels = []

    def init_index(self, **kwargs):
        return None

    def add_items(self, matrix, labels, num_threads=1):
        self.labels = list(labels)
        return None

    def save_index(self, path):
        return None

    def load_index(self, path):
        return None

    def set_ef(self, ef):
        return None

    def knn_query(self, vector, k=None, num_threads=1):
        type(self).queries += 1
        if type(self).fail_query:
            raise RuntimeError("ann query failed")
        return (np.array([self.labels[:k]]), np.array([[0.0] * k]))

    def get_items(self, labels):
        return np.zeros((len(labels), 512), dtype=np.float32)


@pytest.fixture()
def fake_hnswlib(monkeypatch):
    module = types.ModuleType("hnswlib")
    module.Index = _FakeIndex
    _FakeIndex.queries = 0
    _FakeIndex.fail_query = True
    monkeypatch.setitem(sys.modules, "hnswlib", module)
    return module


def _insert_vector(index, label, photo_id, vector):
    blob = np.asarray(vector, dtype=np.float32).tobytes()
    index.cache.execute(
        "INSERT INTO vectors (label, photo, digest, vector, generation, revision)"
        " VALUES (?,?,?,?,1,?)",
        (label, str(photo_id), None, blob, "rev-1"),
    )
    index.cache.commit()


def test_matches_falls_back_to_an_exact_scan_when_the_ann_query_fails(db, tmp_path, fake_hnswlib):
    owner = uuid4()
    query_vector = _embedding(11)
    duplicate = _embedding(11)
    with CleanupIndex(db, owner, MODEL, root=tmp_path) as index:
        query_id, duplicate_id = uuid4(), uuid4()
        _insert_vector(index, 1, query_id, query_vector)
        for label in range(2, 34):
            _insert_vector(index, label, uuid4(), _embedding(label))
        # 最后一行的向量与查询向量完全相同：精确扫描必须能找到它。
        _insert_vector(index, 34, duplicate_id, duplicate)

        found = list(index.matches(query_id, 0.9))

    assert _FakeIndex.queries == 1
    assert str(duplicate_id) in found


def test_matches_evicts_a_resident_shard_when_the_memory_budget_is_exceeded(
    db, tmp_path, fake_hnswlib, monkeypatch
):
    monkeypatch.setattr(cleanup_index_module, "SHARD_SIZE", 2)
    owner = uuid4()
    shared = _embedding(21)
    with CleanupIndex(db, owner, MODEL, root=tmp_path) as index:
        index.max_resident_rows = 1
        query_id = uuid4()
        _insert_vector(index, 1, query_id, shared)
        _insert_vector(index, 2, uuid4(), shared)
        _insert_vector(index, 3, uuid4(), shared)
        _insert_vector(index, 4, uuid4(), shared)

        list(index.matches(query_id, 0.9))

        assert list(index.loaded) == [1]
