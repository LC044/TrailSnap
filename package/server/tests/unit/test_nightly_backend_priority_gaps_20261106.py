"""Nightly coverage guards for 2026-11-06 backend priority gaps."""

import pytest


from app.db.models.face import FaceIdentity
from app.db.models.user import User
from app.service.face_cluster import FaceClusterService
from app.service.task_worker import TaskQueueManager

pytestmark = pytest.mark.smoke


def test_identity_rescan_without_reference_faces_is_a_safe_empty_analysis(
    face_sqlite_session,
):
    """A person with no live assigned faces must return an empty preview."""
    user = User(
        username="rescan-empty-user",
        email="rescan-empty-user@example.com",
        hashed_password="unused",
    )
    face_sqlite_session.add(user)
    face_sqlite_session.flush()
    identity = FaceIdentity(identity_name="Rescan Empty", owner_id=user.id)
    face_sqlite_session.add(identity)
    face_sqlite_session.commit()

    service = FaceClusterService(db=face_sqlite_session, user_id=user.id)
    analysis = service._analyze_identity_rescan(
        identity.id, user.id, lock=False
    )

    assert analysis["identity_id"] == identity.id
    assert analysis["reason"] == "no_reference_faces"
    assert analysis["prototypes"] == []
    assert analysis["add_candidates"] == []
    assert analysis["remove_candidates"] == []


def test_task_queue_reports_empty_queue_priority_floor():
    """An empty priority queue has no real priority and reports the floor."""
    manager = TaskQueueManager()
    assert manager.get_lowest_priority("AI") == -9999
    assert manager.get_lowest_priority("UNKNOWN") == -9999


