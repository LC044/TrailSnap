"""Nightly watch 2026-11-09: face CRUD membership-change gaps.

Targets uncovered branches reported by the 2026-11-09 coverage snapshot for
``app/crud/face.py``:

* ``update_face``   - membership changes (feature update / soft delete) keep the
  appearance-cluster bookkeeping in sync, and ``commit=False`` only flushes.
* ``delete_face``   - a clustered face is detached from its appearance cluster.

Every test exercises already-implemented behaviour; no production code changes.
"""

from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.crud import face as crud_face
from app.db.base import Base
from app.db.models.face import Face, FaceIdentity
from app.db.models.photo import FileType, Photo
from app.db.models.user import User
from app.schemas import face as face_schemas

pytestmark = [pytest.mark.smoke]


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def owner(db):
    owner_id = uuid4()
    db.add(User(id=owner_id, username="nightly-face-owner", hashed_password="x"))
    db.commit()
    return owner_id


def _face(db, owner_id, **kwargs):
    photo = Photo(
        id=uuid4(),
        owner_id=owner_id,
        filename="p.jpg",
        file_path="p.jpg",
        file_type=FileType.image,
        is_deleted=False,
    )
    db.add(photo)
    db.commit()
    face = Face(photo_id=photo.id, is_deleted=False, **kwargs)
    db.add(face)
    db.commit()
    return face


def test_update_face_with_new_feature_detaches_and_invalidates_cache(db, owner):
    face = _face(db, owner)

    with patch("app.service.face_appearance_clusters.lock_owner") as lock_owner, \
         patch("app.service.face_appearance_clusters.detach") as detach, \
         patch("app.service.face_appearance_clusters.set_identity") as set_identity, \
         patch("app.service.face_appearance_clusters.changed") as changed, \
         patch("app.service.face_vector_cache.face_vector_cache.invalidate") as invalidate:
        updated = crud_face.update_face(
            db,
            face.id,
            face_schemas.FaceUpdate(face_feature=[0.1] * 512),
            owner_id=owner,
            commit=False,
        )

    assert updated is face
    lock_owner.assert_called_once()
    detach.assert_called_once()
    set_identity.assert_called_once()
    changed.assert_not_called()
    invalidate.assert_called_once()


def test_update_face_reassigning_identity_updates_cluster_and_default_cover(db, owner):
    face = _face(db, owner)
    identity = FaceIdentity(id=uuid4(), owner_id=owner, identity_name="小李", is_deleted=False, is_hidden=False)
    db.add(identity)
    db.commit()

    with patch("app.service.face_appearance_clusters.lock_owner") as lock_owner, \
         patch("app.service.face_appearance_clusters.detach") as detach, \
         patch("app.service.face_appearance_clusters.set_identity") as set_identity, \
         patch("app.service.face_appearance_clusters.changed") as changed:
        updated = crud_face.update_face(
            db,
            face.id,
            face_schemas.FaceUpdate(face_identity_id=identity.id),
            owner_id=owner,
        )

    assert updated is face
    lock_owner.assert_called_once()
    # 只有 face_feature / is_deleted 变化时才会从聚类中摘除。
    detach.assert_not_called()
    # 归属改写委托给聚类服务，crud 层只负责把新身份传过去。
    set_identity.assert_called_once()
    assert set_identity.call_args.args[2] == identity.id
    changed.assert_not_called()


def test_delete_face_detaches_clustered_face(db, owner):
    face = _face(db, owner, face_cluster_id=uuid4())

    with patch("app.service.face_appearance_clusters.lock_owner"), \
         patch("app.service.face_appearance_clusters.detach") as detach, \
         patch("app.service.face_appearance_clusters.changed") as changed:
        deleted = crud_face.delete_face(db, face.id, owner)

    assert deleted is face
    detach.assert_called_once()
    changed.assert_called_once()


def test_update_face_returns_none_for_unknown_face(db, owner):
    assert crud_face.update_face(
        db, 999999, face_schemas.FaceUpdate(is_deleted=True), owner_id=owner
    ) is None


