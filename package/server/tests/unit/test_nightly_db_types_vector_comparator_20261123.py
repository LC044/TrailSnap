"""Nightly gap coverage: pgvector `<=>` comparator on DatabaseVector.

`DatabaseVector` installs `_VectorComparator` so the distance operator
returns a scalar `Float`.  Without the explicit `return_type` SQLAlchemy
would inherit the vector type from the left operand and try to run the
pgvector result processor on a float, which fails at runtime.
"""

import pytest
from sqlalchemy import Column, MetaData, Table, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.types import Float

from app.db.types import DatabaseVector


pytestmark = pytest.mark.smoke


def _probe_table() -> Table:
    metadata = MetaData()
    return Table(
        "vector_probe",
        metadata,
        Column("embedding", DatabaseVector(3)),
    )


def test_cosine_distance_returns_a_float_typed_expression():
    table = _probe_table()

    expression = table.c.embedding.cosine_distance([1.0, 2.0, 3.0])

    assert isinstance(expression.type, Float)


def test_cosine_distance_compiles_to_the_pgvector_operator():
    table = _probe_table()

    statement = select(table.c.embedding).order_by(
        table.c.embedding.cosine_distance([1.0, 2.0, 3.0])
    )
    sql = str(statement.compile(dialect=postgresql.dialect()))

    assert "<=>" in sql
    assert "ORDER BY" in sql


def test_cosine_distance_is_not_emitted_for_plain_equality():
    """The custom operator must not leak into ordinary comparisons."""
    table = _probe_table()

    statement = select(table.c.embedding).where(table.c.embedding == [1.0, 2.0, 3.0])
    sql = str(statement.compile(dialect=postgresql.dialect()))

    assert "<=>" not in sql
