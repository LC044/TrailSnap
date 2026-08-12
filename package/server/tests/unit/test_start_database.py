"""Database selection tests for the normal web/server startup entry point."""

from pathlib import Path
from unittest.mock import patch

import pytest

import start

pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


def test_sqlite_initialization_creates_parent_directory(tmp_path: Path):
    database = tmp_path / 'nested' / 'trailsnap.sqlite'
    url = f"sqlite:///{database.as_posix()}"

    start.initialize_database(url)

    assert database.parent.is_dir()
    assert start.is_sqlite_url(url) is True


def test_sqlite_uses_its_own_alembic_branch():
    with patch.object(start.subprocess, 'run') as run:
        start.run_migrations('sqlite:///./data/trailsnap.sqlite')

    run.assert_called_once_with(
        ['alembic', '-c', 'alembic_sqlite.ini', 'upgrade', 'head'],
        check=True,
    )


def test_postgres_uses_default_alembic_branch():
    with patch.object(start.subprocess, 'run') as run:
        start.run_migrations('postgresql://user:pass@localhost/trailsnap')

    run.assert_called_once_with(['alembic', 'upgrade', 'head'], check=True)
