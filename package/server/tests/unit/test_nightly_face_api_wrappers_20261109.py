"""Nightly watch 2026-11-09 (round 2): face API wrapper gaps.

Targets uncovered branches in ``app/api/face.py`` reported by the 2026-11-09
coverage snapshot:

* ``/clustering/retry`` - restarting the pending-task worker after a retry.
* ``/photos/{id}/{face_id}/similar`` and its assign / undo counterparts - the
  thin wrappers around ``app.service.similar_faces``.
* ``/identities/{id}/rescan`` and ``/rescan/preview`` / ``/rescan/apply`` -
  the 404 guard, the 409 conflict mapping and the conditional album refresh.

Every test exercises already-implemented behaviour; no production code changes.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api import face as face_api
from app.db.base import Base
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
def user(db):
    owner = User(id=uuid4(), username="nightly-face-api-owner", hashed_password="x")
    db.add(owner)
    db.commit()
    return owner


def _identity_result():
    return {"face_count": 2, "photo_ids": [uuid4()], "undo_token": "token"}


# --- clustering retry -------------------------------------------------------

def test_clustering_retry_restarts_the_pending_task_worker(db, user):
    manager = MagicMock()
    with patch("app.service.face_appearance_clusters.retry_clustering", return_value={"queued": 3}) as retry, \
         patch("app.service.task_manager.TaskManager.get_instance", return_value=manager):
        response = face_api.retry_clustering(db=db, current_user=user)

    assert response.data == {"queued": 3}
    retry.assert_called_once_with(db, user.id)
    manager.start_worker_for_pending_tasks.assert_called_once()


# --- similar faces ----------------------------------------------------------

def test_search_similar_faces_delegates_to_the_service(db, user):
    photo_id, face_id = uuid4(), 3
    with patch("app.service.similar_faces.search_similar_faces", return_value=_identity_result()) as search:
        response = face_api.search_similar_faces(photo_id, face_id, db=db, current_user=user)

    assert response.data["undo_token"] == "token"
    assert search.call_args.args[0] is db
    assert search.call_args.args[1] == photo_id
    assert search.call_args.args[2] == face_id


def test_assign_similar_faces_delegates_to_the_service(db, user):
    identity_id = uuid4()
    payload = face_schemas.AssignSimilarFaces(
        identity_id=identity_id,
        selections=[face_schemas.SimilarFaceSelection(face_id=7, review_token="rt")],
    )
    with patch("app.service.similar_faces.assign_similar_faces", return_value=_identity_result()) as assign:
        response = face_api.assign_similar_faces(uuid4(), 7, payload, db=db, current_user=user)

    assert response.data["face_count"] == 2
    assert assign.call_args.args[3] == user.id
    assert assign.call_args.args[4] is payload


def test_undo_face_assignment_delegates_to_the_service(db, user):
    payload = face_schemas.UndoFaceAssignment(undo_token="tok")
    with patch("app.service.similar_faces.undo_face_assignment", return_value=_identity_result()) as undo:
        response = face_api.undo_face_assignment(payload, db=db, current_user=user)

    assert response.data["undo_token"] == "token"
    assert undo.call_args.args[2] == "tok"


# --- identity rescan --------------------------------------------------------

def test_rescan_identity_returns_404_when_the_identity_is_unknown(db, user):
    with patch.object(face_api.crud_face, "get_identity", return_value=None):
        with pytest.raises(HTTPException) as excinfo:
            face_api.rescan_identity(uuid4(), db=db, current_user=user)
    assert excinfo.value.status_code == 404
    assert excinfo.value.detail == "Identity not found"


def test_rescan_identity_triggers_the_conditional_album_update(db, user):
    identity_id = uuid4()
    result = {"affected_photo_ids": [str(uuid4())], "added": 1}

    with patch.object(face_api.crud_face, "get_identity", return_value=MagicMock()), \
         patch("app.service.face_cluster.FaceClusterService") as service_cls, \
         patch("app.crud.album.trigger_conditional_albums_update") as trigger:
        service_cls.return_value.rescan_identity.return_value = dict(result)
        response = face_api.rescan_identity(identity_id, db=db, current_user=user)

    assert response.code == 200
    assert response.data["added"] == 1
    assert "affected_photo_ids" not in response.data
    trigger.assert_called_once()
    assert trigger.call_args.args[2]


def test_preview_identity_rescan_maps_service_errors_to_500(db, user):
    from app.service.face_cluster import FaceRescanError

    with patch.object(face_api.crud_face, "get_identity", return_value=MagicMock()), \
         patch("app.service.face_cluster.FaceClusterService") as service_cls:
        service_cls.return_value.preview_identity_rescan.side_effect = FaceRescanError("boom")
        with pytest.raises(HTTPException) as excinfo:
            face_api.preview_identity_rescan(uuid4(), db=db, current_user=user)

    assert excinfo.value.status_code == 500
    assert excinfo.value.detail == "Face identity rescan preview failed"


def test_apply_identity_rescan_maps_conflicts_to_409(db, user):
    from app.service.face_cluster import FaceRescanConflictError

    payload = face_schemas.FaceRescanApplyRequest(add_face_ids=[1], remove_face_ids=[2])
    with patch.object(face_api.crud_face, "get_identity", return_value=MagicMock()), \
         patch("app.service.face_cluster.FaceClusterService") as service_cls:
        service_cls.return_value.apply_identity_rescan.side_effect = FaceRescanConflictError("changed")
        with pytest.raises(HTTPException) as excinfo:
            face_api.apply_identity_rescan(payload, uuid4(), db=db, current_user=user)

    assert excinfo.value.status_code == 409
    assert excinfo.value.detail == "Face rescan candidates changed; preview again"


def test_apply_identity_rescan_applies_confirmed_changes(db, user):
    identity_id = uuid4()
    payload = face_schemas.FaceRescanApplyRequest(add_face_ids=[1], remove_face_ids=[2])

    with patch.object(face_api.crud_face, "get_identity", return_value=MagicMock()), \
         patch("app.service.face_cluster.FaceClusterService") as service_cls, \
         patch("app.crud.album.trigger_conditional_albums_update") as trigger:
        service_cls.return_value.apply_identity_rescan.return_value = {"added": 1, "removed": 1, "affected_photo_ids": [str(uuid4())]}
        response = face_api.apply_identity_rescan(payload, identity_id, db=db, current_user=user)

    assert response.code == 200
    assert response.data["added"] == 1
    trigger.assert_called_once()

