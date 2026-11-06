"""Error-path coverage for identity assignment in face clustering.

The existing vectorised SQLite tests cover matching semantics, but the
assignment transaction guards are only exercised through successful paths.
These tests pin down rollback behaviour when the lookup itself fails.
"""

import pytest
from unittest.mock import patch
from sqlalchemy.exc import PendingRollbackError, SQLAlchemyError

from app.service.face_cluster import FaceClusterService

pytestmark = [pytest.mark.smoke, pytest.mark.module_face]


def test_assign_face_to_identity_rolls_back_pending_transaction(face_sqlite_session):
    service = FaceClusterService(db=face_sqlite_session, user_id=None)

    with patch.object(
        service,
        "_sqlite_nearest_assigned_face",
        side_effect=PendingRollbackError("transaction already rolled back"),
    ) as lookup, patch.object(face_sqlite_session, "rollback") as rollback:
        with pytest.raises(PendingRollbackError):
            service.assign_face_to_identity(1, [1.0], None)

    lookup.assert_called_once()
    rollback.assert_called_once()


def test_assign_face_to_identity_rolls_back_database_error(face_sqlite_session):
    service = FaceClusterService(db=face_sqlite_session, user_id=None)

    with patch.object(
        service,
        "_sqlite_nearest_assigned_face",
        side_effect=SQLAlchemyError("database unavailable"),
    ) as lookup, patch.object(face_sqlite_session, "rollback") as rollback:
        with pytest.raises(SQLAlchemyError):
            service.assign_face_to_identity(1, [1.0], None)

    lookup.assert_called_once()
    rollback.assert_called_once()

