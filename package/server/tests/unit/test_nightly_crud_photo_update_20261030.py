"""2026-10-30 nightly coverage for ``app/crud/photo.py``.

The 2026-10-30 backend coverage scan reported ``crud/photo.py`` at 90.2% with
65 uncovered lines.  Two groups of them matter:

* the list-shaped filters of ``get_all_photos`` (``album_ids`` / ``face_ids`` /
  ``tag_ids``) — they join through the M:N tables and are the only place where
  a duplicate row could slip into the photo browser;
* ``update_photo`` with ``modify_original_file`` — it renames the file on
  disk, so a missing source file or an already existing target must be
  reported instead of silently corrupting the library.
"""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.crud import photo as photo_crud
from app.db.base import Base
from app.db.models.album import Album, AlbumPhoto
from app.db.models.face import Face, FaceIdentity
from app.db.models.photo import FileType, Photo
from app.db.models.tag import PhotoTag, PhotoTagRelation
from app.db.models.user import User
from app.schemas import photo as photo_schemas


pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    owner = uuid.uuid4()
    session.add(User(id=owner, username="crud-owner", hashed_password="x"))
    session.commit()
    try:
        yield session, owner
    finally:
        session.close()
        engine.dispose()


def _photo(db, owner, name, when=None):
    photo = Photo(id=uuid.uuid4(), owner_id=owner, filename=name, file_path=name,
                   file_type=FileType.image, size=1, is_deleted=False, photo_time=when)
    db.add(photo)
    db.flush()
    return photo


# ---------------------------------------------------------------------------
# list-shaped filters of get_all_photos
# ---------------------------------------------------------------------------


def test_album_ids_filter_returns_the_photos_of_every_listed_album(db):
    session, owner = db
    first = _photo(session, owner, "a.jpg", datetime(2025, 3, 1, 10, 0))
    second = _photo(session, owner, "b.jpg", datetime(2025, 3, 2, 10, 0))
    other = _photo(session, owner, "c.jpg", datetime(2025, 3, 3, 10, 0))
    albums = []
    for index, photo in enumerate((first, second, other)):
        album = Album(id=uuid.uuid4(), name=f"album-{index}", type="user", owner_id=owner)
        session.add(album)
        session.flush()
        session.add(AlbumPhoto(album_id=album.id, photo_id=photo.id))
        albums.append(album)
    session.commit()

    result = photo_crud.get_all_photos(session, album_ids=[albums[0].id, albums[1].id], user_id=owner)

    assert {photo.id for photo in result} == {first.id, second.id}


def test_face_ids_filter_returns_the_photos_of_every_listed_identity(db):
    session, owner = db
    tagged = _photo(session, owner, "a.jpg", datetime(2025, 3, 1, 10, 0))
    other_tagged = _photo(session, owner, "b.jpg", datetime(2025, 3, 2, 10, 0))
    plain = _photo(session, owner, "c.jpg", datetime(2025, 3, 3, 10, 0))
    identities = []
    for index, photo in enumerate((tagged, other_tagged)):
        identity = FaceIdentity(id=uuid.uuid4(), owner_id=owner,
                                identity_name=f"identity-{index}", is_deleted=False)
        session.add(identity)
        session.flush()
        session.add(Face(photo_id=photo.id, face_identity_id=identity.id, is_deleted=False))
        identities.append(identity)
    session.commit()

    result = photo_crud.get_all_photos(session, face_ids=[identity.id for identity in identities], user_id=owner)

    assert {photo.id for photo in result} == {tagged.id, other_tagged.id}
    assert plain.id not in {photo.id for photo in result}


def test_tag_ids_filter_returns_the_photos_of_every_listed_tag(db):
    session, owner = db
    tagged = _photo(session, owner, "a.jpg", datetime(2025, 3, 1, 10, 0))
    other_tagged = _photo(session, owner, "b.jpg", datetime(2025, 3, 2, 10, 0))
    plain = _photo(session, owner, "c.jpg", datetime(2025, 3, 3, 10, 0))
    tags = []
    for index, photo in enumerate((tagged, other_tagged)):
        tag = PhotoTag(id=uuid.uuid4(), tag_name=f"tag-{index}", owner_id=owner, is_deleted=False)
        session.add(tag)
        session.flush()
        session.add(PhotoTagRelation(photo_id=photo.id, tag_id=tag.id))
        tags.append(tag)
    session.commit()

    result = photo_crud.get_all_photos(session, tag_ids=[tag.id for tag in tags], user_id=owner)

    assert {photo.id for photo in result} == {tagged.id, other_tagged.id}
    assert plain.id not in {photo.id for photo in result}


# ---------------------------------------------------------------------------
# update_photo with modify_original_file
# ---------------------------------------------------------------------------


def test_update_photo_rejects_renaming_a_missing_source_file(db, tmp_path):
    session, owner = db
    photo = _photo(session, owner, "a.jpg")
    photo.file_path = str(tmp_path / "missing.jpg")
    session.commit()

    with pytest.raises(ValueError, match="原文件不存在"):
        photo_crud.update_photo(session, photo.id, photo_schemas.PhotoUpdate(
            filename="renamed.jpg", modify_original_file=True), user_id=owner)


def test_update_photo_rejects_renaming_onto_an_existing_file(db, tmp_path):
    session, owner = db
    source = tmp_path / "a.jpg"
    source.write_bytes(b"origin")
    target = tmp_path / "b.jpg"
    target.write_bytes(b"existing")
    photo = _photo(session, owner, "a.jpg")
    photo.file_path = str(source)
    session.commit()

    with pytest.raises(ValueError, match="目标文件名已存在"):
        photo_crud.update_photo(session, photo.id, photo_schemas.PhotoUpdate(
            filename="b.jpg", modify_original_file=True), user_id=owner)

    assert source.exists()
    assert target.read_bytes() == b"existing"


def test_update_photo_renames_the_file_and_keeps_the_extension(db, tmp_path):
    session, owner = db
    source = tmp_path / "a.jpg"
    source.write_bytes(b"origin")
    photo = _photo(session, owner, "a.jpg")
    photo.file_path = str(source)
    session.commit()

    updated = photo_crud.update_photo(session, photo.id, photo_schemas.PhotoUpdate(
        filename="renamed", modify_original_file=True), user_id=owner)

    renamed = tmp_path / "renamed.jpg"
    assert renamed.exists()
    assert not source.exists()
    assert updated.filename == "renamed.jpg"
    assert updated.file_path == str(renamed)


def test_update_photo_without_the_file_flag_only_renames_the_row(db, tmp_path):
    session, owner = db
    source = tmp_path / "a.jpg"
    source.write_bytes(b"origin")
    photo = _photo(session, owner, "a.jpg")
    photo.file_path = str(source)
    session.commit()

    updated = photo_crud.update_photo(session, photo.id, photo_schemas.PhotoUpdate(
        filename="renamed.jpg"), user_id=owner)

    assert source.exists()
    assert updated.filename == "renamed.jpg"


def test_update_photo_refuses_to_touch_another_users_photo(db):
    session, owner = db
    stranger = uuid.uuid4()
    session.add(User(id=stranger, username="crud-stranger", hashed_password="x"))
    photo = _photo(session, owner, "a.jpg")
    session.commit()

    assert photo_crud.update_photo(session, photo.id, photo_schemas.PhotoUpdate(
        filename="renamed.jpg"), user_id=stranger) is None
