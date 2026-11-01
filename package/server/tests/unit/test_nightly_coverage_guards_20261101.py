"""Nightly coverage guards for bounded relations and worker guards."""

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import OperationalError

from app.api import relations as relations_api
from app.core import runtime_limits
from app.service.agent.skills import registry as skill_registry
from app.service.desktop_maintenance import (
    DesktopMaintenance,
    DesktopMaintenanceMiddleware,
)


pytestmark = pytest.mark.smoke


def _postgres_db():
    db = MagicMock()
    db.connection.return_value.dialect.name = "postgresql"
    return db


def test_relations_respond_sets_postgres_timeout():
    db = _postgres_db()

    result = relations_api._respond(db, lambda: {"ok": True})

    db.execute.assert_called_once()
    assert result.code == 0
    assert result.data == {"ok": True}


def test_relations_respond_translates_cancelled_postgres_query():
    db = _postgres_db()
    cancelled = Exception("timeout")
    cancelled.pgcode = "57014"
    error = OperationalError("stmt", {}, cancelled)
    def operation():
        raise error

    result = relations_api._respond(db, operation)

    assert result.code == 503
    assert "稍后重试" in result.msg
    db.rollback.assert_called_once()


def test_relations_respond_reraises_unrelated_operational_error():
    db = _postgres_db()
    db.rollback.reset_mock()
    def operation():
        raise OperationalError("stmt", {}, Exception("disk full"))

    with pytest.raises(OperationalError):
        relations_api._respond(db, operation)

    db.rollback.assert_not_called()


@pytest.mark.parametrize(
    ("handler", "method_name", "args"),
    [
        (relations_api.evidence, "evidence", ("left", "right", "photo", 20, "cursor")),
        (relations_api.search, "search", ("person", "query", 20, "cursor")),
    ],
)
def test_relations_endpoints_delegate_to_user_scoped_service(handler, method_name, args):
    db = MagicMock()
    db.connection.return_value.dialect.name = "postgresql"
    user = SimpleNamespace(id="user-1")
    service = MagicMock()
    expected = getattr(service, method_name).return_value

    with patch.object(relations_api, "Relations", return_value=service):
        result = handler(*args, user=user, db=db)

    assert result.data is expected
    getattr(service, method_name).assert_called_once_with(*args)


def test_lower_worker_priority_logs_and_swallows_priority_failure(monkeypatch):
    monkeypatch.setattr(runtime_limits.sys, "platform", "linux")

    def fail():
        raise PermissionError("not permitted")

    monkeypatch.setattr(runtime_limits.os, "nice", fail, raising=False)
    runtime_limits.lower_worker_priority()


def test_skill_parse_reads_plain_instructions(tmp_path):
    path = tmp_path / "plain-skill" / "SKILL.md"
    path.parent.mkdir()
    path.write_text("  Use the bounded API.  ", encoding="utf-8")

    parsed = skill_registry._parse(path)

    assert parsed == {
        "name": "plain-skill",
        "description": "",
        "instructions": "Use the bounded API.",
    }


def test_skill_parse_rejects_invalid_directory_name(tmp_path):
    path = tmp_path / "Invalid_Name" / "SKILL.md"
    path.parent.mkdir()
    path.write_text("instructions", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid skill name"):
        skill_registry._parse(path)


def test_skill_parse_rejects_oversized_file(tmp_path):
    path = tmp_path / "large-skill" / "SKILL.md"
    path.parent.mkdir()
    path.write_text("x" * (skill_registry._MAX_BYTES + 1), encoding="utf-8")

    with pytest.raises(ValueError, match="too large"):
        skill_registry._parse(path)


@pytest.mark.asyncio
async def test_maintenance_prepare_drains_scheduler_active_request_and_manager(monkeypatch):
    from app.service import desktop_maintenance

    maintenance = DesktopMaintenance()
    maintenance.active = 1
    scheduler = MagicMock()
    manager = MagicMock()

    async def finish_sleep(_delay):
        maintenance.active = 0

    async def call_inline(func, **_kwargs):
        return func()

    monkeypatch.setattr(desktop_maintenance.asyncio, "sleep", finish_sleep)
    monkeypatch.setattr(desktop_maintenance.asyncio, "to_thread", call_inline)
    monkeypatch.setitem(
        sys.modules,
        "railway.initialization",
        SimpleNamespace(wait_for_initialization=MagicMock()),
    )

    await maintenance.prepare(scheduler, manager)

    assert maintenance.draining is True
    assert maintenance.active == 0
    scheduler.stop.assert_called_once()
    manager.drain_for_migration.assert_called_once_with()


@pytest.mark.asyncio
async def test_maintenance_middleware_delegates_normal_http_request():
    calls = []

    async def app(scope, receive, send):
        calls.append(scope)

    middleware = DesktopMaintenanceMiddleware(app)
    scope = {"type": "http", "path": "/photos"}

    await middleware(scope, MagicMock(), MagicMock())

    assert calls == [scope]






