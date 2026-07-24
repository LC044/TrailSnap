"""Unit tests for the album REST router (app/api/album.py).

Covers the album CRUD endpoints that gate behaviour on ownership and
whether the cover is auto-populated. ``crud`` and ``app.crud.photo`` are
patched so no Postgres is needed.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.api import album as album_api


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
