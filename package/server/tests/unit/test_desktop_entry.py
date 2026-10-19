"""Fast-path checks for the frozen desktop sidecar bootstrap."""

import os
import errno
import json
import socket
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from fastapi import FastAPI
from fastapi.testclient import TestClient

import desktop_entry


@pytest.mark.smoke
@pytest.mark.module_system
def test_desktop_listener_reports_occupied_port(tmp_path, monkeypatch):
    monkeypatch.setenv('TS_DATA_DIR', str(tmp_path))
    with desktop_entry._bind_desktop_listener(0) as occupied:
        port = occupied.getsockname()[1]
        with pytest.raises(OSError):
            desktop_entry._bind_desktop_listener(port)
        error = json.loads((tmp_path / 'startup-error.json').read_text(encoding='utf-8'))
        assert error['code'] == 'port_bind_failed'
        assert error['port'] == port
        assert '占用' in error['message'] or '拒绝访问' in error['message']


@pytest.mark.smoke
@pytest.mark.module_system
@pytest.mark.parametrize('error,code', [(PermissionError(errno.EACCES, 'denied'), 'port_bind_failed'),
                                       (OSError(errno.ENOBUFS, 'resources'), 'port_listener_failed')])
def test_desktop_listener_classifies_errors_and_closes_socket(tmp_path, monkeypatch, error, code):
    from unittest.mock import Mock
    monkeypatch.setenv('TS_DATA_DIR', str(tmp_path))
    listener = Mock()
    listener.bind.side_effect = error
    monkeypatch.setattr(socket, 'socket', lambda *args: listener)
    with pytest.raises(OSError):
        desktop_entry._bind_desktop_listener(2688)
    listener.close.assert_called_once()
    result = json.loads((tmp_path / 'startup-error.json').read_text(encoding='utf-8'))
    assert result['code'] == code
    if isinstance(error, PermissionError):
        assert '保留端口' in result['message']


@pytest.mark.smoke
@pytest.mark.module_system
def test_desktop_startup_does_not_import_optional_processing_dependencies(tmp_path):
    # A fresh interpreter is essential: other tests may already import NumPy,
    # PostgreSQL types or LLM clients before this test is collected.
    environment = {
        **os.environ,
        "TS_DESKTOP": "1",
        "TS_DATA_DIR": str(tmp_path),
        "TS_DB_URL": f"sqlite:///{(tmp_path / 'trailsnap.sqlite').as_posix()}",
        "RAILWAY_DB_URL": f"sqlite:///{(tmp_path / 'railway.sqlite').as_posix()}",
    }
    result = subprocess.run(
        [sys.executable, "-c", """
import sys
import main
optional = ('numpy', 'cv2', 'pgvector', 'langchain_core', 'zeroconf', 'mcp')
loaded = [name for name in optional if name in sys.modules]
assert not loaded, f'Optional dependencies loaded during desktop startup: {loaded}'
assert '/auth/desktop-session' in main.app.openapi()['paths']
"""],
        cwd=Path(__file__).resolve().parents[2],
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr


def test_database_is_current_for_bundled_schema(tmp_path):
    database = tmp_path / "trailsnap.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        connection.execute(
            "INSERT INTO alembic_version(version_num) VALUES (?)",
            (desktop_entry.DESKTOP_SCHEMA_REVISION,),
        )

    assert desktop_entry._database_is_current(database) is True


def test_database_is_current_rejects_missing_or_old_schema(tmp_path):
    assert desktop_entry._database_is_current(tmp_path / "missing.sqlite") is False

    database = tmp_path / "old.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        connection.execute("INSERT INTO alembic_version(version_num) VALUES ('sqlite_0004')")

    assert desktop_entry._database_is_current(database) is False


def test_desktop_sidecar_accepts_frontend_api_prefix():
    app = FastAPI()

    @app.get("/health-check")
    def health_check():
        return {"status": "ok"}

    desktop_entry._apply_desktop_api_prefix(app)
    client = TestClient(app)

    assert client.get("/api/health-check").status_code == 200
    assert client.get("/health-check").status_code == 200
