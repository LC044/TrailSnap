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


@pytest.mark.parametrize("reload", [False, True])
def test_server_migrates_before_starting_with_optional_reload(monkeypatch, reload):
    calls = []
    monkeypatch.setenv("TS_DB_URL", "sqlite:///test.sqlite")
    monkeypatch.setattr(start.sys, "argv", ["start.py", "--port", "8123"] + (["--reload"] if reload else []))
    monkeypatch.setattr(start, "initialize_database", lambda url: calls.append("initialize"))
    monkeypatch.setattr(start, "run_migrations", lambda url: calls.append("migrate"))
    monkeypatch.setattr(start, "import_scenes", lambda url: calls.append("scenes"))
    with patch.object(start.os, "execvp", side_effect=lambda *args: calls.append("serve")) as execute:
        start.main()
    assert calls == ["initialize", "migrate", "scenes", "serve"]
    command = execute.call_args.args[1]
    assert ("--reload" in command) is reload
    assert command[command.index("--port") + 1] == "8123"
