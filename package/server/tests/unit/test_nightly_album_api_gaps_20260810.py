"""Nightly watch gap coverage for app.api.album.

Targets the four endpoints not yet exercised by ``test_album_api.py``
(60.0% coverage -> higher after this file).

* PUT /{album_id}        - update_album (smart-album embedding path).
* PUT /{album_id}/cover  - set_album_cover.
* GET /{album_id}/photos - read_photos.
* DELETE /{album_id}/photos/{photo_id} - delete_photo.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
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


# -------------------- PUT /albums/{id} --------------------


@pytest.mark.asyncio
async def test_update_album_404_when_album_missing():
    user = _user()
    db = MagicMock()
    payload = MagicMock()
    payload.description = None
    payload.name = None
    payload.shared_users = None

    with patch.object(album_api.crud, "get_album", return_value=None):
        response = await album_api.update_album(
            album_id=uuid4(),
            album=payload,
            background_tasks=MagicMock(),
            db=db,
            current_user=user,
        )

    assert response.code == 404


@pytest.mark.asyncio
async def test_update_album_403_when_not_owner():
    user = _user()
    db = MagicMock()
    payload = MagicMock()
    album = _album(owner_id=uuid4())  # different owner

    with patch.object(album_api.crud, "get_album", return_value=album):
        response = await album_api.update_album(
            album_id=album.id,
            album=payload,
            background_tasks=MagicMock(),
            db=db,
            current_user=user,
        )

    assert response.code == 403


@pytest.mark.asyncio
async def test_update_album_normal_type_returns_crud_result_without_embedding():
    user = _user()
    db = MagicMock()
    album = _album(owner_id=user.id, type="normal")
    payload = MagicMock()
    payload.description = "new"
    payload.name = "renamed"
    payload.shared_users = None

    with patch.object(album_api.crud, "get_album", return_value=album), \
         patch.object(album_api.crud, "update_album", return_value=album) as update_call, \
         patch.object(album_api, "async_get_embedding", new=AsyncMock()) as embed_call:
        response = await album_api.update_album(
            album_id=album.id,
            album=payload,
            background_tasks=MagicMock(),
            db=db,
            current_user=user,
        )

    # Normal albums never trigger embedding or SCAN_ALBUM task.
    embed_call.assert_not_called()
    update_call.assert_called_once()
    assert response.code == 0


@pytest.mark.asyncio
async def test_update_album_smart_type_changed_description_triggers_embedding_and_scan():
    user = _user()
    db = MagicMock()
    album = _album(owner_id=user.id, type="smart", description="old")
    payload = MagicMock()
    payload.description = "new"
    payload.name = None
    payload.shared_users = None

    with patch.object(album_api.crud, "get_album", return_value=album), \
         patch.object(album_api.crud, "update_album", return_value=album), \
         patch.object(album_api, "async_get_embedding", new=AsyncMock(return_value=[0.1, 0.2])), \
         patch.object(album_api.TaskManager, "get_instance") as gmi:
        response = await album_api.update_album(
            album_id=album.id,
            album=payload,
            background_tasks=MagicMock(),
            db=db,
            current_user=user,
        )

    gmi.assert_called_once()
    gmi.return_value.add_task.assert_called_once()
    assert response.code == 0


# -------------------- PUT /albums/{id}/cover --------------------


def test_set_album_cover_400_when_photo_id_missing():
    user = _user()
    db = MagicMock()

    response = album_api.set_album_cover(
        album_id=uuid4(), payload={}, db=db, current_user=user
    )
    assert response.code == 400


def test_set_album_cover_404_when_album_missing():
    user = _user()
    db = MagicMock()
    photo_id = uuid4()

    with patch.object(album_api.crud, "get_album", return_value=None):
        response = album_api.set_album_cover(
            album_id=uuid4(),
            payload={"photo_id": str(photo_id)},
            db=db,
            current_user=user,
        )
    assert response.code == 404


def test_set_album_cover_403_when_not_owner():
    user = _user()
    db = MagicMock()
    album = _album(owner_id=uuid4())

    with patch.object(album_api.crud, "get_album", return_value=album):
        response = album_api.set_album_cover(
            album_id=album.id,
            payload={"photo_id": str(uuid4())},
            db=db,
            current_user=user,
        )
    assert response.code == 403


def test_set_album_cover_404_when_photo_missing():
    user = _user()
    db = MagicMock()
    album = _album(owner_id=user.id)

    with patch.object(album_api.crud, "get_album", return_value=album), \
         patch.object(album_api.app.crud.photo, "get_photo", return_value=None):
        response = album_api.set_album_cover(
            album_id=album.id,
            payload={"photo_id": str(uuid4())},
            db=db,
            current_user=user,
        )
    assert response.code == 404


def test_set_album_cover_happy_path_assigns_cover_and_commits():
    user = _user()
    db = MagicMock()
    album = _album(owner_id=user.id)
    photo = SimpleNamespace(id=uuid4())

    with patch.object(album_api.crud, "get_album", return_value=album), \
         patch.object(album_api.app.crud.photo, "get_photo", return_value=photo):
        response = album_api.set_album_cover(
            album_id=album.id,
            payload={"photo_id": str(photo.id)},
            db=db,
            current_user=user,
        )

    assert album.cover_id == photo.id
    assert album.cover == photo
    db.commit.assert_called_once()
    db.refresh.assert_called_once_with(album)
    assert response.code == 0


# -------------------- GET /albums/{id}/photos --------------------


def test_read_photos_delegates_to_crud_photo():
    user = _user()
    db = MagicMock()
    fake_photos = [SimpleNamespace(id=uuid4()), SimpleNamespace(id=uuid4())]

    with patch.object(
        album_api.app.crud.photo,
        "get_photos",
        return_value=fake_photos,
    ) as crud_call:
        response = album_api.read_photos(
            album_id=uuid4(),
            skip=0,
            limit=50,
            start_time=None,
            end_time=None,
            db=db,
            current_user=user,
        )

    crud_call.assert_called_once()
    assert response.code == 0
    assert response.data == fake_photos


def test_read_photos_forwards_time_window_to_crud():
    user = _user()
    db = MagicMock()
    from datetime import datetime

    start = datetime(2026, 1, 1)
    end = datetime(2026, 12, 31)

    with patch.object(
        album_api.app.crud.photo,
        "get_photos",
        return_value=[],
    ) as crud_call:
        album_api.read_photos(
            album_id=uuid4(),
            skip=10,
            limit=20,
            start_time=start,
            end_time=end,
            db=db,
            current_user=user,
        )

    _, kwargs = crud_call.call_args
    assert kwargs["skip"] == 10
    assert kwargs["limit"] == 20
    assert kwargs["start_time"] == start
    assert kwargs["end_time"] == end


# -------------------- DELETE /albums/{id}/photos/{photo_id} --------------------


def test_delete_photo_404_when_album_missing():
    user = _user()
    db = MagicMock()

    with patch.object(album_api.crud, "get_album", return_value=None):
        response = album_api.delete_photo(
            album_id=uuid4(),
            photo_id=uuid4(),
            db=db,
            current_user=user,
        )
    assert response.code == 404


def test_delete_photo_403_when_not_owner():
    user = _user()
    db = MagicMock()
    album = _album(owner_id=uuid4())

    with patch.object(album_api.crud, "get_album", return_value=album):
        response = album_api.delete_photo(
            album_id=album.id,
            photo_id=uuid4(),
            db=db,
            current_user=user,
        )
    assert response.code == 403


def test_delete_photo_404_when_association_missing():
    user = _user()
    db = MagicMock()
    album = _album(owner_id=user.id)

    with patch.object(album_api.crud, "get_album", return_value=album), \
         patch.object(album_api.crud, "batch_update_album_association", return_value=0):
        response = album_api.delete_photo(
            album_id=album.id,
            photo_id=uuid4(),
            db=db,
            current_user=user,
        )
    assert response.code == 404


def test_delete_photo_happy_path_returns_photo():
    user = _user()
    db = MagicMock()
    album = _album(owner_id=user.id)
    photo = SimpleNamespace(id=uuid4())

    with patch.object(album_api.crud, "get_album", return_value=album), \
         patch.object(album_api.crud, "batch_update_album_association", return_value=1) as assoc_call, \
         patch.object(album_api.app.crud.photo, "get_photo", return_value=photo):
        response = album_api.delete_photo(
            album_id=album.id,
            photo_id=photo.id,
            db=db,
            current_user=user,
        )

    assoc_call.assert_called_once()
    assert response.code == 0
    assert response.data == photo
