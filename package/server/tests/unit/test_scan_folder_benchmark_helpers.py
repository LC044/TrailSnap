"""Unit contracts for tests/performance/scan_folder_benchmark.py.

The benchmark itself needs a live server; these tests keep its parsing, timing
and report helpers honest without starting any service.
"""

from __future__ import annotations

import importlib.util
import sys
import time
from pathlib import Path

import pytest

pytestmark = [pytest.mark.smoke]

_BENCHMARK_PATH = Path(__file__).resolve().parents[4] / "tests" / "performance" / "scan_folder_benchmark.py"
_SPEC = importlib.util.spec_from_file_location("scan_folder_benchmark", _BENCHMARK_PATH)
assert _SPEC and _SPEC.loader
benchmark = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = benchmark
_SPEC.loader.exec_module(benchmark)


# ---------------------------------------------------------------------------
# SSE parsing
# ---------------------------------------------------------------------------
def test_sse_parser_handles_multiline_data_and_comments():
    parser = benchmark.SseParser()
    assert parser.feed(": keep-alive") is None
    assert parser.feed("event: task.updated") is None
    assert parser.feed('data: {"id": "a",') is None
    assert parser.feed('data: "status": "completed"}') is None
    frame = parser.feed("")
    assert frame is not None
    event, payload = frame
    assert event == "task.updated"
    assert payload == '{"id": "a",\n"status": "completed"}'

    # A new event must not inherit the previous event name or data.
    assert parser.feed("data: {}") is None
    assert parser.feed("") == ("message", "{}")


def test_sse_parser_ignores_blank_block_without_data():
    parser = benchmark.SseParser()
    parser.feed("event: ping")
    assert parser.feed("") is None
    assert parser.feed("data: x") is None
    assert parser.feed("") == ("message", "x")


# ---------------------------------------------------------------------------
# Timestamp / statistics
# ---------------------------------------------------------------------------
def test_parse_server_timestamp_supports_aware_and_naive_values(monkeypatch):
    from datetime import timedelta, timezone

    monkeypatch.setattr(benchmark, "_LOCAL_TZ", timezone(timedelta(hours=8)))
    aware = benchmark.parse_server_timestamp("2026-01-01T00:00:00+00:00")
    naive = benchmark.parse_server_timestamp("2026-01-01T08:00:00")
    assert aware is not None and naive is not None
    # naive 值来自 worker 的 datetime.now()，必须按宿主机本地时区解释。
    assert aware == naive
    assert benchmark.parse_server_timestamp("not-a-date") is None
    assert benchmark.parse_server_timestamp(None) is None


def test_summarize_seconds_reports_empty_and_interpolated_percentiles():
    assert benchmark.summarize_seconds([])["count"] == 0
    summary = benchmark.summarize_seconds([1.0, 2.0, 3.0, 4.0])
    assert summary["count"] == 4
    assert summary["min"] == 1.0
    assert summary["max"] == 4.0
    assert summary["p50"] == pytest.approx(2.5)
    assert summary["p95"] == pytest.approx(3.85)


def test_redact_database_url_hides_password():
    redacted = benchmark._redact_database_url(
        "postgresql://user:secret@localhost:5432/trailsnap_test?connect_timeout=5"
    )
    assert redacted == "postgresql://user:***@localhost:5432/trailsnap_test?connect_timeout=5"
    assert benchmark._redact_database_url(None) is None


# ---------------------------------------------------------------------------
# Task event tracker
# ---------------------------------------------------------------------------
def test_tracker_merges_created_processing_and_completed_events():
    tracker = benchmark.TaskEventTracker()
    base = benchmark.parse_server_timestamp("2026-01-01T00:00:00+00:00")
    assert base is not None

    tracker.observe_event(
        "task.created",
        {
            "id": "task-1",
            "type": "PROCESS_BASIC",
            "status": "pending",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
        },
        received_mono=1.0,
    )
    tracker.observe_event(
        "task.updated",
        {
            "id": "task-1",
            "type": "PROCESS_BASIC",
            "status": "processing",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00.250000+00:00",
            "processed_items": 0,
            "total_items": 1,
        },
        received_mono=1.5,
    )
    tracker.observe_event(
        "task.updated",
        {
            "id": "task-1",
            "type": "PROCESS_BASIC",
            "status": "completed",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:01.250000+00:00",
        },
        received_mono=2.0,
    )

    record = tracker.get("task-1")
    assert record is not None
    assert record.status == "completed"
    assert record.queue_seconds() == pytest.approx(0.25)
    # execution 用事件到达的客户端单调时钟：1.5 -> 2.0。
    assert record.execution_seconds() == pytest.approx(0.5)
    # total = queue + execution，避免下游任务缺少 created 事件时少算排队。
    assert record.total_seconds() == pytest.approx(0.75)
    assert tracker.counts(set())["completed"] == 1


def test_tracker_does_not_downgrade_processing_from_stale_poll():
    tracker = benchmark.TaskEventTracker()
    tracker.observe_event(
        "task.updated",
        {"id": "t", "type": "PROCESS_BASIC", "status": "processing"},
        received_mono=1.0,
    )
    tracker.observe_task_rows(
        [{"id": "t", "type": "PROCESS_BASIC", "status": "pending"}],
        received_mono=1.1,
    )
    record = tracker.get("t")
    assert record is not None
    assert record.status == "processing"


def test_tracker_poll_fallback_records_processing_and_ignores_paused_types():
    tracker = benchmark.TaskEventTracker()
    tracker.observe_task_rows(
        [
            {
                "id": "scan-1",
                "type": "SCAN_FOLDER",
                "status": "processing",
                "created_at": "2026-01-01T00:00:00+00:00",
                "updated_at": "2026-01-01T00:00:01+00:00",
            },
            {
                "id": "face-1",
                "type": "RECOGNIZE_FACE",
                "status": "pending",
                "created_at": "2026-01-01T00:00:00+00:00",
            },
        ],
        received_mono=time.monotonic(),
    )
    assert tracker.scan_task() is not None
    counts = tracker.counts({"RECOGNIZE_FACE"})
    assert counts["active"] == 1  # only the scan task counts; paused face is ignored


def test_tracker_total_seconds_falls_back_to_monotonic_clock():
    tracker = benchmark.TaskEventTracker()
    tracker.observe_event(
        "task.updated",
        {"id": "t", "type": "PROCESS_BASIC", "status": "completed"},
        received_mono=10.0,
    )
    record = tracker.get("t")
    assert record is not None
    assert record.total_seconds() == 0.0


def test_wait_for_pipeline_passes_when_scan_terminal_and_no_active_tasks():
    tracker = benchmark.TaskEventTracker()
    now = time.monotonic()
    tracker.observe_event(
        "task.updated",
        {"id": "scan-1", "type": "SCAN_FOLDER", "status": "completed", "updated_at": "2026-01-01T00:00:00+00:00"},
        received_mono=now,
    )
    tracker.last_change_mono = now
    scan = tracker.scan_task()
    assert scan is not None
    result = benchmark._wait_for_pipeline(
        tracker,
        scan,
        pipeline_started=now,
        total_expected=1,
        timeout=5,
        stall_seconds=5,
        settle_seconds=0.1,
    )
    assert result["stalled"] is False
    assert result["timed_out"] is False
    assert result["core_completed"] == 1
    # settle 只用于确认排空，不能计入 pipeline 耗时。
    assert result["pipeline_seconds"] < result["drain_seconds"] - 0.05


def test_wait_for_pipeline_detects_stalled_processing_task():
    tracker = benchmark.TaskEventTracker()
    now = time.monotonic()
    tracker.observe_event(
        "task.updated",
        {"id": "scan-1", "type": "SCAN_FOLDER", "status": "completed", "updated_at": "2026-01-01T00:00:00+00:00"},
        received_mono=now,
    )
    tracker.observe_event(
        "task.updated",
        {"id": "meta-1", "type": "EXTRACT_METADATA", "status": "processing", "updated_at": "2026-01-01T00:00:00+00:00"},
        received_mono=now,
    )
    tracker.last_change_mono = now - 10
    scan = tracker.scan_task()
    assert scan is not None
    result = benchmark._wait_for_pipeline(
        tracker,
        scan,
        pipeline_started=now,
        total_expected=2,
        timeout=5,
        stall_seconds=0.15,
        settle_seconds=0.01,
    )
    assert result["stalled"] is True
    assert result["timed_out"] is False
    assert result["active"] == 1
    assert result["core_completed"] == 1
    assert result["pipeline_seconds"] >= 0


def test_aggregate_tasks_marks_paused_ai_and_computes_throughput():
    record = benchmark.TaskTiming(
        task_id="t1",
        task_type="CLASSIFY_IMAGE",
        status="pending",
        first_seen_mono=1.0,
    )
    rows = benchmark._aggregate_tasks(
        [record], pipeline_seconds=2.0, paused_types={"CLASSIFY_IMAGE"}
    )
    assert rows[0]["paused"] is True
    assert rows[0]["throughput_tasks_per_second"] is None

    completed = benchmark.TaskTiming(
        task_id="t2",
        task_type="PROCESS_BASIC",
        status="completed",
        created_at=0.0,
        processing_at=0.0,
        completed_at=1.0,
        first_seen_mono=1.0,
    )
    rows = benchmark._aggregate_tasks([completed], pipeline_seconds=2.0)
    assert rows[0]["paused"] is False
    assert rows[0]["throughput_tasks_per_second"] == 0.5
    assert rows[0]["total_seconds"]["mean"] == 1.0


def test_media_extensions_match_server_scan_policy():
    from app.utils.image_loading import IMAGE_EXTENSIONS as SERVER_IMAGE
    from app.utils.image_loading import VIDEO_EXTENSIONS as SERVER_VIDEO

    assert benchmark.IMAGE_EXTENSIONS == set(SERVER_IMAGE)
    assert benchmark.VIDEO_EXTENSIONS == set(SERVER_VIDEO)


def test_prepare_generated_dataset_has_exact_expected_task_count(tmp_path):
    dataset = benchmark.prepare_dataset(None, 2, tmp_path / "photos")
    assert dataset["photos"] == 2
    assert dataset["expected_core_tasks"] == 1 + 2 * 2
    assert dataset["min_expected_core_tasks"] == 1 + 2 * 2
    assert (tmp_path / "photos" / "album_000" / "IMG_00000.jpg").is_file()


# ---------------------------------------------------------------------------
# Fixture generation and report rendering
# ---------------------------------------------------------------------------
def test_generate_photos_is_reproducible_and_countable(tmp_path):
    folder = tmp_path / "photos"
    benchmark.generate_photos(folder, 3, seed=7)
    count, size = benchmark.count_media_files(folder)
    assert count == 3
    assert size > 0
    assert (folder / "album_000" / "IMG_00000.jpg").is_file()
    assert (folder / "album_000" / "IMG_00002.jpg").is_file()


def test_render_markdown_contains_core_metrics():
    result = {
        "schema_version": 1,
        "run_id": "unit-test",
        "status": "passed",
        "started_at": "2026-01-01T00:00:00+08:00",
        "finished_at": "2026-01-01T00:00:10+08:00",
        "environment": {"api_base_url": "http://127.0.0.1:8000", "git_commit": "abc123"},
        "dataset": {"folder": "/tmp/photos", "photos": 10, "bytes": 1024},
        "summary": {
            "pipeline_seconds": 5.0,
            "photos": 10,
            "bytes": 1024,
            "photos_per_second": 2.0,
            "seconds_per_photo": 0.5,
            "core_tasks_completed": 21,
            "core_tasks_expected": 21,
            "core_failed": 0,
            "scan_task_seconds": 0.5,
            "add_directory_seconds": 0.1,
            "scan_new_files": 10,
        },
        "tasks": [
            {
                "type": "PROCESS_BASIC",
                "count": 10,
                "completed": 10,
                "failed": 0,
                "queue_seconds": {"mean": 0.1},
                "execution_seconds": {"mean": 0.2},
                "total_seconds": {"p50": 0.3, "p95": 0.4},
                "throughput_tasks_per_second": 2.0,
            }
        ],
        "scan": {"task_id": "scan-1", "status": "completed", "new_files": 10, "deleted_files": 0},
        "task_samples": [],
        "events": {"sse_event_count": 30, "sse_parse_errors": 0},
    }
    text = benchmark._render_markdown(result)
    assert "# TrailSnap 文件夹扫描性能报告" in text
    assert "10 张" not in text  # rendered through the photos metric table
    assert "2.0 张/秒" in text
    assert "PROCESS_BASIC" in text
    assert "scan-1" in text
