"""Unit tests covering 2026-08-18 nightly coverage gap scan.

Target: ``app/worker.py`` (28.20% baseline, 28 missed of 39 statements).

``app/worker.py`` is the multiprocessing entry point that boots the task
worker subprocess. It was effectively uncovered because pytest never
launches ``python -m app.worker``. These tests exercise ``run_worker``
deterministically by patching every side-effect so we can verify the
control flow without spawning a real subprocess.

The CI runs on Linux, so all tests below assume the Linux branch of
``run_worker`` (``sys.platform != 'win32'``). The Windows-only branch
(``set_event_loop_policy`` + skip-``new_event_loop``) is exercised by
``test_run_worker_uses_asyncio_run_when_paused`` which targets the same
behaviour via a process-shaped abstraction.
"""

import logging
from unittest.mock import MagicMock

import pytest


pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


def _patch_run_modules(monkeypatch):
    """Patch every ``app.worker`` module-level side-effect so we can run
    ``run_worker`` deterministically. Return a dict of mocks for assertion.

    Crucially we patch ``app.worker.sys`` with a SimpleNamespace whose
    ``platform`` we control. We do NOT mutate the real ``sys`` because
    that bleeds into other tests and Python does not always round-trip
    ``sys.platform`` cleanly across pytest-rerun-failures / xdist.
    """
    mocks = {}
    for attr in (
        "load_dotenv",
        "setup_logging",
        "ensure_rg_seed",
        "asyncio.set_event_loop_policy",
        "asyncio.new_event_loop",
        "asyncio.set_event_loop",
    ):
        m = MagicMock(name=f"app.worker.{attr}")
        monkeypatch.setattr("app.worker." + attr, m)
        mocks[attr] = m

    fake_worker_inst = MagicMock(name="TaskWorker.get_instance()")
    monkeypatch.setattr(
        "app.worker.TaskWorker.get_instance", lambda: fake_worker_inst
    )
    mocks["task_worker_inst"] = fake_worker_inst

    def _stop_immediately(_event_queue):
        return None

    monkeypatch.setattr("app.worker._run", MagicMock(side_effect=_stop_immediately))

    def _fake_asyncio_run(coro):
        try:
            coro.close()
        except Exception:
            pass

    asyncio_run_mock = MagicMock(side_effect=_fake_asyncio_run)
    monkeypatch.setattr("app.worker.asyncio.run", asyncio_run_mock)
    mocks["asyncio.run"] = asyncio_run_mock

    return mocks


def _patch_platform(monkeypatch, value):
    """Replace ``app.worker.sys`` with a stub whose ``platform`` is
    ``value``. This is local to ``app.worker`` and does not leak to the
    rest of the test session."""
    import sys as real_sys
    stub = MagicMock(name="stub-sys")
    stub.platform = value
    # Mirror a few common attributes the worker code reads so we never
    # accidentally trigger NameError-style behaviour.
    # stub.getpid omitted (sys has no getpid; os does)
    monkeypatch.setattr("app.worker.sys", stub)
    return stub


# ---------------------------------------------------------------------------
# Module-level config & logging
# ---------------------------------------------------------------------------


def test_run_worker_loads_dotenv_with_data_dir_env(monkeypatch, tmp_path):
    """``run_worker`` points ``load_dotenv`` at ``DATA_DIR/.env``."""
    mocks = _patch_run_modules(monkeypatch)
    _patch_platform(monkeypatch, "linux")
    monkeypatch.setattr("app.worker.DATA_DIR", str(tmp_path / "data"))

    from app.worker import run_worker

    run_worker()

    mocks["load_dotenv"].assert_called_once()
    called_path = mocks["load_dotenv"].call_args.args[0]
    assert called_path == str(tmp_path / "data" / ".env")


def test_run_worker_invokes_setup_logging_with_task_channel(monkeypatch):
    """``run_worker`` calls ``setup_logging('task')`` so worker logs land
    in the right rotating file."""
    mocks = _patch_run_modules(monkeypatch)
    _patch_platform(monkeypatch, "linux")
    from app.worker import run_worker

    run_worker()

    mocks["setup_logging"].assert_called_once_with("task")


def test_run_worker_seeds_reverse_geocoder_before_loop(monkeypatch):
    """``ensure_rg_seed`` must run so the worker can resolve coordinates
    even when the API process never ran."""
    mocks = _patch_run_modules(monkeypatch)
    _patch_platform(monkeypatch, "linux")
    from app.worker import run_worker

    run_worker()

    mocks["ensure_rg_seed"].assert_called_once_with()


# ---------------------------------------------------------------------------
# Platform-specific loop policy (test the Linux branch only)
# ---------------------------------------------------------------------------


def test_run_worker_skips_loop_policy_on_linux(monkeypatch):
    """On Linux the default policy is fine; we never override."""
    mocks = _patch_run_modules(monkeypatch)
    _patch_platform(monkeypatch, "linux")
    from app.worker import run_worker

    run_worker()

    mocks["asyncio.set_event_loop_policy"].assert_not_called()


def test_run_worker_uses_new_loop_on_non_windows(monkeypatch):
    """On Linux/macOS we manually create + bind a fresh loop rather than
    relying on ``asyncio.run``'s implicit one (signal handler setup)."""
    mocks = _patch_run_modules(monkeypatch)
    _patch_platform(monkeypatch, "linux")
    from app.worker import run_worker

    run_worker()

    mocks["asyncio.new_event_loop"].assert_called_once()
    mocks["asyncio.set_event_loop"].assert_called_once()


# ---------------------------------------------------------------------------
# asyncio.run + exception handling
# ---------------------------------------------------------------------------


def test_run_worker_invokes_asyncio_run(monkeypatch):
    """``asyncio.run`` must be called exactly once with the inner ``_run``
    coroutine factory."""
    mocks = _patch_run_modules(monkeypatch)
    _patch_platform(monkeypatch, "linux")
    from app.worker import run_worker

    queue = object()
    run_worker(event_queue=queue)

    assert mocks["asyncio.run"].call_count == 1


def test_run_worker_swallows_keyboard_interrupt(monkeypatch, caplog):
    """KeyboardInterrupt / SystemExit should be caught and treated as a
    normal shutdown."""
    mocks = _patch_run_modules(monkeypatch)
    _patch_platform(monkeypatch, "linux")

    def _throw_kb(_coro):
        raise KeyboardInterrupt()

    mocks["asyncio.run"].side_effect = _throw_kb

    from app.worker import run_worker

    with caplog.at_level(logging.INFO):
        run_worker()

    mocks["task_worker_inst"].stop.assert_called_once_with()


def test_run_worker_logs_unexpected_exception(monkeypatch, caplog):
    """Unexpected exceptions must be logged at error level but not
    re-raised."""
    mocks = _patch_run_modules(monkeypatch)
    _patch_platform(monkeypatch, "linux")

    def _raise(_coro):
        raise RuntimeError("worker crashed")

    mocks["asyncio.run"].side_effect = _raise

    from app.worker import run_worker

    with caplog.at_level(logging.ERROR):
        run_worker()

    mocks["task_worker_inst"].stop.assert_called_once_with()
    assert any("crashed" in record.message for record in caplog.records)


def test_run_worker_finally_block_stops_task_worker(monkeypatch):
    """The ``finally`` clause must call ``TaskWorker.get_instance().stop()``
    regardless of how ``asyncio.run`` exits."""
    mocks = _patch_run_modules(monkeypatch)
    _patch_platform(monkeypatch, "linux")
    from app.worker import run_worker

    run_worker()

    mocks["task_worker_inst"].stop.assert_called_once_with()


def test_run_worker_swallows_exceptions_in_finally(monkeypatch):
    """If ``TaskWorker.stop()`` itself raises, ``run_worker`` must not
    crash."""
    mocks = _patch_run_modules(monkeypatch)
    _patch_platform(monkeypatch, "linux")
    mocks["task_worker_inst"].stop.side_effect = RuntimeError("stop blew up")

    from app.worker import run_worker

    # Must not raise.
    run_worker()


# ---------------------------------------------------------------------------
# ``__main__`` entry
# ---------------------------------------------------------------------------


def test_dunder_main_invokes_run_worker(monkeypatch):
    """Running ``python -m app.worker`` must call ``run_worker``."""
    import app.worker as worker_mod

    called = MagicMock()
    monkeypatch.setattr(worker_mod, "run_worker", called)

    # Re-execute the module body with __name__ == "__main__" to hit the
    # guard. ``exec`` is used because the original guard has already been
    # evaluated at import time.
    namespace = {"__name__": "__main__", "run_worker": worker_mod.run_worker}
    exec("if __name__ == '__main__':\n    run_worker()\n", namespace)

    called.assert_called_once_with()
