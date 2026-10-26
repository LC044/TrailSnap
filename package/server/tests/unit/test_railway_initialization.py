"""First-install railway imports must not block or strand onboarding."""
import threading

import pytest
from fastapi import HTTPException

from railway import initialization

pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


@pytest.fixture(autouse=True)
def isolate_history_seed(monkeypatch):
    from railway import history_seed
    monkeypatch.setattr(history_seed, 'ensure_history_seed', lambda: None)


def test_background_import_returns_before_completion(tmp_path, monkeypatch):
    from app.core import paths
    from railway import start

    entered, release = threading.Event(), threading.Event()
    monkeypatch.setattr(paths, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(initialization, "_state", "pending")
    monkeypatch.setattr(initialization, "_thread", None)

    def slow_import():
        entered.set()
        release.wait(5)

    monkeypatch.setattr(start, "create_database", slow_import)
    initialization.start_background_initialization()
    try:
        assert entered.wait(2)
        with pytest.raises(HTTPException) as error:
            initialization.require_ready()
        assert error.value.status_code == 503
    finally:
        release.set()
        initialization._thread.join(3)
    initialization.require_ready()


def test_failed_background_import_explains_retry(tmp_path, monkeypatch):
    from app.core import paths
    from railway import start

    monkeypatch.setattr(paths, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(initialization, "_state", "pending")
    monkeypatch.setattr(start, "create_database", lambda: (_ for _ in ()).throw(RuntimeError("import failed")))
    initialization._initialize()
    with pytest.raises(HTTPException, match="初始化失败"):
        initialization.require_ready()


def test_railway_api_waits_without_opening_database(monkeypatch):
    monkeypatch.setenv("RAILWAY_DB_URL", "sqlite:///:memory:")
    from railway.db import dependencies
    monkeypatch.setattr(initialization, "_state", "pending")
    monkeypatch.setattr(dependencies, "SessionLocal", lambda: pytest.fail("database opened before readiness"))
    with pytest.raises(HTTPException) as error:
        next(dependencies.get_ready_db())
    assert error.value.status_code == 503
