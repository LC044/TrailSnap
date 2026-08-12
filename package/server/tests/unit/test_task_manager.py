"""Unit tests for ``app/service/task_manager.py``.

The TaskManager is the API-process-side controller of the worker subprocess.
We focus on the pieces that do not require a real DB or a real worker
process, so we can exercise the control plane in milliseconds.

Coverage:

* Singleton lifecycle (``get_instance`` memoises a single instance).
* ``paused_categories`` is loaded from / persisted to ``SystemState``.
* ``set_fast_mode`` writes the same key through to ``SystemState``.
* ``subscribe`` / ``unsubscribe`` register queues; ``publish_event``
  delivers to every connected subscriber.
* ``publish_task_update`` builds a JSON-friendly payload out of an ORM row.
* ``attach_loop`` + ``publish_event`` use ``call_soon_threadsafe`` when a
  loop is attached; otherwise fall through to direct publish.
"""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Force a fresh TaskManager per test so internal state never leaks."""
    from app.service import task_manager as tm_mod

    tm_mod.TaskManager._instance = None
    yield
    tm_mod.TaskManager._instance = None


def _make_system_state_stub():
    """Build a stub ``SystemState`` row mirroring what the manager reads."""

    state = MagicMock()
    state.value = None
    return state


def test_get_instance_returns_singleton():
    from app.service.task_manager import TaskManager

    a = TaskManager.get_instance()
    b = TaskManager.get_instance()
    assert a is b


def test_get_status_reads_fast_mode_from_system_state():
    from app.service.task_manager import TaskManager

    manager = TaskManager.get_instance()

    # No prior state -> default False.
    with patch.object(manager, "_load_system_state", return_value=False) as load:
        assert manager.get_status() == {"fast_mode": False}
    load.assert_called_with("fast_mode", False)


def test_get_status_propagates_persisted_fast_mode_true():
    from app.service.task_manager import TaskManager

    manager = TaskManager.get_instance()
    with patch.object(manager, "_load_system_state", return_value=True):
        assert manager.get_status() == {"fast_mode": True}


def test_pause_category_persists_to_system_state():
    from app.service.task_manager import TaskManager

    manager = TaskManager.get_instance()

    # Empty initial state -> category is added.
    with patch.object(manager, "_load_system_state", return_value=[]), \
         patch.object(manager, "_save_system_state") as save:
        manager.pause_category("face")
    save.assert_called_once_with("paused_categories", ["face"])


def test_pause_category_does_not_duplicate_existing():
    from app.service.task_manager import TaskManager

    manager = TaskManager.get_instance()

    with patch.object(manager, "_load_system_state", return_value=["face"]), \
         patch.object(manager, "_save_system_state") as save:
        manager.pause_category("face")
    save.assert_called_once_with("paused_categories", ["face"])


def test_resume_category_drops_entry_and_starts_worker():
    from app.service.task_manager import TaskManager

    manager = TaskManager.get_instance()

    with patch.object(manager, "_load_system_state", return_value=["face", "ocr"]), \
         patch.object(manager, "_save_system_state") as save, \
         patch.object(manager, "start_worker_if_needed") as start:
        manager.resume_category("face")
    save.assert_called_once_with("paused_categories", ["ocr"])
    start.assert_called_once()


def test_resume_category_noop_when_not_paused():
    from app.service.task_manager import TaskManager

    manager = TaskManager.get_instance()

    with patch.object(manager, "_load_system_state", return_value=["ocr"]), \
         patch.object(manager, "_save_system_state") as save, \
         patch.object(manager, "start_worker_if_needed") as start:
        manager.resume_category("face")
    # No save, no worker startup -- the category was never paused.
    save.assert_not_called()
    start.assert_not_called()


def test_set_fast_mode_persists_boolean():
    from app.service.task_manager import TaskManager

    manager = TaskManager.get_instance()

    with patch.object(manager, "_save_system_state") as save:
        manager.set_fast_mode(True)
    save.assert_called_once_with("fast_mode", True)


def test_subscribe_and_publish_event_delivers_to_all_subscribers():
    """Async queues receive published events without an attached loop."""
    from app.service.task_manager import TaskManager

    manager = TaskManager.get_instance()

    async def _run():
        q1 = manager.subscribe()
        q2 = manager.subscribe()
        # No loop attached -> falls through to direct publish path.
        manager._loop = None
        manager.publish_event("task.updated", {"id": "abc"})
        msg1 = await asyncio.wait_for(q1.get(), timeout=1)
        msg2 = await asyncio.wait_for(q2.get(), timeout=1)
        return msg1, msg2

    msg1, msg2 = asyncio.run(_run())
    assert msg1 == {"event": "task.updated", "data": {"id": "abc"}}
    assert msg2 == {"event": "task.updated", "data": {"id": "abc"}}


def test_unsubscribe_removes_queue():
    from app.service.task_manager import TaskManager

    manager = TaskManager.get_instance()

    q = manager.subscribe()
    manager.unsubscribe(q)
    assert q not in manager._subscribers


def test_publish_event_drops_closed_subscriber(monkeypatch):
    """A subscriber whose ``put_nowait`` raises should be silently skipped."""
    from app.service.task_manager import TaskManager

    manager = TaskManager.get_instance()
    manager._loop = None

    class _BoomQueue:
        full = staticmethod(lambda: False)
        @staticmethod
        def put_nowait(_):
            raise RuntimeError("closed")

    bad = _BoomQueue()
    manager._subscribers.append(bad)

    # Patch NotificationManager bridge to a no-op (avoid importing subprocess chain).
    monkeypatch.setattr(
        "app.service.notification_manager.NotificationManager.get_instance",
        lambda: MagicMock(),
    )

    # Must not raise.
    manager.publish_event("task.updated", {"id": "abc"})


def test_publish_task_update_builds_json_payload():
    """``publish_task_update`` flattens the ORM row to a JSON-friendly dict."""
    from app.service.task_manager import TaskManager

    manager = TaskManager.get_instance()
    manager._loop = None

    task = SimpleNamespace(
        id="tid-1",
        type="PROCESS_BASIC",
        status="PENDING",
        priority=10,
        total_items=42,
        processed_items=7,
        error=None,
        owner_id=None,
        created_at=None,
        updated_at=None,
        payload={"foo": "bar"},
    )

    captured = []

    def capture(event, data):
        captured.append((event, data))

    with patch.object(manager, "publish_event", side_effect=capture):
        manager.publish_task_update(task, event="task.created")

    event, data = captured[0]
    assert event == "task.created"
    # All values are JSON-safe strings / dicts.
    json.dumps(data)
    assert data["id"] == "tid-1"
    assert data["type"] == "PROCESS_BASIC"
    assert data["payload"] == {"foo": "bar"}


def test_attach_loop_then_publish_uses_call_soon_threadsafe():
    """When a loop is attached, ``publish_event`` schedules a coroutine on it."""
    from app.service.task_manager import TaskManager

    manager = TaskManager.get_instance()
    loop = asyncio.new_event_loop()
    try:
        manager.attach_loop(loop)

        scheduled = []

        def fake_call_soon_threadsafe(fn, *args, **kwargs):
            scheduled.append((fn, args))

        with patch.object(loop, "call_soon_threadsafe", side_effect=fake_call_soon_threadsafe):
            manager.publish_event("task.updated", {"id": "abc"})

        assert len(scheduled) == 1
        fn, args = scheduled[0]
        # First arg after fn is the event name, second is the payload.
        assert fn.__func__ is manager._do_publish.__func__
        assert args == ("task.updated", {"id": "abc"})
    finally:
        loop.close()


def test_attach_loop_loop_closed_falls_back(monkeypatch):
    """When the attached loop is closed, publish_event must not raise."""
    from app.service.task_manager import TaskManager

    manager = TaskManager.get_instance()

    class _DeadLoop:
        def call_soon_threadsafe(self, *_a, **_kw):
            raise RuntimeError("loop closed")

    manager.attach_loop(_DeadLoop())
    monkeypatch.setattr(
        "app.service.notification_manager.NotificationManager.get_instance",
        lambda: MagicMock(),
    )
    # Should not raise, even though the loop is unusable.
    manager.publish_event("task.updated", {"id": "abc"})


def test_scan_folder_dedup_query_works_on_sqlite(tmp_path):
    """JSON user_id lookup must compile for SQLite as well as PostgreSQL."""
    from app.db.base import Base
    from app.db.models.task import Task, TaskStatus, TaskType
    from app.service.task_manager import TaskManager

    engine = create_engine(f"sqlite:///{(tmp_path / 'tasks.sqlite').as_posix()}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        existing = Task(
            type=TaskType.SCAN_FOLDER,
            status=TaskStatus.PENDING,
            payload={"user_id": "sqlite-user", "scan_roots": ["/photos"]},
        )
        session.add(existing)
        session.commit()

        manager = TaskManager.get_instance()
        reused = manager.add_task(
            session,
            TaskType.SCAN_FOLDER,
            {"user_id": "sqlite-user", "scan_roots": ["/photos"]},
        )

        assert reused.id == existing.id
        assert session.query(Task).count() == 1
    finally:
        session.close()
        engine.dispose()
