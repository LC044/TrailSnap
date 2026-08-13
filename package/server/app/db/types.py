"""Database-neutral SQLAlchemy types used by both PostgreSQL and SQLite."""

from __future__ import annotations

import uuid
from typing import Any

from pgvector.sqlalchemy import Vector as PostgreSQLVector
from sqlalchemy import CHAR, JSON, Float
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.types import TypeDecorator


class GUID(TypeDecorator[uuid.UUID]):
    """Store UUID values natively on PostgreSQL and as text on SQLite."""

    impl = CHAR(36)
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PostgreSQLUUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value: Any, dialect):
        if value is None:
            return None
        parsed = value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
        return parsed if dialect.name == "postgresql" else str(parsed)

    def process_result_value(self, value: Any, dialect):
        if value is None or isinstance(value, uuid.UUID):
            return value
        return uuid.UUID(str(value))


class _VectorComparator(TypeDecorator.Comparator):
    def cosine_distance(self, other):
        # pgvector's <=> operator returns a scalar distance, not another vector.
        # Without an explicit return type SQLAlchemy inherits DatabaseVector from
        # the left operand and runs pgvector's vector result processor on the
        # float returned by PostgreSQL (``float is not subscriptable``).
        return self.expr.op("<=>", return_type=Float())(other)


class DatabaseVector(TypeDecorator[list[float]]):
    """Use pgvector on PostgreSQL and a JSON float array on SQLite."""

    impl = JSON
    cache_ok = True
    comparator_factory = _VectorComparator

    def __init__(self, dimensions: int):
        self.dimensions = dimensions
        super().__init__()

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PostgreSQLVector(self.dimensions))
        return dialect.type_descriptor(JSON())

    def process_bind_param(self, value: Any, dialect):
        if value is None:
            return None
        if hasattr(value, "tolist"):
            value = value.tolist()
        result = [float(item) for item in value]
        if len(result) != self.dimensions:
            raise ValueError(
                f"Expected a {self.dimensions}-dimensional vector, got {len(result)}"
            )
        return result


UUID = GUID
Vector = DatabaseVector
VECTOR = DatabaseVector
