"""Face vector cache streaming statement construction."""
import pytest
from sqlalchemy.dialects import postgresql

from app.service.face_vector_cache import _vector_stmt

pytestmark = [pytest.mark.smoke, pytest.mark.module_face]


def _sql(statement):
    return str(statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


def test_statement_filters_out_null_features():
    assert "face_feature IS NOT NULL" in _sql(_vector_stmt(None, 0))


def test_statement_only_returns_faces_after_the_cursor():
    assert "faces.id > 42" in _sql(_vector_stmt(None, 42))


def test_owner_scope_adds_a_photo_subquery():
    from uuid import uuid4

    scoped = _sql(_vector_stmt(uuid4(), 0))
    assert "photos.id" in scoped
    assert "owner_id" in scoped
