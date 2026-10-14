"""Database-neutral SQLAlchemy types used by both PostgreSQL and SQLite."""

from __future__ import annotations

import uuid
import math
from typing import Any

from sqlalchemy import CHAR, JSON, Float
from sqlalchemy.types import TypeDecorator


class PortableJSON(TypeDecorator):
    """JSON with explicit portable path fields; servers retain identical JSON."""
    impl = JSON
    cache_ok = True
    hashable = False

    def coerce_compared_value(self, op, value):
        return self.impl.coerce_compared_value(op, value)

    def process_bind_param(self, value, dialect):
        from app.utils.portable_config import transform_paths
        return transform_paths(value, encode=True)

    def process_result_value(self, value, dialect):
        from app.utils.portable_config import transform_paths
        return transform_paths(value, encode=False)


class GUID(TypeDecorator[uuid.UUID]):
    """Store UUID values natively on PostgreSQL and as text on SQLite."""

    impl = CHAR(36)
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID

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
    # ORM queries mixing an entity and a vector column deduplicate result rows.
    # SQLite returns lists (PostgreSQL returns arrays), which cannot be hashed.
    hashable = False
    comparator_factory = _VectorComparator

    def __init__(self, dimensions: int):
        self.dimensions = dimensions
        super().__init__()

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            # SQLite stores JSON vectors and must not load pgvector/NumPy.
            from pgvector.sqlalchemy import Vector as PostgreSQLVector

            return dialect.type_descriptor(PostgreSQLVector(self.dimensions))
        return dialect.type_descriptor(JSON())

    def process_bind_param(self, value: Any, dialect):
        if value is None:
            return None
        if hasattr(value, "tolist"):
            value = value.tolist()
        try:
            result = [float(item) for item in value]
        except (TypeError, ValueError, OverflowError) as error:
            raise ValueError("Vector values must be finite numbers") from error
        if len(result) != self.dimensions:
            raise ValueError(
                f"Expected a {self.dimensions}-dimensional vector, got {len(result)}"
            )
        if not all(math.isfinite(item) for item in result):
            raise ValueError("Vector values must be finite numbers")
        return result


UUID = GUID
Vector = DatabaseVector
VECTOR = DatabaseVector
