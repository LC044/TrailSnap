from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.service.migrations import user_storage_v1


pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


def _connection(dialect: str) -> MagicMock:
    connection = MagicMock()
    connection.dialect = SimpleNamespace(name=dialect)
    return connection


def test_postgres_storage_migration_uses_advisory_lock_and_alembic_transaction():
    connection = _connection("postgresql")
    session = MagicMock()
    result = {"photos": 2, "thumbnails": 3, "users": 1}

    with (
        patch.object(user_storage_v1, "Session", return_value=session),
        patch.object(user_storage_v1, "migrate_legacy_user_storage", return_value=result),
    ):
        actual = user_storage_v1.run(connection)

    assert actual == result
    connection.execute.assert_called_once()
    assert connection.execute.call_args.args[1] == {
        "lock_key": user_storage_v1.POSTGRES_ADVISORY_LOCK_KEY
    }
    session.flush.assert_called_once()
    session.commit.assert_not_called()
    session.close.assert_called_once()


def test_sqlite_storage_migration_skips_postgres_lock():
    connection = _connection("sqlite")
    session = MagicMock()

    with (
        patch.object(user_storage_v1, "Session", return_value=session),
        patch.object(user_storage_v1, "migrate_legacy_user_storage", return_value={}),
    ):
        user_storage_v1.run(connection)

    connection.execute.assert_not_called()
    session.flush.assert_called_once()
    session.commit.assert_not_called()
    session.close.assert_called_once()
