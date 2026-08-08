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


# ----------------------------- POST /identities/{id}/rescan -----------


def test_rescan_identity_uses_user_config_and_returns_two_phase_counts():
    user = _user()
    db = MagicMock()
    identity_id = uuid4()
    result = {
        "status": "success",
        "added_count": 3,
        "removed_count": 1,
        "reassigned_count": 1,
        "count": 3,
        "affected_photo_ids": [],
    }

    with patch.object(face_api.crud_face, "get_identity", return_value=SimpleNamespace(id=identity_id)), \
         patch.object(face_api, "FaceClusterService") as service_class:
        service_class.return_value.rescan_identity.return_value = result
        response = face_api.rescan_identity(id=identity_id, db=db, current_user=user)

    service_class.assert_called_once_with(db, user_id=user.id)
    service_class.return_value.rescan_identity.assert_called_once_with(identity_id, owner_id=user.id)
    assert response.data["added_count"] == 3
    assert response.data["removed_count"] == 1


def test_rescan_identity_exposes_execution_failure_as_http_500():
    from app.service.face_cluster import FaceRescanError

    user = _user()
    db = MagicMock()
    identity_id = uuid4()

    with patch.object(face_api.crud_face, "get_identity", return_value=SimpleNamespace(id=identity_id)), \
         patch.object(face_api, "FaceClusterService") as service_class:
        service_class.return_value.rescan_identity.side_effect = FaceRescanError("failed")
        with pytest.raises(HTTPException) as exc_info:
            face_api.rescan_identity(id=identity_id, db=db, current_user=user)

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Face identity rescan failed"


def test_preview_identity_rescan_returns_candidates_without_applying():
    user = _user()
    db = MagicMock()
    identity_id = uuid4()
    preview = {
        "status": "success",
        "add_candidates": [{"face_id": 10}],
        "remove_candidates": [{"face_id": 20}],
        "summary": {"add_count": 1, "remove_count": 1, "reassign_count": 0},
    }

    with patch.object(face_api.crud_face, "get_identity", return_value=SimpleNamespace(id=identity_id)), \
         patch.object(face_api, "FaceClusterService") as service_class:
        service_class.return_value.preview_identity_rescan.return_value = preview
        response = face_api.preview_identity_rescan(id=identity_id, db=db, current_user=user)

    service_class.assert_called_once_with(db, user_id=user.id)
    service_class.return_value.preview_identity_rescan.assert_called_once_with(identity_id, owner_id=user.id)
    assert response.data["summary"]["add_count"] == 1


def test_apply_identity_rescan_passes_selection_and_updates_affected_photos():
    user = _user()
    db = MagicMock()
    identity_id = uuid4()
    photo_id = uuid4()
    payload = SimpleNamespace(add_face_ids=[10], remove_face_ids=[20])
    result = {
        "status": "success",
        "added_count": 1,
        "removed_count": 1,
        "affected_photo_ids": [str(photo_id)],
    }

    with patch.object(face_api.crud_face, "get_identity", return_value=SimpleNamespace(id=identity_id)), \
         patch.object(face_api, "FaceClusterService") as service_class, \
         patch("app.crud.album.trigger_conditional_albums_update") as trigger:
        service_class.return_value.apply_identity_rescan.return_value = result
        response = face_api.apply_identity_rescan(payload=payload, id=identity_id, db=db, current_user=user)

    service_class.return_value.apply_identity_rescan.assert_called_once_with(
        identity_id,
        owner_id=user.id,
        add_face_ids=[10],
        remove_face_ids=[20],
    )
    trigger.assert_called_once_with(db, user.id, [photo_id])
    assert response.data["added_count"] == 1
    assert "affected_photo_ids" not in response.data


def test_apply_identity_rescan_exposes_stale_preview_as_http_409():
    from app.service.face_cluster import FaceRescanConflictError

    user = _user()
    db = MagicMock()
    identity_id = uuid4()
    payload = SimpleNamespace(add_face_ids=[10], remove_face_ids=[])

    with patch.object(face_api.crud_face, "get_identity", return_value=SimpleNamespace(id=identity_id)), \
         patch.object(face_api, "FaceClusterService") as service_class:
        service_class.return_value.apply_identity_rescan.side_effect = FaceRescanConflictError("stale")
        with pytest.raises(HTTPException) as exc_info:
            face_api.apply_identity_rescan(payload=payload, id=identity_id, db=db, current_user=user)

    assert exc_info.value.status_code == 409
