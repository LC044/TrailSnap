"""2026-09-16 nightly tests for app/service/task_worker.py priority gaps.

Targets three helpers in task_worker.py that are still untested by the
existing test_task_worker.py, test_nightly_task_worker_gaps_20260815.py
and test_nightly_task_worker_resource_limits_gaps_20260830.py suites:

* TaskWorker._save_system_state -- JSON encoding for set/list/dict values,
  string fallback for scalars, raising branch swallowed and logged.
* TaskWorker._load_system_state -- JSON decode, raw value fallback when the
  payload is not JSON, and outer exception returning the default.
* TaskWorker._recover_unfinished_tasks -- no-op when no tasks exist;
  PROCESSING -> PENDING reset including the payload.force=True strip and
  finished-counts persisted via scan_status.
"""

import logging
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


def _bare_worker():
    from app.service import task_worker
    return task_worker.TaskWorker.__new__(task_worker.TaskWorker)


# ---------------------------------------------------------------------------
# _save_system_state
# ---------------------------------------------------------------------------


def test_save_system_state_serializes_collections_and_stringifies_scalars():
    worker = _bare_worker()
    real_db = MagicMock()

    with patch("app.service.task_worker.SessionLocal", return_value=real_db):
        # 1) dict -> JSON
        real_db.reset_mock()
        row = MagicMock()
        row.value = "old"
        real_db.query.return_value.filter.return_value.first.return_value = row
        from app.service.task_worker import TaskWorker
        TaskWorker._save_system_state(worker, "adaptive_resource_limits", {"face": 2, "ocr": 1})
        assert row.value.startswith("{")
        assert '"face"' in row.value

    with patch("app.service.task_worker.SessionLocal", return_value=real_db):
        # 2) scalar -> str(value)
        real_db.reset_mock()
        row = MagicMock()
        row.value = "old"
        real_db.query.return_value.filter.return_value.first.return_value = row
        TaskWorker._save_system_state(worker, "fast_mode", True)
        assert row.value == "True"

    with patch("app.service.task_worker.SessionLocal", return_value=real_db):
        # 3) list with datetime -> JSON with default=str
        real_db.reset_mock()
        row = MagicMock()
        row.value = "old"
        real_db.query.return_value.filter.return_value.first.return_value = row
        TaskWorker._save_system_state(
            worker, "recent_runs", [{"at": datetime(2026, 9, 16)}]
        )
        assert row.value.startswith("[")
        assert "2026" in row.value


def test_save_system_state_adds_new_row_when_state_missing():
    worker = _bare_worker()
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    added = {}
    db.add.side_effect = lambda s: added.setdefault("state", s)

    with patch("app.service.task_worker.SessionLocal", return_value=db):
        from app.service.task_worker import TaskWorker
        TaskWorker._save_system_state(worker, "new_key", {"a": 1})

    assert added["state"].key == "new_key"
    assert added["state"].value.startswith("{")
    db.commit.assert_called_once()


def test_save_system_state_swallows_db_exceptions(caplog):
    worker = _bare_worker()
    bad_db = MagicMock()
    bad_db.query.return_value.filter.return_value.first.side_effect = RuntimeError("db down")

    with caplog.at_level(logging.ERROR):
        with patch("app.service.task_worker.SessionLocal", return_value=bad_db):
            from app.service.task_worker import TaskWorker
            # 不应抛出
            TaskWorker._save_system_state(worker, "k", {"a": 1})

    assert any("Failed to save system state" in r.message for r in caplog.records)
    bad_db.close.assert_called_once()


# ---------------------------------------------------------------------------
# _load_system_state
# ---------------------------------------------------------------------------


def test_load_system_state_decodes_json_then_falls_back_to_raw_string():
    worker = _bare_worker()
    db = MagicMock()
    row = MagicMock()
    row.value = '{"face": 3, "ocr": 1}'
    db.query.return_value.filter.return_value.first.return_value = row

    with patch("app.service.task_worker.SessionLocal", return_value=db):
        from app.service.task_worker import TaskWorker
        assert TaskWorker._load_system_state(worker, "limits") == {"face": 3, "ocr": 1}

    # raw non-JSON string should be returned as-is
    row.value = "not-json"
    with patch("app.service.task_worker.SessionLocal", return_value=db):
        assert TaskWorker._load_system_state(worker, "limits") == "not-json"
    db.close.assert_called()


def test_load_system_state_returns_default_when_missing_or_db_broken():
    worker = _bare_worker()
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    with patch("app.service.task_worker.SessionLocal", return_value=db):
        from app.service.task_worker import TaskWorker
        assert TaskWorker._load_system_state(worker, "missing", default={"x": 1}) == {"x": 1}
        assert TaskWorker._load_system_state(worker, "missing") is None

    # db exception -> default
    broken_db = MagicMock()
    broken_db.query.return_value.filter.return_value.first.side_effect = RuntimeError("db down")
    with patch("app.service.task_worker.SessionLocal", return_value=broken_db):
        from app.service.task_worker import TaskWorker
        assert TaskWorker._load_system_state(worker, "k", default=42) == 42
        broken_db.close.assert_called_once()


# ---------------------------------------------------------------------------
# _recover_unfinished_tasks
# ---------------------------------------------------------------------------


def test_recover_unfinished_tasks_no_op_when_no_pending_or_processing():
    worker = _bare_worker()
    worker.scan_status = {"total_files": 0, "running": False}
    worker.paused_categories = set()

    db = MagicMock()
    with (
        patch("app.service.task_worker.SessionLocal", return_value=db),
        patch("app.service.task_worker.crud_task") as crud,
    ):
        crud.count_tasks_by_status.return_value = 0
        from app.service.task_worker import TaskWorker
        TaskWorker._recover_unfinished_tasks(worker)
        crud.get_tasks_by_status.assert_not_called()
        # scan_status 不会被覆盖为 running
        assert worker.scan_status["running"] is False
        assert worker.paused_categories == set()


def test_recover_unfinished_tasks_resets_processing_strips_force_flag():
    worker = _bare_worker()
    worker.scan_status = {"total_files": 0, "running": False, "message": ""}
    worker.paused_categories = set()

    db = MagicMock()
    from app.service.task_worker import TaskWorker

    processing_task_with_force = SimpleNamespace(
        id="t-force",
        payload={"force": True, "scan_roots": ["/photos"]},
        status="PROCESSING",
    )
    processing_task_plain = SimpleNamespace(
        id="t-plain",
        payload={},
        status="PROCESSING",
    )

    def _save_state(key, value):
        if key == "scan_status":
            worker.scan_status.update(value)

    with (
        patch("app.service.task_worker.SessionLocal", return_value=db),
        patch("app.service.task_worker.crud_task") as crud,
        patch.object(worker, "_save_system_state", _save_state),
        patch.object(worker, "_load_system_state", return_value=["OCR"]),
    ):
        # pending=1, processing=2 -> total 3
        crud.count_tasks_by_status.side_effect = [1, 2]
        crud.get_tasks_by_status.return_value = [
            processing_task_with_force,
            processing_task_plain,
        ]
        TaskWorker._recover_unfinished_tasks(worker)

    # force=True 必须被改写为 False，避免下一次扫描无限重复
    assert processing_task_with_force.payload["force"] is False
    # 两个 PROCESSING 都重置为 PENDING
    assert str(processing_task_with_force.status).endswith("PENDING")
    assert str(processing_task_plain.status).endswith("PENDING")
    db.commit.assert_called_once()
    # scan_status 应该带 running=True + message 含 "Recovered 3"
    assert worker.scan_status["running"] is True
    assert "3" in worker.scan_status["message"]
    assert worker.scan_status["total_files"] >= 3
    assert worker.paused_categories == {"OCR"}


def test_recover_unfinished_tasks_rolls_back_on_db_failure():
    worker = _bare_worker()
    worker.scan_status = {"total_files": 0, "running": False, "message": ""}
    worker.paused_categories = set()

    db = MagicMock()

    from app.service.task_worker import TaskWorker

    with (
        patch("app.service.task_worker.SessionLocal", return_value=db),
        patch("app.service.task_worker.crud_task") as crud,
    ):
        crud.count_tasks_by_status.side_effect = [0, 1]
        crud.get_tasks_by_status.side_effect = RuntimeError("boom")
        # 不应抛出
        TaskWorker._recover_unfinished_tasks(worker)

    db.rollback.assert_called_once()
    db.close.assert_called_once()
