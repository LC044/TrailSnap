"""Regression tests for database-neutral vector distance expressions."""

from sqlalchemy import Float, select
from sqlalchemy.dialects import postgresql

from app.db.models.image_vector import ImageVector


def test_postgres_cosine_distance_is_typed_as_scalar_float():
    """A pgvector distance result must never use the vector result processor."""
    embedding = [1.0] + [0.0] * 511
    distance = ImageVector.embedding.cosine_distance(embedding)

    assert isinstance(distance.type, Float)
    assert distance.type.result_processor(postgresql.dialect(), None) is None

    statement = select(ImageVector, distance.label("distance")).order_by(distance)
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "image_vectors.embedding <=>" in sql
