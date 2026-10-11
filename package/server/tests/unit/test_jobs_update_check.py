"""Unit tests for app/service/jobs/update_check.py.

``update_check_job`` is a thin shim around
``UpdateCheckScheduler().tick()``. We mock the scheduler and assert that
exceptions are swallowed (the cron loop must never re-raise).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = [pytest.mark.smoke, pytest.mark.module_jobs]


@pytest.fixture(autouse=True)
def no_update_downloads(monkeypatch):
    # The scheduled job also warms the APK cache. Unit tests must not download it.
    monkeypatch.setattr('app.service.app_update.prefetch_latest_app_update', AsyncMock())


def test_update_check_job_invokes_scheduler_tick():
    from app.service.jobs import update_check

    with patch.object(update_check, "UpdateCheckScheduler") as fake_cls:
        update_check.update_check_job()

    fake_cls.assert_called_once_with()
    fake_cls.return_value.tick.assert_called_once_with()


def test_update_check_job_swallows_scheduler_exception():
    """If ``tick()`` raises, the cron must not propagate the failure."""
    from app.service.jobs import update_check

    with patch.object(update_check, "UpdateCheckScheduler",
                      MagicMock(side_effect=RuntimeError("net down"))):
        # Should NOT re-raise.
        update_check.update_check_job()
