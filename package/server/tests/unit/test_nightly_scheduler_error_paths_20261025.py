"""Nightly coverage for ``app.service.scheduler`` failure branches.

The 2026-10-24 backend coverage report ranked ``service/scheduler.py`` at
83.9% with 10 statements never executed.  Every uncovered line sat in an
``except`` block: APScheduler refusing a job registration and the shutdown
path blowing up.  Those branches decide whether a misconfigured scan /
recycle-bin schedule is silently skipped (job never runs) or whether the
whole service refuses to start.

The wrapper is deliberately defensive -- it logs and returns ``False`` instead
of propagating -- so the assertions below pin the *contract*: a failed
registration must never raise, and a failed shutdown must not hide the
process-exit path (``wait=True`` re-raises so the caller can decide).
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.service.scheduler import JobScheduler


pytestmark = [pytest.mark.smoke]


@pytest.fixture
def scheduler():
    """A JobScheduler that was never started (no APScheduler threads)."""
    return JobScheduler()


def test_register_cron_job_returns_false_when_scheduler_rejects_job(scheduler):
    """A scheduler-side rejection is swallowed and reported as False."""
    fn = MagicMock()

    with patch.object(scheduler._scheduler, "add_job", side_effect=RuntimeError("boom")):
        assert scheduler.register_cron_job("scan", "*/5 * * * *", fn) is False


def test_register_interval_job_returns_false_when_scheduler_rejects_job(scheduler):
    """Interval registration has the same swallow-and-report contract."""
    fn = MagicMock()

    with patch.object(scheduler._scheduler, "add_job", side_effect=RuntimeError("boom")):
        assert scheduler.register_interval_job("recycle", 3600, fn) is False


def test_register_interval_job_with_next_run_time_returns_false_on_failure(scheduler):
    """The ``next_run_time`` variant must fail the same way as the plain one."""
    fn = MagicMock()

    with patch.object(scheduler._scheduler, "add_job", side_effect=RuntimeError("boom")):
        assert (
            scheduler.register_interval_job(
                "recycle", 3600, fn, next_run_time=datetime.now() + timedelta(minutes=1)
            )
            is False
        )


def test_register_once_job_returns_false_when_scheduler_rejects_job(scheduler):
    """One-shot jobs (e.g. the startup upgrade task) must not raise."""
    fn = MagicMock()

    with patch.object(scheduler._scheduler, "add_job", side_effect=RuntimeError("boom")):
        assert scheduler.register_once_job("upgrade", datetime.now() + timedelta(hours=1), fn) is False


def test_stop_without_start_is_a_noop(scheduler):
    """Stopping an unstarted scheduler must not touch APScheduler."""
    with patch.object(scheduler._scheduler, "shutdown") as shutdown:
        scheduler.stop()
    shutdown.assert_not_called()


def test_stop_swallows_shutdown_error_when_wait_is_false(scheduler):
    """A shutdown failure is logged, not raised, for the lenient path."""
    scheduler._started = True

    with patch.object(scheduler._scheduler, "shutdown", side_effect=RuntimeError("boom")):
        scheduler.stop(wait=False)

    assert scheduler._started is False


def test_stop_reraises_shutdown_error_when_wait_is_true(scheduler):
    """The strict path re-raises so a caller can abort the shutdown sequence."""
    scheduler._started = True

    with patch.object(scheduler._scheduler, "shutdown", side_effect=RuntimeError("boom")):
        with pytest.raises(RuntimeError):
            scheduler.stop(wait=True)


def test_start_is_idempotent(scheduler):
    """Calling ``start`` twice must not start APScheduler twice."""
    with patch.object(scheduler._scheduler, "start") as start:
        scheduler.start()
        scheduler.start()

    start.assert_called_once_with()
    assert scheduler._started is True

