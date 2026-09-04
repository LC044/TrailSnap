"""Regression tests for the standalone CLUSTER_FACES task.

Clustering used to run inline inside RECOGNIZE_FACE. The three properties
asserted here are exactly the ones whose absence caused the NAS symptom
"recognition is slow, AI container idle, server container at 90%+ CPU":

* it does not share the recognition resource slot,
* it does not block the event loop,
* deferring must not silently drop the task (the worker deletes anything it
  sees as completed, so a ``{'status': 'deferred'}`` return value would mean
  clustering never happens).
"""
import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest


pytestmark = [pytest.mark.smoke]


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


_UNSET = object()


def _task(owner_id=_UNSET, **kw):
    base = {
        "id": uuid4(),
        "type": "CLUSTER_FACES",
        "owner_id": uuid4() if owner_id is _UNSET else owner_id,
        "payload": {},
        "status": "processing",
        "attempt_count": 1,
        "next_retry_at": None,
        "error": "previous",
    }
    base.update(kw)
    return SimpleNamespace(**base)


def _strategy():
    from app.service.tasks.face_cluster import ClusterFacesStrategy

    return ClusterFacesStrategy()


def _db(recognition_pending: bool):
    db = MagicMock(name="db")
    q = MagicMock()
    q.filter.return_value = q
    q.first.return_value = object() if recognition_pending else None
    db.query.return_value = q
    return db


# ---------------------------------------------------------------------------
# Strategy declaration
# ---------------------------------------------------------------------------


def test_cluster_faces_uses_cpu_queue_and_dedicated_resource_key():
    s = _strategy()
    assert s.task_category == "CPU"
    # Sharing 'face' would hold the single recognition slot, which is the
    # stall this task type exists to remove.
    assert s.resource_key == "face_cluster"


def test_cluster_faces_timeout_is_longer_than_the_default():
    from app.service.task_strategy import BaseTaskStrategy

    # The 5 minute default would abort a large pass, and the timeout message
    # matches _is_retryable_error, so the same CPU work would be burned three
    # times before the task finally failed.
    assert _strategy().timeout > BaseTaskStrategy.timeout.fget(BaseTaskStrategy)
    assert _strategy().timeout == 3600


def test_cluster_faces_is_registered_with_a_dedicated_chunk_size():
    from app.db.models.task import TaskType
    from app.service.task_strategy import TaskStrategyFactory
    from app.service.task_worker import get_chunk_size

    assert TaskStrategyFactory.get_strategy(TaskType.CLUSTER_FACES) is not None
    # Batching several owners together would serialise their passes inside one
    # timeout window.
    assert get_chunk_size(TaskType.CLUSTER_FACES) == 1


def test_cluster_faces_priority_is_below_recognition():
    from app.db.models.task import DEFAULT_PRIORITIES, TaskType

    assert (
        DEFAULT_PRIORITIES[TaskType.CLUSTER_FACES]
        < DEFAULT_PRIORITIES[TaskType.RECOGNIZE_FACE]
    )


def test_cluster_faces_resource_limit_stays_one_on_every_level():
    from app.service import task_worker

    worker = task_worker.TaskWorker()
    for level in ("low", "medium", "high"):
        with patch.object(task_worker, "resolve_concurrency_level", lambda _l, _v=level: _v):
            assert worker._get_resource_limits()["face_cluster"] == 1


# ---------------------------------------------------------------------------
# Defer guard
# ---------------------------------------------------------------------------


def test_cluster_faces_defers_while_recognition_is_in_flight():
    db = _db(recognition_pending=True)
    task = _task()
    s = _strategy()

    with patch("app.service.tasks.face_cluster._cluster_in_thread") as cluster:
        result = _run(s.process(MagicMock(), task, db))

    cluster.assert_not_called()
    assert result is None
    assert task.status == "pending"
    assert isinstance(task.next_retry_at, datetime)
    db.commit.assert_called_once()


def test_cluster_faces_defer_does_not_consume_a_retry_attempt():
    """Waiting is not a failed attempt.

    Counting it would let a long import exhaust max_attempts and mark
    clustering FAILED.
    """
    db = _db(recognition_pending=True)
    task = _task(attempt_count=2)
    _run(_strategy().process(MagicMock(), task, db))
    assert task.attempt_count == 2


def test_cluster_faces_deferred_task_is_omitted_from_results():
    """A deferred row must not be reported as completed.

    ``_flush_results`` deletes every completed task, so reporting the defer
    would drop the row and clustering would never run.
    """
    db = _db(recognition_pending=True)
    task = _task()
    results = _run(_strategy().process_batch(MagicMock(), [task], db))
    assert results == []


def test_cluster_faces_defer_guard_is_scoped_to_the_owner():
    from app.db.models.task import Task

    db = _db(recognition_pending=False)
    task = _task()
    with patch("app.service.tasks.face_cluster._cluster_in_thread"):
        _run(_strategy().process(MagicMock(), task, db))

    filters = db.query.return_value.filter.call_args.args
    assert any(
        getattr(getattr(f, "left", None), "key", None) == "owner_id" for f in filters
    ), f"owner_id filter missing from {filters}"
    db.query.assert_called_with(Task.id)


# ---------------------------------------------------------------------------
# Clustering execution
# ---------------------------------------------------------------------------


def test_cluster_faces_runs_off_the_event_loop():
    """The pass must go through an executor.

    Calling it directly from the coroutine froze the producer loop, the other
    consumers and SSE progress, and made asyncio.wait_for ineffective.
    """
    db = _db(recognition_pending=False)
    owner_id = uuid4()
    task = _task(owner_id=owner_id)
    seen = {}

    real_loop_getter = asyncio.get_running_loop

    async def _drive():
        loop = real_loop_getter()
        original = loop.run_in_executor

        def _spy(executor, func, *args):
            seen["called"] = True
            seen["args"] = args
            return original(executor, func, *args)

        with patch.object(loop, "run_in_executor", _spy), \
             patch("app.service.tasks.face_cluster._cluster_in_thread") as cluster:
            result = await _strategy().process(MagicMock(), task, db)
        return result, cluster

    result, cluster = _run(_drive())

    assert seen.get("called") is True
    assert seen["args"] == (owner_id,)
    cluster.assert_called_once_with(owner_id)
    assert result == {"status": "success"}


def test_cluster_faces_skips_task_without_owner():
    db = _db(recognition_pending=False)
    task = _task(owner_id=None)
    with patch("app.service.tasks.face_cluster._cluster_in_thread") as cluster:
        result = _run(_strategy().process(MagicMock(), task, db))
    cluster.assert_not_called()
    assert result["status"] == "skipped"


def test_cluster_faces_uses_its_own_session_in_the_worker_thread():
    """A Session is not thread-safe, so the pass must open its own."""
    from app.service.tasks import face_cluster

    owner_id = uuid4()
    session = MagicMock(name="session")
    service = MagicMock(name="service")

    with patch("app.db.session.SessionLocal", return_value=session), \
         patch("app.service.face_cluster.FaceClusterService", return_value=service) as factory:
        face_cluster._cluster_in_thread(owner_id)

    factory.assert_called_once_with(session, owner_id)
    service.process_unassigned_faces.assert_called_once_with(owner_id)
    session.close.assert_called_once()


def test_cluster_faces_reports_failure_for_the_batch():
    db = _db(recognition_pending=False)
    task = _task()
    with patch(
        "app.service.tasks.face_cluster._cluster_in_thread",
        side_effect=RuntimeError("dbscan exploded"),
    ):
        results = _run(_strategy().process_batch(MagicMock(), [task], db))

    assert len(results) == 1
    assert results[0]["status"] == "failed"
    assert "dbscan exploded" in results[0]["error"]


# ---------------------------------------------------------------------------
# enqueue_cluster_faces
# ---------------------------------------------------------------------------


def test_enqueue_cluster_faces_reuses_an_outstanding_task():
    """Deduplication is what collapses an import round into one pass."""
    from app.service.tasks.face_cluster import enqueue_cluster_faces

    existing = _task()
    db = MagicMock()
    with patch("app.crud.task.get_latest_task_by_type_and_owner", return_value=existing), \
         patch("app.crud.task.add_task") as add_task:
        result = enqueue_cluster_faces(db, existing.owner_id)

    assert result is existing
    add_task.assert_not_called()


def test_enqueue_cluster_faces_creates_a_pending_task():
    from app.db.models.task import TaskStatus, TaskType
    from app.service.tasks.face_cluster import enqueue_cluster_faces

    owner_id = uuid4()
    db = MagicMock()
    with patch("app.crud.task.get_latest_task_by_type_and_owner", return_value=None) as lookup, \
         patch("app.crud.task.add_task", return_value="created") as add_task:
        result = enqueue_cluster_faces(db, owner_id)

    assert result == "created"
    assert lookup.call_args.args[1] == TaskType.CLUSTER_FACES
    assert lookup.call_args.args[3] == [TaskStatus.PENDING, TaskStatus.PROCESSING]
    assert add_task.call_args.args[1] == TaskType.CLUSTER_FACES
    assert add_task.call_args.kwargs["owner_id"] == owner_id


def test_enqueue_cluster_faces_ignores_missing_owner():
    from app.service.tasks.face_cluster import enqueue_cluster_faces

    db = MagicMock()
    with patch("app.crud.task.add_task") as add_task:
        assert enqueue_cluster_faces(db, None) is None
    add_task.assert_not_called()
