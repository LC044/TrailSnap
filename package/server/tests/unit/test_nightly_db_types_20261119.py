"""2026-11-19 nightly coverage for ``app/db/types.py``.

``GUID.load_dialect_impl`` / ``process_bind_param`` / ``process_result_value``
and the ``DatabaseVector`` / ``PortableJSON`` helpers were never referenced by
any test file.  They are the portability seam between PostgreSQL (pgvector,
native UUID) and SQLite (JSON array, CHAR(36)), so the round trips are
asserted here without touching a database.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql, sqlite

from app.db.types import DatabaseVector, GUID, PortableJSON


pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


# Dialects are used directly: no DB connection is needed to exercise the
# type's dialect-dependent behaviour.
SQLITE = sqlite.dialect()
POSTGRES = postgresql.dialect()


def test_guid_uses_a_uuid_column_on_postgres():
    dialect = POSTGRES

    assert dialect.name == "postgresql"
    assert type(GUID().load_dialect_impl(dialect)).__name__ == "PGUuid"


def test_guid_uses_a_char_column_on_sqlite():
    dialect = SQLITE

    assert type(GUID().load_dialect_impl(dialect)).__name__ == "CHAR"


def test_guid_binds_a_uuid_object_on_postgres():
    value = uuid.uuid4()

    assert GUID().process_bind_param(value, POSTGRES) is value


def test_guid_binds_a_uuid_as_text_on_sqlite():
    value = uuid.uuid4()

    assert GUID().process_bind_param(value, SQLITE) == str(value)


def test_guid_accepts_a_uuid_string_and_normalises_it():
    value = uuid.uuid4()

    assert GUID().process_bind_param(str(value), SQLITE) == str(value)


def test_guid_passes_none_through():
    assert GUID().process_bind_param(None, SQLITE) is None


def test_guid_rejects_a_malformed_uuid():
    with pytest.raises(ValueError):
        GUID().process_bind_param("not-a-uuid", SQLITE)


def test_guid_reads_a_text_value_back_as_a_uuid():
    value = uuid.uuid4()

    result = GUID().process_result_value(str(value), SQLITE)

    assert isinstance(result, uuid.UUID)
    assert result == value


def test_guid_passes_a_uuid_result_through_unchanged():
    value = uuid.uuid4()

    assert GUID().process_result_value(value, SQLITE) is value


def test_guid_passes_a_none_result_through():
    assert GUID().process_result_value(None, SQLITE) is None


def test_vector_uses_a_json_column_on_sqlite():
    assert isinstance(DatabaseVector(3).load_dialect_impl(SQLITE), sa.JSON)


def test_vector_binds_a_list_of_floats():
    assert DatabaseVector(3).process_bind_param([1, 2, 3], SQLITE) == [1.0, 2.0, 3.0]


def test_vector_accepts_a_numpy_like_value_with_tolist():
    class _FakeArray:
        def tolist(self):
            return [1, 2, 3]

    assert DatabaseVector(3).process_bind_param(_FakeArray(), SQLITE) == [1.0, 2.0, 3.0]


def test_vector_rejects_a_wrong_dimension():
    with pytest.raises(ValueError, match="Expected a 3-dimensional vector"):
        DatabaseVector(3).process_bind_param([1, 2], SQLITE)


def test_vector_rejects_non_finite_values():
    with pytest.raises(ValueError, match="Vector values must be finite numbers"):
        DatabaseVector(3).process_bind_param([1, float("inf"), 3], SQLITE)


def test_vector_rejects_non_numeric_values():
    with pytest.raises(ValueError, match="Vector values must be finite numbers"):
        DatabaseVector(3).process_bind_param([1, "x", 3], SQLITE)


def test_vector_passes_none_through():
    assert DatabaseVector(3).process_bind_param(None, SQLITE) is None


def test_portable_json_encodes_paths_on_bind_and_decodes_on_result():
    value = {"path": "C:/photos/a.jpg"}

    encoded = PortableJSON().process_bind_param(value, SQLITE)
    decoded = PortableJSON().process_result_value(encoded, SQLITE)

    assert isinstance(encoded, dict)
    assert isinstance(decoded, dict)
    assert set(decoded.keys()) == set(value.keys())


def test_portable_json_coerces_a_compared_value():
    coerced = PortableJSON().coerce_compared_value("==", "x")
    assert coerced is not None



