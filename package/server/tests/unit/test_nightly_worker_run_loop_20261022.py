"""Unit tests for ``app/worker.py``'s asyncio loop (``_run``).

The 2026-10-22 coverage scan showed ``app/worker.py`` at 75.4%
(14 missed of 57). The misses were the body of ``_run`` -- the coroutine
that keeps the worker alive, honours the wake event and performs the
graceful drain on shutdown.

``run_worker`` was already covered (it delegates to ``asyncio.run``), but
``_run`` itself was never executed because every test stubbed it out.

``_run`` is an infinite loop, so these tests drive it with stub events and
stop it by making ``worker.is_drained()`` return ``True`` after the
shutdown event has been raised.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest


pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


class _StubEvent:
    """Minimal stand-in for ``asyncio.Event`` (sync is_set/clear)."""

    def __init__(self, set_on_init=False):
        self._set = set_on_init
        self.cleared = 0

    def is_set(self):
        return self._set

    def set(self):
        self._set = True

    def clear(self):
        self._set = False
        self.cleared += 1


@pytest.fixture
def fast_sleep(monkeypatch):
    """Collapse the worker's poll interval so the loop tests stay instant.

    ``asyncio.sleep`` is patched globally for the duration of the test and
    restored afterwards; the original coroutine is handed back so a test can
    still yield to the event loop deliberately.
    """
    original = asyncio.sleep

    async def _instant(delay, *args, **kwargs):
        return await original(0, *args, **kwargs)

    monkeypatch.setattr(asyncio, "sleep", _instant)
    return original


def _install_worker(monkeypatch, *, drained_after_first_check=False):
    """Patch ``app.worker.TaskWorker`` and return the stub instance."""
    worker = MagicMock(name="TaskWorker")
    checks = {"count": 0}

    def _is_drained():
        checks["count"] += 1
        if drained_after_first_check:
            return checks["count"] >= 2
        return True

    worker.is_drained.side_effect = _is_drained
    monkeypatch.setattr("app.worker.TaskWorker.get_instance", lambda: worker)
    return worker


def test_run_starts_worker_and_publishes_the_event_queue(monkeypatch, fast_sleep):
    worker = _install_worker(monkeypatch)
    shutdown = _StubEvent(set_on_init=True)
    queue = object()

    from app.worker import _run

    # shutdown is already set and the worker reports drained, so the loop
    # exits after one iteration.
    asyncio.run(_run(queue, shutdown))

    worker.set_event_queue.assert_called_once_with(queue)
    worker.start.assert_called_once()
    worker.request_drain.assert_called_once()


def test_run_wakes_the_worker_when_the_wake_event_fires(monkeypatch, fast_sleep):
    worker = _install_worker(monkeypatch)
    wake = _StubEvent(set_on_init=True)
    shutdown = _StubEvent(set_on_init=True)

    from app.worker import _run

    asyncio.run(_run(object(), shutdown, wake))

    worker.wake.assert_called_once()
    # The wake event must be cleared so the next iteration does not spin.
    assert wake.cleared == 1


def test_run_waits_for_drain_before_returning(monkeypatch, fast_sleep):
    """The loop must keep polling until the worker reports it is drained."""
    worker = _install_worker(monkeypatch, drained_after_first_check=True)
    shutdown = _StubEvent(set_on_init=True)

    from app.worker import _run

    asyncio.run(_run(object(), shutdown))

    # First check said "not drained", so the loop polled again.
    assert worker.is_drained.call_count >= 2
    assert worker.request_drain.call_count >= 2


def test_run_without_wake_event_never_calls_wake(monkeypatch, fast_sleep):
    worker = _install_worker(monkeypatch)
    shutdown = _StubEvent(set_on_init=True)

    from app.worker import _run

    asyncio.run(_run(object(), shutdown))

    worker.wake.assert_not_called()
    worker.request_drain.assert_called_once()


def test_run_without_shutdown_event_keeps_polling(monkeypatch, fast_sleep):
    """Without a shutdown event the loop must never request a drain."""
    worker = _install_worker(monkeypatch)
    wake = _StubEvent(set_on_init=True)

    from app.worker import _run

    async def _stop_after_first_iteration():
        task = asyncio.ensure_future(_run(object(), None, wake))
        for _ in range(5):
            await fast_sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(_stop_after_first_iteration())

    worker.start.assert_called_once()
    worker.wake.assert_called_once()
    worker.request_drain.assert_not_called()
    worker.is_drained.assert_not_called()
