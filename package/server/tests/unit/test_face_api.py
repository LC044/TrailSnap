"""Unit tests for the face REST router (app/api/face.py).

Covers the identity CRUD endpoints (create / update / delete / cover /
merge) by patching ``app.crud.face`` so no Postgres is needed. The
``trigger_conditional_albums_update`` side-effect is patched to avoid
reaching into album logic.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api import face as face_api


pytestmark = [pytest.mark.smoke, pytest.mark.module_face]


def _user(uid=None):
    return SimpleNamespace(id=uid or uuid4())


# ----------------------------- POST /identities ------------------------


def test_create_identity_delegates_to_crud():
    user = _user()
    db = MagicMock()
    payload = SimpleNamespace(identity_name="Alice", description="friend")
    identity = SimpleNamespace(id=uuid4(), identity_name="Alice")

    with patch.object(face_api.crud_face, "create_identity", return_value=identity) as create:
        response = face_api.create_identity(payload=payload, db=db, current_user=user)

    create.assert_called_once_with(db, payload, owner_id=user.id)
    assert response.code == 200
    assert response.data == identity


# ----------------------------- PUT /identities/{id} --------------------


def test_update_identity_returns_404_when_missing():
    user = _user()
    db = MagicMock()
    payload = SimpleNamespace(identity_name="Bob")

    with patch.object(face_api.crud_face, "update_identity", return_value=None):
        with pytest.raises(HTTPException) as exc_info:
            face_api.update_identity(id=uuid4(), payload=payload, db=db, current_user=user)

    assert exc_info.value.status_code == 404


def test_update_identity_succeeds_for_existing_identity():
    user = _user()
    db = MagicMock()
    payload = SimpleNamespace(identity_name="Bob")
    updated = SimpleNamespace(id=uuid4(), identity_name="Bob")

    with patch.object(face_api.crud_face, "update_identity", return_value=updated):
        response = face_api.update_identity(id=uuid4(), payload=payload, db=db, current_user=user)

    assert response.code == 200
    assert response.data == updated


# ----------------------------- DELETE /identities/{id} -----------------


def test_delete_identity_returns_404_when_missing():
    user = _user()
    db = MagicMock()

    with patch.object(face_api.crud_face, "delete_identity", return_value=False):
        response = face_api.delete_identity(id=uuid4(), db=db, current_user=user)

    assert response.code == 404


def test_delete_identity_triggers_album_update_on_success():
    user = _user()
    db = MagicMock()

    with patch.object(face_api.crud_face, "delete_identity", return_value=True):
        with patch("app.crud.album.trigger_conditional_albums_update") as trigger:
            response = face_api.delete_identity(id=uuid4(), db=db, current_user=user)

    trigger.assert_called_once_with(db, user.id, None)
    assert response.code == 200
    assert response.data == {"status": "success"}


# ----------------------------- PUT /identities/{id}/cover --------------


def test_set_identity_cover_returns_404_when_identity_missing():
    user = _user()
    db = MagicMock()
    payload = SimpleNamespace(photo_id=uuid4())

    with patch.object(face_api.crud_face, "get_identity", return_value=None):
        response = face_api.set_identity_cover(id=uuid4(), payload=payload, db=db, current_user=user)

    assert response.code == 404


def test_set_identity_cover_returns_404_when_face_not_in_photo():
    user = _user()
    db = MagicMock()
    payload = SimpleNamespace(photo_id=uuid4())
    identity = SimpleNamespace(id=uuid4())

    with patch.object(face_api.crud_face, "get_identity", return_value=identity):
        with patch.object(face_api.crud_face, "set_identity_cover", return_value=False):
            response = face_api.set_identity_cover(id=uuid4(), payload=payload, db=db, current_user=user)

    assert response.code == 404
    assert "Face not found" in response.msg


def test_set_identity_cover_succeeds():
    user = _user()
    db = MagicMock()
    payload = SimpleNamespace(photo_id=uuid4())
    identity = SimpleNamespace(id=uuid4())

    with patch.object(face_api.crud_face, "get_identity", return_value=identity):
        with patch.object(face_api.crud_face, "set_identity_cover", return_value=True):
            response = face_api.set_identity_cover(id=uuid4(), payload=payload, db=db, current_user=user)

    assert response.code == 200


# ----------------------------- POST /identities/merge ------------------


def test_merge_identities_raises_400_on_failure():
    user = _user()
    db = MagicMock()
    payload = SimpleNamespace(target_id=uuid4(), source_ids=[uuid4(), uuid4()])

    with patch.object(face_api.crud_face, "merge_identities", return_value=False):
        with pytest.raises(HTTPException) as exc_info:
            face_api.merge_identities(payload=payload, db=db, current_user=user)

    assert exc_info.value.status_code == 400


def test_merge_identities_triggers_album_update_on_success():
    user = _user()
    db = MagicMock()
    payload = SimpleNamespace(target_id=uuid4(), source_ids=[uuid4()])

    with patch.object(face_api.crud_face, "merge_identities", return_value=True):
        with patch("app.crud.album.trigger_conditional_albums_update") as trigger:
            response = face_api.merge_identities(payload=payload, db=db, current_user=user)

    trigger.assert_called_once_with(db, user.id, None)
    assert response.code == 200
