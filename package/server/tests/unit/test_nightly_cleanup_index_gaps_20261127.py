"""Nightly gap coverage for app/service/cleanup_index.py.

The nightly coverage scan flagged these uncovered branches:

* ``sync`` never rejected a corrupt legacy embedding.  The ORM column refuses
  to persist a non-512 / non-finite vector, but rows written by older builds
  (or by a partially migrated library) are still readable, so the cache must
  drop them instead of indexing garbage.
* a vector whose *content revision* changed but whose bytes stayed identical
  skipped the digest fast-path.
* ``matches`` yielded nothing for a photo that is not cached at all.
* a shard file that disappeared between ``prepare`` and ``matches`` was never
  rebuilt on demand.
* the ``complete=True`` whole-cache scan was never used.
* the resident HNSW fast path (``knn_query`` + rescoring) was never used, so
  the fallback scan always shadowed it.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from uuid import uuid4

import numpy as np
import pytest
from sqlalchemy import create_engine, text, update
from sqlalchemy.orm import Session

import app.db.models  # noqa: F401
from app.db.base import Base
from app.db.models import ImageVector, Photo, User
from app.service.cleanup_index import CleanupIndex

pytestmark = [pytest.mark.smoke, pytest.mark.module_toolbox]


def _unit_vector(angle: float = 0.0) -> np.ndarray:
    vector = np.zeros(512, dtype=np.float32)
    vector[0] = np.cos(angle)
    vector[1] = np.sin(angle)
    return vector


@pytest.fixture
def lib(tmp_path, monkeypatch):
    monkeypatch.setenv("TS_CLEANUP_CACHE_DIR", str(tmp_path / "cache"))
    engine = create_engine(f"sqlite:///{(tmp_path / 'library.sqlite').as_posix()}")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        user = User(id=uuid4(), username="nightly-index", hashed_password="unused", settings={})
        db.add(user)
        db.commit()

        def photo(name: str, vector=None, model: str = "model-a"):
            path = tmp_path / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"payload")
            item = Photo(id=uuid4(), owner_id=user.id, filename=name, file_path=str(path), file_type="image")
            db.add(item)
            db.flush()
            if vector is not None:
                db.add(ImageVector(photo_id=item.id, embedding=list(vector), model_name=model))
            db.commit()
            return item

        yield SimpleNamespace(db=db, user=user, photo=photo, root=tmp_path)
    engine.dispose()


def _corrupt_vector(lib, name, payload):
    """Insert a legacy row whose stored vector is not a valid 512-float array."""
    item = lib.photo(name)
    lib.db.execute(
        text("INSERT INTO image_vectors (photo_id, embedding, model_name, content_revision) "
             "VALUES (:pid, :embedding, :model, :revision)"),
        {"pid": str(item.id), "embedding": payload, "model": "model-a", "revision": "legacy"},
    )
    lib.db.commit()
    lib.db.expire_all()
    return item


def test_sync_rejects_corrupt_legacy_vectors(lib):
    """A non-numeric, a short and a zero-norm legacy vector are all discarded."""
    _corrupt_vector(lib, "text.jpg", json.dumps(["a", "b"]))
    _corrupt_vector(lib, "short.jpg", json.dumps([1.0, 2.0]))
    _corrupt_vector(lib, "zero.jpg", json.dumps([0.0] * 512))
    lib.photo("good.jpg", vector=_unit_vector())

    with CleanupIndex(lib.db, lib.user.id, "model-a") as index:
        index.sync()
        assert index.invalid == 3
        # Four rows were decoded, but only the valid one was cached.
        assert index.decoded == 4
        assert index.changed == 1
        cached = index.cache.execute("SELECT count(*) FROM vectors").fetchone()[0]
        assert cached == 1


def test_unchanged_embedding_with_new_revision_updates_generation(lib):
    """Same bytes + new content revision refreshes the cached generation."""
    item = lib.photo("a.jpg", vector=_unit_vector())
    with CleanupIndex(lib.db, lib.user.id, "model-a") as index:
        index.sync()
        first = index.cache.execute("SELECT generation FROM vectors").fetchone()[0]
        # Touching the row bumps ``content_revision`` (onupdate) without
        # changing a single vector byte.
        lib.db.execute(
            update(ImageVector).where(ImageVector.photo_id == item.id)
            .values(embedding=[float(x) for x in _unit_vector()])
        )
        lib.db.commit()
        index.sync()
        second = index.cache.execute("SELECT generation FROM vectors").fetchone()[0]
        assert second > first
        assert index.changed == 1


def test_changed_embedding_updates_the_cached_digest(lib):
    """Different bytes under the same photo id refresh the stored digest."""
    item = lib.photo("a.jpg", vector=_unit_vector())
    with CleanupIndex(lib.db, lib.user.id, "model-a") as index:
        index.sync()
        first = index.cache.execute("SELECT digest FROM vectors").fetchone()[0]
        lib.db.execute(
            update(ImageVector).where(ImageVector.photo_id == item.id)
            .values(embedding=[float(x) for x in _unit_vector(0.5)])
        )
        lib.db.commit()
        index.changed = 0
        index.sync()
        second = index.cache.execute("SELECT digest FROM vectors").fetchone()[0]
        assert second != first
        assert index.changed == 1


def test_unchanged_revision_is_reused_without_decoding(lib):
    """A second sync of an unchanged library does not decode anything."""
    lib.photo("a.jpg", vector=_unit_vector())
    with CleanupIndex(lib.db, lib.user.id, "model-a") as index:
        index.sync()
        index.decoded = 0
        index.changed = 0
        index.sync()
        assert index.decoded == 0
        assert index.changed == 0


def test_matches_for_unknown_photo_yields_nothing(lib):
    """``matches`` on a photo that was never cached returns no candidates."""
    lib.photo("a.jpg", vector=_unit_vector())
    with CleanupIndex(lib.db, lib.user.id, "model-a") as index:
        index.sync()
        assert list(index.matches(uuid4(), 0.9)) == []


def test_missing_shard_file_is_rebuilt_on_demand(lib):
    """A shard removed after ``prepare`` is marked dirty and rebuilt."""
    first = lib.photo("a.jpg", vector=_unit_vector())
    lib.photo("b.jpg", vector=_unit_vector())
    with CleanupIndex(lib.db, lib.user.id, "model-a") as index:
        index.sync()
        index.prepare()
        shard = index.shards()[0]
        (index.root / f"{shard}.hnsw").unlink()
        found = list(index.matches(first.id, 0.9))
        assert str(first.id) in found
        assert (index.root / f"{shard}.hnsw").exists()


def test_complete_scan_matches_every_cached_vector(lib):
    """``complete=True`` scans the whole cache instead of the ANN index."""
    first = lib.photo("a.jpg", vector=_unit_vector())
    second = lib.photo("b.jpg", vector=_unit_vector())
    with CleanupIndex(lib.db, lib.user.id, "model-a") as index:
        index.sync()
        index.prepare()
        found = set(index.matches(first.id, 0.9, complete=True))
        assert found == {str(first.id), str(second.id)}


def test_small_shard_falls_back_to_exact_scan(lib):
    """Fewer vectors than the ANN fan-out falls back to an exact shard scan."""
    first = lib.photo("a.jpg", vector=_unit_vector())
    second = lib.photo("b.jpg", vector=_unit_vector())
    with CleanupIndex(lib.db, lib.user.id, "model-a") as index:
        index.sync()
        index.prepare()
        found = set(index.matches(first.id, 0.9))
        assert found == {str(first.id), str(second.id)}


def test_resident_ann_index_is_used_for_large_shards(lib):
    """With more vectors than the ANN fan-out the HNSW fast path answers."""
    close = [lib.photo(f"close{i}.jpg", vector=_unit_vector()).id for i in range(3)]
    far = [lib.photo(f"far{i}.jpg", vector=_unit_vector(np.pi)).id for i in range(37)]
    with CleanupIndex(lib.db, lib.user.id, "model-a") as index:
        index.sync()
        index.prepare()
        found = {str(item) for item in index.matches(close[0], 0.9)}
        assert str(close[0]) in found
        assert not {str(item) for item in far} & found
