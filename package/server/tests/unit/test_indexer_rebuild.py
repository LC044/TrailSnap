"""Unit tests for ``app/service/indexer.py`` (rebuild_index).

Why this file exists:

* The nightly gap scan flagged ``service/indexer.py`` as uncovered.
  It owns the module-level ``status`` dict that powers the
  ``GET /api/index/status`` endpoint and the ``rebuild_index`` call
  that fronts every user-initiated "Rescan now" action.

* ``rebuild_index`` is a thin façade: it guards on ``status['running']``
  and delegates the heavy lifting to ``TaskManager.add_task`` with a
  ``SCAN_FOLDER`` job.  The behaviour we want to pin is:

    - When the flag is ``False``, a ``SCAN_FOLDER`` task is submitted
      with the correct payload (including optional ``user_id``) and the
      flag flips to ``True`` together with the ``running`` message.
    - When the flag is already ``True``, ``rebuild_index`` is a no-op
      (no second task submission, no payload mutation).

* The status dict is module-global, so every test resets it to the
  documented idle defaults in setup/teardown.  Other tests in this
  directory never touch ``status`` directly, but a paranoid snapshot
  is cheap insurance against future cross-test pollution.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.service import indexer
from app.db.models.task import TaskType


pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


@pytest.fixture(autouse=True)
def reset_indexer_status():
    """Snapshot and restore the module-level ``status`` dict.

    ``indexer.status`` is a mutable global; each test sets it to known
    values and the fixture puts it back to the canonical idle state.
    """
    saved = dict(indexer.status)
    indexer.status.update(
        {
            "running": False,
            "progress": 0.0,
            "added": 0,
            "deleted": 0,
            "errors": 0,
            "message": "Idle",
        }
    )
    yield
    indexer.status.clear()
    indexer.status.update(saved)


def _fake_task_manager():
    """Return a ``TaskManager.get_instance`` mock wired with a recorder."""
    tm = MagicMock()
    tm.add_task = MagicMock(return_value="TASK-1")
    return tm


class TestRebuildIndex:
    """``rebuild_index`` enqueues a SCAN_FOLDER task and flips the
    process-wide ``running`` flag.  We patch ``TaskManager.get_instance``
    so no real DB / worker is required.
    """

    def test_submits_scan_folder_task_with_priority_10(self):
        tm = _fake_task_manager()
        with patch.object(indexer.TaskManager, "get_instance", return_value=tm):
            indexer.rebuild_index(db=MagicMock())

        tm.add_task.assert_called_once()
        args, kwargs = tm.add_task.call_args
        # ``add_task(db, task_type, payload, priority=...)`` -- three
        # positional args + one keyword arg.  We assert the full contract.
        db_arg, type_arg, payload_arg = args
        assert db_arg is not None
        assert type_arg == TaskType.SCAN_FOLDER
        assert payload_arg == {}
        assert kwargs == {"priority": 10}

    def test_passes_user_id_through_to_payload(self):
        tm = _fake_task_manager()
        with patch.object(indexer.TaskManager, "get_instance", return_value=tm):
            indexer.rebuild_index(db=MagicMock(), user_id="user-42")

        args, _ = tm.add_task.call_args
        # 3rd positional is the payload dict.
        assert args[2] == {"user_id": "user-42"}

    def test_running_flag_flips_to_true_after_submit(self):
        tm = _fake_task_manager()
        assert indexer.status["running"] is False

        with patch.object(indexer.TaskManager, "get_instance", return_value=tm):
            indexer.rebuild_index(db=MagicMock())

        assert indexer.status["running"] is True
        assert indexer.status["progress"] == 0.0
        assert indexer.status["message"] == "Async scan task submitted"


class TestRebuildIndexGuarded:
    """When ``status['running']`` is already True the function returns
    immediately and does NOT enqueue a second task.
    """

    def test_does_not_submit_when_already_running(self):
        indexer.status["running"] = True
        tm = _fake_task_manager()

        with patch.object(indexer.TaskManager, "get_instance", return_value=tm):
            indexer.rebuild_index(db=MagicMock(), user_id="user-99")

        tm.add_task.assert_not_called()

    def test_running_flag_remains_true(self):
        # The guard does not flip ``running`` back to False -- the worker
        # is expected to do that.  We assert the no-op does not corrupt
        # the running flag, so a future refactor cannot silently turn
        # this into a toggle.
        indexer.status["running"] = True
        indexer.status["message"] = "scanning in progress"

        with patch.object(indexer.TaskManager, "get_instance", return_value=_fake_task_manager()):
            indexer.rebuild_index(db=MagicMock())

        assert indexer.status["running"] is True
        assert indexer.status["message"] == "scanning in progress"
