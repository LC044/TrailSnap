"""Nightly gap tests: ``app/utils/process_lifecycle.py`` + ``app/service/task_runtime.py``.

``test_process_lifecycle.py`` is a real-process suite -- it spawns an owner,
kills it and asserts the descendants die. On any runner where that is skipped,
and even where it passes, the module's own bodies barely execute, leaving
``process_lifecycle.py`` at 18.3% (49 missed statements). These tests drive the
same logic hermetically through mocks, so the Win32 Job-Object wiring and the
reap-on-parent-exit path are asserted everywhere, not just on Windows.

``task_runtime.run_in_executor_owned`` had no test at all.
"""
from __future__ import annotations

import asyncio
import sys
import types
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.service import task_runtime
from app.utils import process_lifecycle


pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


# ---------------------------------------------------------------------------
# app/utils/process_lifecycle.py
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_job_handle():
    """``bind_desktop_process_tree`` memoizes the Job handle in a module global."""
    process_lifecycle._desktop_job = None
    yield
    process_lifecycle._desktop_job = None


def _fake_kernel(handle=99, create=True, set_information=True, assign=True):
    """Stand-in for ``ctypes.WinDLL('kernel32')``.

    The real kernel functions get ``argtypes``/``restype`` attributes assigned
    before use, so a MagicMock is required rather than a plain stub.
    """
    kernel = MagicMock()
    kernel.CreateJobObjectW.return_value = handle if create else None
    kernel.SetInformationJobObject.return_value = set_information
    kernel.AssignProcessToJobObject.return_value = assign
    kernel.GetCurrentProcess.return_value = 1234
    kernel.CloseHandle.return_value = True
    return kernel


class TestBindDesktopProcessTree:
    def test_noop_off_windows(self, monkeypatch):
        """The Job Object is a Win32 concept; other platforms must not load ctypes."""
        monkeypatch.setattr(process_lifecycle.sys, "platform", "linux")
        with patch("ctypes.WinDLL") as win_dll:
            process_lifecycle.bind_desktop_process_tree()
        win_dll.assert_not_called()
        assert process_lifecycle._desktop_job is None

    def test_second_call_is_idempotent(self, monkeypatch):
        """The handle is owned by exactly one process, so a repeat call is a no-op."""
        monkeypatch.setattr(process_lifecycle.sys, "platform", "win32")
        process_lifecycle._desktop_job = 4242
        with patch("ctypes.WinDLL") as win_dll:
            process_lifecycle.bind_desktop_process_tree()
        win_dll.assert_not_called()
        assert process_lifecycle._desktop_job == 4242

    def test_binds_and_keeps_handle_open(self, monkeypatch):
        monkeypatch.setattr(process_lifecycle.sys, "platform", "win32")
        kernel = _fake_kernel()
        with patch("ctypes.WinDLL", return_value=kernel), patch(
            "ctypes.byref", side_effect=lambda value: value
        ), patch("ctypes.sizeof", return_value=64), patch(
            "ctypes.WinError", side_effect=OSError("win32 error")
        ) as win_error:
            process_lifecycle.bind_desktop_process_tree()

        kernel.CreateJobObjectW.assert_called_once_with(None, None)
        # 9 == JobObjectExtendedLimitInformation
        assert kernel.SetInformationJobObject.call_args[0][1] == 9
        kernel.AssignProcessToJobObject.assert_called_once_with(99, 1234)
        assert process_lifecycle._desktop_job == 99
        # The handle intentionally survives for the life of the process; closing
        # it would kill the very children it is meant to protect.
        kernel.CloseHandle.assert_not_called()
        win_error.assert_not_called()

    def test_missing_job_handle_raises(self, monkeypatch):
        monkeypatch.setattr(process_lifecycle.sys, "platform", "win32")
        kernel = _fake_kernel(create=False)
        with patch("ctypes.WinDLL", return_value=kernel), patch(
            "ctypes.WinError", side_effect=OSError("CreateJobObjectW failed")
        ) as win_error, patch("ctypes.get_last_error", return_value=5):
            with pytest.raises(OSError, match="CreateJobObjectW failed"):
                process_lifecycle.bind_desktop_process_tree()
        win_error.assert_called_once_with(5)
        assert process_lifecycle._desktop_job is None

    @pytest.mark.parametrize(
        "failing, expected",
        [
            ("set_information", "SetInformationJobObject"),
            ("assign", "AssignProcessToJobObject"),
        ],
    )
    def test_setup_failure_closes_handle_and_reraises(self, monkeypatch, failing, expected):
        """A half-built Job must not leak its handle -- Windows would then keep
        the workers alive after the owner is gone."""
        monkeypatch.setattr(process_lifecycle.sys, "platform", "win32")
        kernel = _fake_kernel(**{failing: False})
        with patch("ctypes.WinDLL", return_value=kernel), patch(
            "ctypes.byref", side_effect=lambda value: value
        ), patch("ctypes.sizeof", return_value=64), patch(
            "ctypes.WinError", side_effect=OSError(expected + " failed")
        ) as win_error, patch("ctypes.get_last_error", return_value=1):
            with pytest.raises(OSError, match=expected + " failed"):
                process_lifecycle.bind_desktop_process_tree()
        kernel.CloseHandle.assert_called_once_with(99)
        win_error.assert_called_once_with(1)
        assert process_lifecycle._desktop_job is None


def _psutil_stub(children, no_such_process=None):
    """Build a minimal importable ``psutil`` module for ``sys.modules``."""
    module = types.ModuleType("psutil")
    module.NoSuchProcess = no_such_process or type("NoSuchProcess", (Exception,), {})
    module.Process = MagicMock(
        return_value=SimpleNamespace(children=lambda recursive: children)
    )
    module.wait_procs = MagicMock()
    return module


class TestWatchWorkerParent:
    def test_no_parent_means_no_thread(self):
        with patch.object(
            process_lifecycle.multiprocessing, "parent_process", return_value=None
        ), patch.object(process_lifecycle.threading, "Thread") as thread:
            process_lifecycle.watch_worker_parent()
        thread.assert_not_called()

    def test_starts_named_daemon_watch_thread(self):
        parent = MagicMock()
        with patch.object(
            process_lifecycle.multiprocessing, "parent_process", return_value=parent
        ), patch.object(process_lifecycle.threading, "Thread") as thread:
            process_lifecycle.watch_worker_parent()
        thread.assert_called_once_with(
            target=process_lifecycle._exit_with_parent,
            args=(parent,),
            name="WorkerParentWatch",
            daemon=True,
        )
        thread.return_value.start.assert_called_once()


class TestExitWithParent:
    def test_reaps_children_in_reverse_order_then_exits(self):
        """``reversed(children)`` kills the deepest descendant first."""
        killed = []
        first, second = MagicMock(), MagicMock()
        first.kill.side_effect = lambda: killed.append("first")
        second.kill.side_effect = lambda: killed.append("second")
        stub = _psutil_stub([first, second])

        with patch.dict(sys.modules, {"psutil": stub}), patch.object(
            process_lifecycle.os, "_exit"
        ) as exit_:
            process_lifecycle._exit_with_parent(MagicMock())

        assert killed == ["second", "first"]
        stub.wait_procs.assert_called_once_with([first, second], timeout=2)
        exit_.assert_called_once_with(1)

    def test_vanished_child_does_not_abort_the_reap(self):
        """psutil raises NoSuchProcess when a child dies between listing and kill."""
        class NoSuchProcess(Exception):
            pass

        gone, alive = MagicMock(), MagicMock()
        gone.kill.side_effect = NoSuchProcess("gone")
        stub = _psutil_stub([gone, alive], no_such_process=NoSuchProcess)

        with patch.dict(sys.modules, {"psutil": stub}), patch.object(
            process_lifecycle.os, "_exit"
        ) as exit_:
            process_lifecycle._exit_with_parent(MagicMock())

        alive.kill.assert_called_once()
        exit_.assert_called_once_with(1)

    def test_reap_failure_still_terminates_the_worker(self):
        """A broken psutil must never leave the orphaned worker running."""
        stub = _psutil_stub([])
        stub.Process.side_effect = RuntimeError("psutil exploded")

        with patch.dict(sys.modules, {"psutil": stub}), patch.object(
            process_lifecycle.os, "_exit"
        ) as exit_:
            process_lifecycle._exit_with_parent(MagicMock())

        exit_.assert_called_once_with(1)

    def test_waits_for_the_parent_handle_before_reaping(self):
        """The parent handle survives PID reuse, so joining it is authoritative."""
        parent = MagicMock()
        stub = _psutil_stub([])
        parent.join.side_effect = lambda: stub.wait_procs.assert_not_called()

        with patch.dict(sys.modules, {"psutil": stub}), patch.object(
            process_lifecycle.os, "_exit"
        ):
            process_lifecycle._exit_with_parent(parent)

        parent.join.assert_called_once()


# ---------------------------------------------------------------------------
# app/service/task_runtime.py
# ---------------------------------------------------------------------------


class TestRunInExecutorOwned:
    def test_returns_executor_result(self):
        async def main():
            def work(value):
                return value * 2

            return await task_runtime.run_in_executor_owned(None, work, 21)

        assert asyncio.run(main()) == 42

    def test_propagates_executor_exception(self):
        async def main():
            def boom():
                raise ValueError("worker failed")

            return await task_runtime.run_in_executor_owned(None, boom)

        with pytest.raises(ValueError, match="worker failed"):
            asyncio.run(main())

    def test_cancel_waits_for_inflight_work_then_propagates(self):
        """Cancelling must not abandon a running executor job: the helper keeps
        shielding until the underlying future actually finishes."""

        async def main():
            finished = []

            def slow():
                for _ in range(200):
                    pass
                finished.append(True)
                return "done"

            task = asyncio.ensure_future(
                task_runtime.run_in_executor_owned(None, slow)
            )
            await asyncio.sleep(0)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            return finished

        assert asyncio.run(main()) == [True]

    def test_await_owned_passes_through_plain_results(self):
        async def main():
            future = asyncio.get_running_loop().create_future()
            future.set_result("ok")
            return await task_runtime.await_owned(future)

        assert asyncio.run(main()) == "ok"

    def test_await_owned_surfaces_inner_failure(self):
        """After draining, the underlying exception is retrieved so asyncio does
        not log it as never-consumed, then the error still reaches the caller."""

        async def main():
            future = asyncio.get_running_loop().create_future()
            future.set_exception(KeyError("inner"))
            return await task_runtime.await_owned(future)

        with pytest.raises(KeyError):
            asyncio.run(main())

    def test_repeated_cancellation_keeps_draining(self):
        """Cancelling again while the job drains must re-enter the shield rather
        than abandon the executor thread -- that is the whole point of the
        ``while not future.done()`` loop."""

        async def main():
            loop = asyncio.get_running_loop()
            inner = loop.create_future()
            owned = asyncio.ensure_future(task_runtime.await_owned(inner))
            # Let the helper reach `await asyncio.shield(inner)` first;
            # cancelling before it starts would skip the body entirely.
            await asyncio.sleep(0)

            owned.cancel()
            await asyncio.sleep(0)
            # Still draining: the inner future has not resolved.
            assert not owned.done()
            assert not inner.done()

            # A second cancellation must be absorbed by the loop, not escape.
            owned.cancel()
            await asyncio.sleep(0)
            assert not owned.done()

            inner.set_result("finished")
            with pytest.raises(asyncio.CancelledError):
                await owned
            # The inner job ran to completion and was never itself cancelled.
            assert inner.result() == "finished"

        asyncio.run(main())

    def test_inner_failure_during_drain_still_propagates_cancellation(self):
        """If the shielded job fails while we are draining, the loop breaks and
        the cancellation -- not the job's error -- is what the caller sees."""

        async def main():
            loop = asyncio.get_running_loop()
            inner = loop.create_future()
            owned = asyncio.ensure_future(task_runtime.await_owned(inner))
            await asyncio.sleep(0)
            owned.cancel()
            await asyncio.sleep(0)
            assert not owned.done()

            inner.set_exception(RuntimeError("job blew up"))
            with pytest.raises(asyncio.CancelledError):
                await owned

        asyncio.run(main())
