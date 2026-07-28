"""Unit tests for app/service/scheduler.py (JobScheduler).

JobScheduler is a thin wrapper over APScheduler. We don't let it actually
fire jobs in tests — instead we assert that the right trigger type is
registered with the right name, that disabled / invalid schedules are
skipped, and that start/stop transitions are safe.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.service.scheduler import JobScheduler


pytestmark = [pytest.mark.smoke, pytest.mark.module_scheduler]


@pytest.fixture
def fresh_scheduler():
    """Build a JobScheduler but do NOT start it."""
    return JobScheduler()


def test_register_cron_job_with_empty_expr_is_skipped(fresh_scheduler):
    fn = MagicMock()
    assert fresh_scheduler.register_cron_job("noop", None, fn) is False
    assert fresh_scheduler.register_cron_job("noop", "", fn) is False
    # No jobs were added to the underlying scheduler.
    assert fresh_scheduler._scheduler.get_jobs() == []


def test_register_cron_job_with_invalid_expr_returns_false(fresh_scheduler):
    fn = MagicMock()
    # "not-a-cron" has the wrong number of fields and should fail.
    assert fresh_scheduler.register_cron_job("bad", "not-a-cron", fn) is False


def test_register_cron_job_with_valid_expr_returns_true(fresh_scheduler):
    fn = MagicMock()
    assert fresh_scheduler.register_cron_job("every-5m", "*/5 * * * *", fn) is True
    jobs = fresh_scheduler._scheduler.get_jobs()
    assert len(jobs) == 1
    assert jobs[0].id == "every-5m"


def test_register_cron_job_with_same_id_uses_replace_existing(fresh_scheduler):
    """Two registrations with the same id must not crash; replace_existing is on.

    We only assert the call returns True both times — APScheduler''s
    internal ``replace_existing`` behaviour depends on whether the
    scheduler is started yet, which is an implementation detail we
    don''t want to pin.
    """
    fn_a = MagicMock()
    fn_b = MagicMock()
    assert fresh_scheduler.register_cron_job("once", "0 * * * *", fn_a) is True
    assert fresh_scheduler.register_cron_job("once", "*/10 * * * *", fn_b) is True


def test_register_interval_job_returns_true(fresh_scheduler):
    fn = MagicMock()
    assert fresh_scheduler.register_interval_job("scan", seconds=60, fn=fn) is True
    jobs = fresh_scheduler._scheduler.get_jobs()
    assert len(jobs) == 1
    assert jobs[0].id == "scan"


def test_register_interval_job_with_next_run_time_passes_kwarg(fresh_scheduler):
    from datetime import datetime, timezone

    fn = MagicMock()
    nrt = datetime(2030, 1, 1, tzinfo=timezone.utc)
    assert fresh_scheduler.register_interval_job("scan", seconds=300, fn=fn, next_run_time=nrt) is True
    jobs = fresh_scheduler._scheduler.get_jobs()
    assert jobs[0].next_run_time == nrt


def test_start_is_idempotent(fresh_scheduler):
    with patch.object(fresh_scheduler._scheduler, "start") as start_call:
        fresh_scheduler.start()
        fresh_scheduler.start()  # second call is a no-op
    start_call.assert_called_once()
    assert fresh_scheduler._started is True


def test_stop_when_never_started_is_noop(fresh_scheduler):
    # Should not raise.
    fresh_scheduler.stop()
    assert fresh_scheduler._started is False


def test_stop_after_start_shuts_down_scheduler(fresh_scheduler):
    with patch.object(fresh_scheduler._scheduler, "start"):
        fresh_scheduler.start()
    with patch.object(fresh_scheduler._scheduler, "shutdown") as shutdown_call:
        fresh_scheduler.stop()
    shutdown_call.assert_called_once_with(wait=False)
    assert fresh_scheduler._started is False


def test_stop_swallows_shutdown_exception(fresh_scheduler):
    with patch.object(fresh_scheduler._scheduler, "start"):
        fresh_scheduler.start()
    with patch.object(fresh_scheduler._scheduler, "shutdown", side_effect=RuntimeError("boom")):
        # Must not raise.
        fresh_scheduler.stop()
    assert fresh_scheduler._started is False
