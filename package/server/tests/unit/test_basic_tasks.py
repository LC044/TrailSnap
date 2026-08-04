"""Nightly watch gap coverage for app.service.tasks.basic.

Targets the batch wrapper and resource release hooks in basic.py
(178/212 lines missed in nightly coverage scan).

* Happy path: batch returns one result per input task with task_id echoed.
* Edge: empty input returns empty list.
* Error: a single failure inside the per-task processor is captured in the
  returned result dict instead of raising.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.service.tasks import basic as basic_task


pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


def test_process_basic_cpu_batch_job_empty_input():
    assert basic_task.process_basic_cpu_batch_job([]) == []


def test_process_basic_cpu_batch_job_returns_per_task_results():
    fake_results = [
        {"success": True, "thumb_path": "a.jpg"},
        {"success": True, "thumb_path": "b.jpg"},
    ]
    with patch("app.service.tasks.basic.process_basic_cpu_job", side_effect=fake_results):
        tasks = [
            {"task_id": "t1", "file_path": "a", "file_id": "f1", "storage_root": "/r", "user_id": "u1"},
            {"task_id": "t2", "file_path": "b", "file_id": "f2", "storage_root": "/r", "user_id": "u2"},
        ]
        results = basic_task.process_basic_cpu_batch_job(tasks)
    assert len(results) == 2
    assert results[0]["task_id"] == "t1"
    assert results[0]["success"] is True
    assert results[1]["task_id"] == "t2"


def test_process_basic_cpu_batch_job_keeps_going_after_failure():
    fake_results = [
        {"success": False, "error": "boom"},
        {"success": True, "thumb_path": "ok.jpg"},
    ]
    with patch("app.service.tasks.basic.process_basic_cpu_job", side_effect=fake_results):
        tasks = [
            {"task_id": "t1", "file_path": "a", "file_id": "f1", "storage_root": "/r", "user_id": "u1"},
            {"task_id": "t2", "file_path": "b", "file_id": "f2", "storage_root": "/r", "user_id": "u2"},
        ]
        results = basic_task.process_basic_cpu_batch_job(tasks)
    # Both results should be returned; batch keeps iterating.
    assert len(results) == 2
    assert results[0]["error"] == "boom"
    assert results[1]["success"] is True


def test_release_resources_is_noop():
    # The hook currently is a no-op (placeholder for future cleanup).
    assert basic_task.release_resources() is None


def test_basic_task_strategy_task_category():
    # Registered at import time; just verify the marker is set.
    strategy = basic_task.BasicTaskStrategy()
    assert strategy.task_category == "CPU"
