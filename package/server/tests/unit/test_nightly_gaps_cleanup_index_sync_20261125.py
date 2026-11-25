"""Nightly watch 2026-11-25 (part 4): the remaining cleanup vector index gaps.

``app/service/cleanup_index.py`` keeps a disposable on-disk manifest of the
photo vectors.  ``tests/unit/test_nightly_cleanup_index_sync_matches_20261124.py``
already covers the normal sync, a wrong dimension, a zero vector, an unchanged
and a changed revision, a deleted photo, another model and the four
``matches()`` paths.

What was still untested:

* a vector that is finite-shaped but contains a NaN component, which makes
  every dot product meaningless;
* ``prepare()`` itself — the shard build and the rebuild of a shard whose
  index file disappeared;
* the owner isolation of ``sync()``.

A real SQLite session is used because the sync pass reads typed rows and
rewrites the manifest with real numpy vectors.
"""
import json
import uuid

import numpy as np
import pytest
from sqlalchemy import text

from app.db.models.image_vector import ImageVector
from app.db.models.photo import Photo, FileType
from app.db.models.user import User
from app.service.cleanup_index import CleanupIndex

MODEL = "clip-ViT-B-32"


def _user(session, name="owner"):
    user = User(username=name, email=f"{name}@example.com", hashed_password="x")
    session.add(user)
    session.commit()
    return user


def _photo(session, owner, name):
    photo = Photo(
        filename=name,
        _file_path=f"C:/photos/{name}.jpg",
        file_type=FileType.image,
        owner_id=owner.id,
    )
    session.add(photo)
    session.commit()
    return photo


def _unit_vector(seed=0):
    vector = np.zeros(512, dtype=np.float32)
    vector[seed % 512] = 1.0
    return vector


def _store(session, photo, values, revision="rev-1", model=MODEL):
    session.add(ImageVector(
        photo_id=photo.id,
        embedding=values,
        model_name=model,
        content_revision=revision,
    ))
    session.commit()


def _store_raw(session, photo, raw_json, revision="rev-1", model=MODEL):
    """Bypass the ORM so an invalid vector can reach the sync pass."""
    session.execute(
        text(
            "INSERT INTO image_vectors (photo_id, embedding, model_name, content_revision, created_at)"
            " VALUES (:pid, :emb, :model, :rev, CURRENT_TIMESTAMP)"
        ),
        {"pid": str(photo.id), "emb": raw_json, "model": model, "rev": revision},
    )
    session.commit()


def _index(session, owner, tmp_path):
    return CleanupIndex(session, owner.id, MODEL, root=tmp_path / "cache")


def test_sync_rejects_a_vector_with_a_nan_component(face_sqlite_session, tmp_path):
    session = face_sqlite_session
    owner = _user(session)
    good = _photo(session, owner, "good")
    broken = _photo(session, owner, "broken")

    _store(session, good, _unit_vector(1))
    # A NaN component makes every dot product meaningless.
    _store_raw(session, broken, json.dumps([float("nan")] + [0.0] * 511))

    with _index(session, owner, tmp_path) as index:
        index.sync()

        assert index.invalid == 1
        assert index.decoded == 2
        assert index.vector(good.id) is not None
        assert index.vector(broken.id) is None


def test_sync_ignores_the_photos_of_another_owner(face_sqlite_session, tmp_path):
    session = face_sqlite_session
    owner = _user(session, "owner")
    other = _user(session, "other")
    foreign = _photo(session, other, "foreign")
    _store(session, foreign, _unit_vector(9))

    with _index(session, owner, tmp_path) as index:
        index.sync()

        assert index.decoded == 0
        assert index.shards() == []
        assert index.vector(foreign.id) is None


def test_prepare_builds_the_shard_index_file(face_sqlite_session, tmp_path):
    session = face_sqlite_session
    owner = _user(session)
    photo = _photo(session, owner, "shard")
    _store(session, photo, _unit_vector(11))

    with _index(session, owner, tmp_path) as index:
        index.sync()
        index.prepare()

        assert index.rebuilt == 1
        assert (index.root / "0.hnsw").exists()
        assert index.shard_rows(0)


def test_prepare_rebuilds_a_shard_whose_index_file_disappeared(face_sqlite_session, tmp_path):
    session = face_sqlite_session
    owner = _user(session)
    photo = _photo(session, owner, "shard")
    _store(session, photo, _unit_vector(12))

    with _index(session, owner, tmp_path) as index:
        index.sync()
        index.prepare()
        (index.root / "0.hnsw").unlink()

        index.prepare()

        assert index.rebuilt == 2
        assert (index.root / "0.hnsw").exists()
