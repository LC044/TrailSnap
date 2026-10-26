"""Nightly coverage for ``app.service.tasks.chapter_discovery``.

The 2026-10-24 backend coverage report ranked
``service/tasks/chapter_discovery.py`` at 81.2% with 6 statements never
executed: the rollback branch of ``discover_in_session`` and the strategy's
own metadata properties.

Chapter discovery scans the whole library synchronously and is executed in
a worker thread.  If it blows up mid-scan the session must be rolled back
rather than left in a failed transaction, and a task without an owner must
be rejected instead of scanning every user's chapters.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.service.tasks import chapter_discovery as discovery_mod


pytestmark = [pytest.mark.smoke, pytest.mark.module_album]


def _owner():
    return uuid4()


def test_discover_in_session_reports_created_chapters(monkeypatch):
    """A successful scan reports how many chapters were created."""
    db = MagicMock()
    monkeypatch.setattr(discovery_mod, "SessionLocal", MagicMock(return_value=db))

    row = SimpleNamespace(id=uuid4())
    monkeypatch.setattr(discovery_mod.chapter, "discover", lambda session, owner: [row])

    owner = _owner()
    result = discovery_mod.discover_in_session(owner)

    assert result["created"] == 1
    assert result["chapter_ids"] == [str(row.id)]
    assert isinstance(result["duration_ms"], int)
    assert result["duration_ms"] >= 0
    db.close.assert_called_once()


def test_discover_in_session_rolls_back_and_reraises(monkeypatch):
    """A failing scan must roll the session back and surface the error."""
    db = MagicMock()
    monkeypatch.setattr(discovery_mod, "SessionLocal", MagicMock(return_value=db))

    def _boom(session, owner):
        raise RuntimeError("scan exploded")

    monkeypatch.setattr(discovery_mod.chapter, "discover", _boom)

    with pytest.raises(RuntimeError, match="scan exploded"):
        discovery_mod.discover_in_session(_owner())

    db.rollback.assert_called_once()
    db.close.assert_called_once()


def test_strategy_metadata_is_stable():
    """The strategy advertises a CPU / bounded / named resource profile."""
    strategy = discovery_mod.ChapterDiscoveryStrategy()

    assert strategy.task_category == "CPU"
    assert strategy.resource_key == "chapter_discovery"
    assert strategy.timeout == 60 * 30


def test_process_requires_an_owner():
    """A task without an owner is rejected before any scan starts."""
    task = SimpleNamespace(id="task-1", owner_id=None, payload={})

    with pytest.raises(ValueError):
        asyncio.run(
            discovery_mod.ChapterDiscoveryStrategy().process(worker=None, task=task, db=MagicMock())
        )


def test_process_runs_the_scan_for_the_task_owner(monkeypatch):
    """The scan runs with the owner id taken from the task."""
    owner = _owner()
    task = SimpleNamespace(id="task-1", owner_id=owner, payload={})

    seen = {}

    def _fake_discover(target_owner):
        seen["owner"] = target_owner
        return {"created": 2, "chapter_ids": ["a", "b"], "duration_ms": 3}

    monkeypatch.setattr(discovery_mod, "discover_in_session", _fake_discover)

    result = asyncio.run(
        discovery_mod.ChapterDiscoveryStrategy().process(worker=None, task=task, db=MagicMock())
    )

    assert seen["owner"] == owner
    assert result == {"created": 2, "chapter_ids": ["a", "b"], "duration_ms": 3}
