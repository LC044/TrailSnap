"""Read-only PostgreSQL regression for pgvector cosine-distance decoding."""

import os

import pytest
from pgvector.sqlalchemy import Vector as PostgreSQLVector
from sqlalchemy import cast, create_engine, literal, select, type_coerce

from app.db.types import Vector


pytestmark = [
    pytest.mark.regression,
    pytest.mark.module_search,
    pytest.mark.postgres,
]


def test_pgvector_cosine_distance_decodes_as_float():
    database_url = os.environ.get("DB_URL") or os.environ.get("TS_DB_URL")
    if not database_url or not database_url.startswith("postgresql"):
        pytest.skip("A PostgreSQL TS_DB_URL is required")

    engine = create_engine(database_url)
    vector_type = Vector(512)
    raw_vector = [1.0] + [0.0] * 511
    # Explicit casts disambiguate pgvector's vector/halfvec overloads for
    # constants. type_coerce keeps the app's DatabaseVector comparator on the
    # left so this executes the same result-decoding path as ImageVector.
    left = type_coerce(
        cast(literal(raw_vector, type_=PostgreSQLVector(512)), PostgreSQLVector(512)),
        vector_type,
    )
    right = cast(literal(raw_vector, type_=PostgreSQLVector(512)), PostgreSQLVector(512))

    try:
        with engine.connect() as connection:
            distance = connection.scalar(select(left.cosine_distance(right)))
    finally:
        engine.dispose()

    assert isinstance(distance, float)
    assert distance == pytest.approx(0.0)
