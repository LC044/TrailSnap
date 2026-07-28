"""Unit tests for app.service.jobs.scan_folder.

scan_folder_job runs from the JobScheduler cron: if no SCAN_FOLDER task is
already pending/processing, it enqueues a new one via TaskManager. We mock
the DB session + TaskManager so the job path is exercised without Postgres.
"""

from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.smoke, pytest.mark.module_jobs]


def test_scan_folder_job_skips_when_pending_task_exists():
    """If a SCAN_FOLDER task is already pending, no new task should be enqueued."""
    from app.service.jobs import scan_folder

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = MagicMock()  # existing task

    fake_task_manager = MagicMock()
    with patch.object(scan_folder, "SessionLocal", MagicMock(return_value=db)), \
         patch.object(scan_folder, "TaskManager") as fake_tm_cls:
        fake_tm_cls.get_instance.return_value = fake_task_manager
        scan_folder.scan_folder_job()

    fake_task_manager.add_task.assert_not_called()
    db.close.assert_called_once()


def test_scan_folder_job_enqueues_when_no_pending_task():
    """If no SCAN_FOLDER is pending, a new one must be added."""
    from app.service.jobs import scan_folder
    from app.db.models.task import TaskType

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None

    fake_task_manager = MagicMock()
    with patch.object(scan_folder, "SessionLocal", MagicMock(return_value=db)), \
         patch.object(scan_folder, "TaskManager") as fake_tm_cls:
        fake_tm_cls.get_instance.return_value = fake_task_manager
        scan_folder.scan_folder_job()

    fake_task_manager.add_task.assert_called_once()
    args, kwargs = fake_task_manager.add_task.call_args
    # add_task signature: add_task(db, task_type, payload)
    assert kwargs.get("task_type") == TaskType.SCAN_FOLDER or args[1] == TaskType.SCAN_FOLDER
    db.close.assert_called_once()


def test_scan_folder_job_logs_and_swallows_exception():
    """If the DB query blows up, the job must log and exit cleanly (no re-raise)."""
    from app.service.jobs import scan_folder

    db = MagicMock()
    db.query.side_effect = RuntimeError("db down")

    with patch.object(scan_folder, "SessionLocal", MagicMock(return_value=db)):
        # Should not raise — failures are swallowed and logged.
        scan_folder.scan_folder_job()
    db.close.assert_called_once()