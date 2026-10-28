"""Nightly coverage for the photo lifecycle helpers in ``app/crud/photo.py``.

The 2026-10-28 backend coverage scan ranked ``crud/photo.py`` at 82.8%
(114 missed statements).  The bulk-purge path is already covered by
``test_recycle_bin_bulk_delete.py``; what remained dark were the
**single-photo and recycle-bin lifecycle** helpers:

* ``get_photos_by_ids``     -- owner scoping and the include-deleted switch
* ``delete_photo``          -- owner refusal, album recount, cluster cleanup
* ``batch_soft_delete_photos`` -- soft delete + album recount
* ``restore_photos``        -- restore, and clearing the "delete" declutter record
* ``get_recycle_bin_photos`` -- ordering and the ``limit == 0`` "no limit" case
* ``count_recycle_bin_photos`` / ``get_recycle_bin_photo_ids`` -- the paging helpers

These decide what a user sees in the recycle bin and whether a stranger can
delete somebody else's photo, so they are worth pinning down.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.crud import photo as photo_crud
from app.db.base import Base
from app.db.models.album import Album, AlbumPhoto
from app.db.models.face import Face, FaceIdentity
from app.db.models.photo import FileType, Photo
from app.db.models.photo_declutter_record import PhotoDeclutterRecord
from app.db.models.user import User


pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")

    # The production engine turns foreign keys on. ``FaceIdentity.default_face_id``
    # relies on ON DELETE SET NULL, and SQLite ignores FK actions without it, so
    # the fixture must mirror production or the assertion would validate nothing.
    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _owner(db, username="owner"):
    user = User(id=uuid4(), username=username, hashed_password="x")
    db.add(user)
    db.commit()
    return user.id


def _photo(db, owner_id, filename="p.jpg", deleted=False, deleted_at=None):
    photo = Photo(
        id=uuid4(), owner_id=owner_id, filename=filename, file_path=filename,
        file_type=FileType.image, is_deleted=deleted, deleted_at=deleted_at,
        size=1, width=10, height=10,
    )
    db.add(photo)
    db.commit()
    return photo


def _album(db, owner_id, photo=None, name="album"):
    album = Album(id=uuid4(), owner_id=owner_id, name=name, type="user", num_photos=0)
    db.add(album)
    db.flush()
    if photo is not None:
        db.add(AlbumPhoto(album_id=album.id, photo_id=photo.id))
    db.commit()
    return album


# ---------------------------------------------------------------------------
# get_photos_by_ids
# ---------------------------------------------------------------------------


def test_get_photos_by_ids_excludes_deleted_by_default(db):
    """Happy path: a soft-deleted photo is not returned unless asked for."""
    owner = _owner(db)
    alive = _photo(db, owner, "alive.jpg")
    gone = _photo(db, owner, "gone.jpg", deleted=True, deleted_at=datetime.now())

    found = photo_crud.get_photos_by_ids(db, [alive.id, gone.id], user_id=owner)

    assert [row.id for row in found] == [alive.id]


def test_get_photos_by_ids_can_include_deleted(db):
    """Edge: the recycle-bin listing needs the deleted rows too."""
    owner = _owner(db)
    gone = _photo(db, owner, "gone.jpg", deleted=True, deleted_at=datetime.now())

    found = photo_crud.get_photos_by_ids(db, [gone.id], user_id=owner, include_deleted=True)

    assert [row.id for row in found] == [gone.id]


def test_get_photos_by_ids_is_owner_scoped(db):
    """Error guard: another user's photo is never returned."""
    owner, stranger = _owner(db, "owner"), _owner(db, "stranger")
    theirs = _photo(db, stranger, "theirs.jpg")

    found = photo_crud.get_photos_by_ids(db, [theirs.id], user_id=owner)

    assert found == []


# ---------------------------------------------------------------------------
# delete_photo
# ---------------------------------------------------------------------------


def test_delete_photo_removes_the_row_and_the_album_link(db):
    """Happy path: the photo and its album membership are gone."""
    owner = _owner(db)
    photo = _photo(db, owner)
    album = _album(db, owner, photo)

    deleted = photo_crud.delete_photo(db, photo.id, user_id=owner)

    assert deleted is not None
    db.expire_all()
    assert db.query(Photo).filter(Photo.id == photo.id).first() is None
    assert db.query(AlbumPhoto).filter(AlbumPhoto.album_id == album.id).count() == 0


def test_delete_photo_refuses_another_users_photo(db):
    """Error guard: a stranger's photo is not deleted."""
    owner, stranger = _owner(db, "owner"), _owner(db, "stranger")
    theirs = _photo(db, stranger, "theirs.jpg")

    assert photo_crud.delete_photo(db, theirs.id, user_id=owner) is None
    db.expire_all()
    assert db.query(Photo).filter(Photo.id == theirs.id).first() is not None


def test_delete_photo_returns_none_for_an_unknown_id(db):
    """Edge: deleting a photo that is already gone is a no-op."""
    owner = _owner(db)
    assert photo_crud.delete_photo(db, uuid4(), user_id=owner) is None


def test_delete_photo_with_delete_file_removes_the_file(db, tmp_path):
    """Happy path: ``is_delete_file`` also unlinks the original file."""
    owner = _owner(db)
    target = tmp_path / "photo.jpg"
    target.write_bytes(b"x")
    photo = _photo(db, owner)
    photo.file_path = str(target)
    db.commit()

    with patch.object(photo_crud.storage, "delete_file") as delete_file:
        photo_crud.delete_photo(db, photo.id, is_delete_file=True, user_id=owner)

    assert delete_file.called
    assert delete_file.call_args[0][1] == str(target)


def test_delete_photo_reassigns_the_face_avatar(db):
    """The identity loses a dangling avatar when its photo is deleted.

    ``default_face_id`` points at a **face** row, so the avatar has to be
    re-pointed (or cleared) when the photo that carried it disappears.
    """
    owner = _owner(db)
    photo = _photo(db, owner)
    identity = FaceIdentity(id=uuid4(), owner_id=owner, identity_name="小李",
                             is_deleted=False, is_hidden=False)
    db.add(identity)
    db.flush()
    face = Face(photo_id=photo.id, face_identity_id=identity.id, is_deleted=False)
    db.add(face)
    db.commit()
    identity.default_face_id = face.id
    db.commit()

    photo_crud.delete_photo(db, photo.id, user_id=owner)

    db.expire_all()
    refreshed = db.query(FaceIdentity).filter(FaceIdentity.id == identity.id).one()
    assert refreshed.default_face_id is None


# ---------------------------------------------------------------------------
# batch_soft_delete_photos / restore_photos
# ---------------------------------------------------------------------------


def test_batch_soft_delete_marks_the_photos_and_recounts_the_album(db):
    """Happy path: the photos are flagged, not deleted, and the count is fixed."""
    owner = _owner(db)
    first = _photo(db, owner, "a.jpg")
    second = _photo(db, owner, "b.jpg")
    album = _album(db, owner, first)
    db.add(AlbumPhoto(album_id=album.id, photo_id=second.id))
    db.commit()
    album.num_photos = 2
    db.commit()

    count = photo_crud.batch_soft_delete_photos(db, [first.id, second.id], user_id=owner)

    assert count == 2
    db.expire_all()
    assert all(row.is_deleted for row in db.query(Photo).all())
    assert all(row.deleted_at is not None for row in db.query(Photo).all())
    assert db.query(Album).filter(Album.id == album.id).one().num_photos == 0


def test_batch_soft_delete_is_owner_scoped(db):
    """Error guard: another user's photo is not soft-deleted."""
    owner, stranger = _owner(db, "owner"), _owner(db, "stranger")
    theirs = _photo(db, stranger, "theirs.jpg")

    assert photo_crud.batch_soft_delete_photos(db, [theirs.id], user_id=owner) == 0
    db.expire_all()
    assert db.query(Photo).filter(Photo.id == theirs.id).one().is_deleted is False


def test_restore_photos_clears_the_deleted_flag_and_the_delete_decision(db):
    """Happy path: restoring also forgets the swipe-filter "delete" decision."""
    owner = _owner(db)
    photo = _photo(db, owner, "a.jpg", deleted=True, deleted_at=datetime.now())
    db.add(PhotoDeclutterRecord(
        photo_id=photo.id, owner_id=owner, decision="delete",
    ))
    db.commit()

    count = photo_crud.restore_photos(db, [photo.id], user_id=owner)

    assert count == 1
    db.expire_all()
    refreshed = db.query(Photo).filter(Photo.id == photo.id).one()
    assert refreshed.is_deleted is False
    assert refreshed.deleted_at is None
    # The "delete" decision must not survive the restore.
    assert db.query(PhotoDeclutterRecord).filter(
        PhotoDeclutterRecord.photo_id == photo.id,
        PhotoDeclutterRecord.decision == "delete",
    ).count() == 0


def test_restore_photos_keeps_a_keep_decision(db):
    """Edge: a "keep" decision is intentionally preserved across a restore."""
    owner = _owner(db)
    photo = _photo(db, owner, "a.jpg", deleted=True, deleted_at=datetime.now())
    db.add(PhotoDeclutterRecord(
        photo_id=photo.id, owner_id=owner, decision="keep",
    ))
    db.commit()

    photo_crud.restore_photos(db, [photo.id], user_id=owner)

    db.expire_all()
    assert db.query(PhotoDeclutterRecord).filter(
        PhotoDeclutterRecord.photo_id == photo.id,
        PhotoDeclutterRecord.decision == "keep",
    ).count() == 1


def test_restore_photos_ignores_photos_that_are_not_deleted(db):
    """Edge: a live photo is not counted as restored."""
    owner = _owner(db)
    photo = _photo(db, owner, "a.jpg")

    assert photo_crud.restore_photos(db, [photo.id], user_id=owner) == 0


# ---------------------------------------------------------------------------
# recycle bin listing helpers
# ---------------------------------------------------------------------------


def test_recycle_bin_lists_the_newest_deletion_first(db):
    """Happy path: the most recently deleted photo is at the top."""
    owner = _owner(db)
    now = datetime(2026, 3, 1, 12, 0)
    older = _photo(db, owner, "older.jpg", deleted=True, deleted_at=now)
    newer = _photo(db, owner, "newer.jpg", deleted=True, deleted_at=now + timedelta(hours=1))
    _photo(db, owner, "alive.jpg")

    rows = photo_crud.get_recycle_bin_photos(db, owner)

    assert [row.id for row in rows] == [newer.id, older.id]


def test_recycle_bin_limit_zero_means_no_limit(db):
    """Edge: ``limit == 0`` returns every row instead of none."""
    owner = _owner(db)
    for index in range(3):
        _photo(db, owner, f"p{index}.jpg", deleted=True, deleted_at=datetime.now())

    assert len(photo_crud.get_recycle_bin_photos(db, owner, limit=0)) == 3
    assert len(photo_crud.get_recycle_bin_photos(db, owner, limit=2)) == 2


def test_recycle_bin_count_is_owner_scoped(db):
    """Error guard: the count only covers the owner's own bin."""
    owner, stranger = _owner(db, "owner"), _owner(db, "stranger")
    _photo(db, owner, "mine.jpg", deleted=True, deleted_at=datetime.now())
    _photo(db, stranger, "theirs.jpg", deleted=True, deleted_at=datetime.now())

    assert photo_crud.count_recycle_bin_photos(db, owner) == 1
    assert photo_crud.count_recycle_bin_photos(db, stranger) == 1


def test_recycle_bin_ids_are_ordered_oldest_first_and_respect_the_limit(db):
    """The purge worker walks the ids from the oldest deletion upwards."""
    owner = _owner(db)
    now = datetime(2026, 3, 1, 12, 0)
    older = _photo(db, owner, "older.jpg", deleted=True, deleted_at=now)
    newer = _photo(db, owner, "newer.jpg", deleted=True, deleted_at=now + timedelta(hours=1))

    assert photo_crud.get_recycle_bin_photo_ids(db, owner) == [older.id, newer.id]
    assert photo_crud.get_recycle_bin_photo_ids(db, owner, limit=1) == [older.id]
    # A non-positive limit means "no limit".
    assert len(photo_crud.get_recycle_bin_photo_ids(db, owner, limit=0)) == 2


