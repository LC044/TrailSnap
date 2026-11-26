"""Unit tests for the album REST router (app/api/album.py).

Covers the album CRUD endpoints that gate behaviour on ownership and
whether the cover is auto-populated. ``crud`` and ``app.crud.photo`` are
patched so no Postgres is needed.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.api import album as album_api
from app.db.models.album import Album
from app.db.models.photo import FileType, Photo
from app.db.models.user import User


pytestmark = [pytest.mark.smoke, pytest.mark.module_album]


def _user(uid=None):
    return SimpleNamespace(id=uid or uuid4())


def _album(owner_id=None, **kwargs):
    return SimpleNamespace(
        id=kwargs.get("id", uuid4()),
        owner_id=owner_id or uuid4(),
        name=kwargs.get("name", "Vacation"),
        type=kwargs.get("type", "normal"),
        cover_id=kwargs.get("cover_id"),
        cover=kwargs.get("cover"),
        description=kwargs.get("description"),
    )


def test_create_album_with_selected_photos_is_atomic(face_sqlite_session, tmp_path):
    db = face_sqlite_session
    owner = User(username="owner", hashed_password="unused")
    other = User(username="other", hashed_password="unused")
    db.add_all([owner, other])
    db.flush()

    def photo(name, user, deleted=False):
        row = Photo(owner_id=user.id, filename=name, file_path=str(tmp_path / name),
                    file_type=FileType.image, is_deleted=deleted)
        db.add(row)
        return row

    first, second = photo("first.jpg", owner), photo("second.jpg", owner)
    private = photo("private.jpg", other)
    deleted = photo("deleted.jpg", owner, deleted=True)
    db.commit()

    def create(name, photos):
        payload = album_api.schemas.AlbumCreate(name=name, photo_ids=[item.id for item in photos])
        return asyncio.run(album_api.create_album(payload, MagicMock(), db, owner))

    for unavailable in (private, deleted):
        assert create("Invalid", [first, unavailable]).code == 400
    assert db.query(Album).count() == 0

    result = create("Trip", [second, first, second])
    assert result.code == 0
    assert result.data.num_photos == 2
    assert result.data.cover_id == second.id
    assert {item.id for item in result.data.photos} == {first.id, second.id}


# ----------------------------- GET /albums ----------------------------


def test_read_albums_returns_list_from_crud():
    user = _user()
    db = MagicMock()
    albums = [_album(owner_id=user.id), _album(owner_id=user.id)]

    with patch.object(album_api.crud, "get_albums", return_value=albums) as crud_call:
        response = album_api.read_albums(skip=0, limit=50, db=db, current_user=user)

    crud_call.assert_called_once_with(db, skip=0, limit=50, user_id=user.id)
    assert response.code == 0
    assert response.data == albums



@pytest.mark.parametrize("skip,limit", [(0, 4), (4, 12)])
def test_read_smart_album_overview_returns_crud_data(skip, limit):
    user = _user()
    db = MagicMock()
    section = album_api.schemas.SmartAlbumSection(
        item_count=2,
        photo_count=7,
        representatives=[album_api.schemas.SmartAlbumRepresentative(
            entity_id="person-1",
            name="Person 1",
            photo_id=uuid4(),
            photo_count=4,
        )],
    )
    overview = album_api.schemas.SmartAlbumOverview(people=section)

    with patch.object(album_api.crud, "get_smart_album_overview", return_value=overview) as crud_call:
        response = album_api.read_smart_album_overview(skip=skip, limit=limit, db=db, current_user=user)

    crud_call.assert_called_once_with(db, owner_id=user.id, representative_limit=limit, representative_skip=skip)
    assert response.code == 0
    assert response.data is overview

# ----------------------------- GET /albums/{id} -----------------------


def test_read_album_returns_404_when_missing():
    user = _user()
    db = MagicMock()

    with patch.object(album_api.crud, "get_album", return_value=None):
        response = album_api.read_album(album_id=uuid4(), db=db, current_user=user)

    assert response.code == 404
    assert response.data is None


def test_read_album_assigns_earliest_photo_as_cover_when_unset():
    user = _user()
    db = MagicMock()
    album = _album(owner_id=user.id, cover_id=None)
    earlier = SimpleNamespace(id=uuid4(), photo_time=None, upload_time="2025-01-01")
    later = SimpleNamespace(id=uuid4(), photo_time=None, upload_time="2026-01-01")

    with patch.object(album_api.crud, "get_album", return_value=album):
        with patch.object(
            album_api.app.crud.photo,
            "get_photos",
            return_value=[later, earlier],
        ):
            response = album_api.read_album(album_id=album.id, db=db, current_user=user)

    assert response.code == 0
    assert album.cover_id == earlier.id
    assert album.cover == earlier
    db.add.assert_called_once_with(album)
    db.commit.assert_called_once()


def test_read_album_skips_cover_assignment_when_already_set():
    user = _user()
    db = MagicMock()
    cover_id = uuid4()
    album = _album(owner_id=user.id, cover_id=cover_id)

    with patch.object(album_api.crud, "get_album", return_value=album):
        with patch.object(album_api.app.crud.photo, "get_photos") as get_photos:
            response = album_api.read_album(album_id=album.id, db=db, current_user=user)

    get_photos.assert_not_called()
    assert response.code == 0
    assert album.cover_id == cover_id


# ----------------------------- DELETE /albums/{id} --------------------


def test_delete_album_returns_404_when_missing():
    user = _user()
    db = MagicMock()

    with patch.object(album_api.crud, "get_album", return_value=None):
        response = album_api.delete_album(album_id=uuid4(), db=db, current_user=user)

    assert response.code == 404


def test_delete_album_returns_403_when_not_owner():
    user = _user()
    db = MagicMock()
    album = _album(owner_id=uuid4())  # different owner

    with patch.object(album_api.crud, "get_album", return_value=album):
        response = album_api.delete_album(album_id=album.id, db=db, current_user=user)

    assert response.code == 403


def test_delete_album_succeeds_for_owner():
    user = _user()
    db = MagicMock()
    album = _album(owner_id=user.id)

    with patch.object(album_api.crud, "get_album", return_value=album):
        with patch.object(album_api.crud, "delete_album", return_value=album) as crud_delete:
            response = album_api.delete_album(album_id=album.id, db=db, current_user=user)

    crud_delete.assert_called_once_with(db, album_id=album.id)
    assert response.code == 0
    assert response.data == album
