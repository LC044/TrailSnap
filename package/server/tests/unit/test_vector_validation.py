"""Bad inference values must not be persisted as searchable vectors."""

from uuid import uuid4

import pytest
from sqlalchemy.exc import StatementError

from app.db.models.face import Face


pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


@pytest.mark.parametrize("embedding", [
    [None] * 512, [float('nan')] * 512, [float('inf')] * 512,
])
def test_face_vector_rejects_invalid_values_before_sqlite_insert(face_sqlite_session, embedding):
    db = face_sqlite_session
    db.add(Face(photo_id=uuid4(), face_feature=embedding))
    with pytest.raises(StatementError, match="Vector values must be finite numbers"):
        db.flush()
    db.rollback()
    assert db.query(Face).count() == 0


def test_valid_and_absent_face_vectors_round_trip(face_sqlite_session):
    db = face_sqlite_session
    valid = Face(photo_id=uuid4(), face_feature=[0.1] * 512)
    absent = Face(photo_id=uuid4(), face_feature=None)
    db.add_all([valid, absent])
    db.commit()
    db.expire_all()
    assert valid.face_feature == [0.1] * 512
    assert absent.face_feature is None
