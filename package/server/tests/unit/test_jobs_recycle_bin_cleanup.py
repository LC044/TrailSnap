"""Unit tests for app.service.jobs.recycle_bin_cleanup.

recycle_bin_cleanup_job permanently deletes photos whose deleted_at is older
than the configured retention window. We mock DB + system_config + crud
batch_delete so the job path is exercised without a real database.
"""

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.smoke, pytest.mark.module_jobs]


def _fake_photo(pid, owner_id, deleted_days_ago):
    return SimpleNamespace(
        id=pid,
        owner_id=owner_id,
        deleted_at=datetime.now() - timedelta(days=deleted_days_ago),
    )


def test_recycle_bin_cleanup_job_no_op_when_no_expired_photos():
    """If no expired photos exist, batch_delete must not be called."""
    from app.service.jobs import recycle_bin_cleanup

    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = []

    fake_config = MagicMock()
    fake_config.config.recycle_bin.retention_days = 30

    with patch.object(recycle_bin_cleanup, "SessionLocal", MagicMock(return_value=db)), \
         patch.object(recycle_bin_cleanup, "system_config", fake_config), \
         patch("app.crud.photo.batch_delete_photos_db") as fake_delete:
        recycle_bin_cleanup.recycle_bin_cleanup_job()

    fake_delete.assert_not_called()
    db.close.assert_called_once()


def test_recycle_bin_cleanup_job_groups_expired_photos_by_owner():
    """Expired photos from 2 owners must trigger 2 batch_delete calls, grouped by owner."""
    from app.service.jobs import recycle_bin_cleanup

    owner_a = "11111111-1111-1111-1111-111111111111"
    owner_b = "22222222-2222-2222-2222-222222222222"

    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [
        _fake_photo("p1", owner_a, 60),
        _fake_photo("p2", owner_a, 45),
        _fake_photo("p3", owner_b, 90),
    ]

    fake_config = MagicMock()
    fake_config.config.recycle_bin.retention_days = 30

    with patch.object(recycle_bin_cleanup, "SessionLocal", MagicMock(return_value=db)), \
         patch.object(recycle_bin_cleanup, "system_config", fake_config), \
         patch("app.crud.photo.batch_delete_photos_db") as fake_delete:
        recycle_bin_cleanup.recycle_bin_cleanup_job()

    assert fake_delete.call_count == 2
    owner_calls = {call_args.kwargs["user_id"]: call_args.args[1] for call_args in fake_delete.call_args_list}
    assert owner_calls[owner_a] == ["p1", "p2"]
    assert owner_calls[owner_b] == ["p3"]
    db.close.assert_called_once()


def test_recycle_bin_cleanup_job_logs_and_swallows_exception():
    """If batch_delete raises, the job must log and exit cleanly."""
    from app.service.jobs import recycle_bin_cleanup

    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [
        _fake_photo("p1", "owner", 60),
    ]

    fake_config = MagicMock()
    fake_config.config.recycle_bin.retention_days = 30

    with patch.object(recycle_bin_cleanup, "SessionLocal", MagicMock(return_value=db)), \
         patch.object(recycle_bin_cleanup, "system_config", fake_config), \
         patch("app.crud.photo.batch_delete_photos_db",
                      MagicMock(side_effect=RuntimeError("db boom"))):
        # Should NOT re-raise.
        recycle_bin_cleanup.recycle_bin_cleanup_job()
    db.close.assert_called_once()