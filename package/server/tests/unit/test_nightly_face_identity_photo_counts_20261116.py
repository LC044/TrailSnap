"""2026-11-16 nightly coverage for ``app/crud/face.py::_identity_photo_counts``.

The 2026-11-16 backend coverage scan reported ``crud/face.py`` at 94.9% and
showed that the private helper that counts the photos behind an identity
was never referenced by any test.  It powers the face-list queries and
must respect the owner, the requested photo and the soft-delete state.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.crud import face as crud_face
from app.db.base import Base
from app.db.models.face import Face, FaceIdentity
from app.db.models.photo import FileType, Photo
from app.db.models.user import User


pytestmark = [pytest.mark.smoke, pytest.mark.module_face]


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


def _owner(db, name="owner-a"):
    owner_id = uuid4()
    db.add(User(id=owner_id, username=name, hashed_password="x"))
    db.commit()
    return owner_id


def _photo(db, owner_id, name="p.jpg", deleted=False):
    photo = Photo(
        id=uuid4(),
        owner_id=owner_id,
        filename=name,
        file_path=name,
        file_type=FileType.image,
        is_deleted=deleted,
    )
    db.add(photo)
    db.commit()
    return photo


def _identity(db, owner_id, name="identity-a"):
    identity = FaceIdentity(id=uuid4(), owner_id=owner_id, identity_name=name,
                            is_deleted=False)
    db.add(identity)
    db.commit()
    return identity


def _counts(db, **kwargs):
    counted = crud_face._identity_photo_counts(db, **kwargs)
    return {
        str(identity_id): count
        for identity_id, count in db.query(counted.c.face_identity_id, counted.c.count).all()
    }


def test_identity_photo_counts_distinguishes_photos_and_identities(db):
    owner_id = _owner(db)
    identity = _identity(db, owner_id)
    other = _identity(db, owner_id, "identity-b")
    photo_a = _photo(db, owner_id, "a.jpg")
    photo_b = _photo(db, owner_id, "b.jpg")

    # Two faces of the same identity on the same photo count once.
    db.add(Face(photo_id=photo_a.id, face_identity_id=identity.id, is_deleted=False))
    db.add(Face(photo_id=photo_a.id, face_identity_id=identity.id, is_deleted=False))
    db.add(Face(photo_id=photo_b.id, face_identity_id=identity.id, is_deleted=False))
    db.add(Face(photo_id=photo_a.id, face_identity_id=other.id, is_deleted=False))
    # A face without an identity never belongs to a counted identity.
    db.add(Face(photo_id=photo_b.id, face_identity_id=None, is_deleted=False))
    db.commit()

    assert _counts(db, owner_id=owner_id) == {
        str(identity.id): 2,
        str(other.id): 1,
    }


def test_identity_photo_counts_can_be_restricted_to_one_photo(db):
    owner_id = _owner(db)
    identity = _identity(db, owner_id)
    photo_a = _photo(db, owner_id, "a.jpg")
    photo_b = _photo(db, owner_id, "b.jpg")
    db.add(Face(photo_id=photo_a.id, face_identity_id=identity.id, is_deleted=False))
    db.add(Face(photo_id=photo_b.id, face_identity_id=identity.id, is_deleted=False))
    db.commit()

    assert _counts(db, owner_id=owner_id, photo_id=photo_a.id) == {str(identity.id): 1}


def test_identity_photo_counts_skip_soft_deleted_faces(db):
    owner_id = _owner(db)
    identity = _identity(db, owner_id)
    photo = _photo(db, owner_id)
    db.add(Face(photo_id=photo.id, face_identity_id=identity.id, is_deleted=False))
    db.add(Face(photo_id=photo.id, face_identity_id=identity.id, is_deleted=True))
    db.commit()

    assert _counts(db, owner_id=owner_id) == {str(identity.id): 1}
    assert _counts(db, owner_id=owner_id, active_only=True) == {str(identity.id): 1}


def test_identity_photo_counts_are_scoped_to_the_owner(db):
    owner_id = _owner(db, "owner-a")
    other_owner = _owner(db, "owner-b")
    identity = _identity(db, owner_id)
    own_photo = _photo(db, owner_id, "own.jpg")
    foreign_photo = _photo(db, other_owner, "foreign.jpg")
    db.add(Face(photo_id=own_photo.id, face_identity_id=identity.id, is_deleted=False))
    db.add(Face(photo_id=foreign_photo.id, face_identity_id=identity.id, is_deleted=False))
    db.commit()

    assert _counts(db, owner_id=owner_id) == {str(identity.id): 1}
    assert _counts(db) == {str(identity.id): 2}
