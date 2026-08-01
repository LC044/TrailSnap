"""Unit tests for ``app.core.logger`` -- the JSON-formatted logger used by
both the API server and the AI worker.

Why this file exists:

* The nightly gap scan flagged ``app/core/logger.py`` as uncovered. The
  file powers every request's structured log line, so a silent regression
  (e.g. dropping the ``operation`` key) would break downstream log
  ingestion in production where there is no other test boundary.

What we cover:

* ``JSONFormatter`` -- produces a JSON line with the four baseline keys,
  serialises tracebacks when ``exc_info`` is set, and preserves the
  ``operation`` / ``params`` / ``result`` extras.
* ``DailySizeRotatingFileHandler`` -- switches its filename when the day
  rolls over, and prunes the oldest files once ``limit_backup_count`` is
  exceeded.
* ``log_operation`` -- dispatches to the correct ``logging`` level and
  attaches ``exc_info`` when an error is supplied.

The module mutates process-wide state (``logging.getLogger()`` handlers),
so every test restores the previous handler stack.
"""

import json
import logging
import time
from datetime import date
from pathlib import Path

import pytest

from app.core.logger import (
    DailySizeRotatingFileHandler,
    JSONFormatter,
    log_operation,
)


pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


@pytest.fixture
def restore_loggers():
    """Snapshot + restore logger handler lists so we don't pollute other tests."""
    snapshots = {}
    for name in ("", "app", "uvicorn", "uvicorn.access", "uvicorn.error", "fastapi"):
        snapshots[name] = list(logging.getLogger(name).handlers)
    yield
    for name, original in snapshots.items():
        logging.getLogger(name).handlers = list(original)


# ---------------------------------------------------------------------------
# JSONFormatter
# ---------------------------------------------------------------------------


def _build_record(message="hello", level=logging.INFO, **extras):
    """Create a LogRecord with optional extras, bypassing actual logging I/O."""
    record = logging.LogRecord(
        name="app.test",
        level=level,
        pathname=__file__,
        lineno=10,
        msg=message,
        args=(),
        exc_info=None,
    )
    for k, v in extras.items():
        setattr(record, k, v)
    return record


def test_json_formatter_outputs_core_keys():
    """Every record must contain the four baseline keys regardless of extras."""
    formatter = JSONFormatter()
    record = _build_record("hello world")
    data = json.loads(formatter.format(record))
    assert data["message"] == "hello world"
    assert data["level"] == "INFO"
    assert data["operation"] == "N/A"
    assert data["params"] == {}
    assert data["result"] == "N/A"
    assert "timestamp" in data


def test_json_formatter_preserves_extra_fields():
    """The ``operation`` / ``params`` / ``result`` extras must survive."""
    formatter = JSONFormatter()
    record = _build_record(
        "scene_detect",
        operation="scan_folder",
        params={"path": "/a/b"},
        result="ok",
    )
    data = json.loads(formatter.format(record))
    assert data["operation"] == "scan_folder"
    assert data["params"] == {"path": "/a/b"}
    assert data["result"] == "ok"


def test_json_formatter_includes_stack_trace_on_exc_info():
    """An exception should surface as a ``stack_trace`` field."""
    formatter = JSONFormatter()
    try:
        raise ValueError("boom")
    except ValueError:
        import sys
        record = _build_record("bad input", level=logging.ERROR)
        record.exc_info = sys.exc_info()
    data = json.loads(formatter.format(record))
    assert data["level"] == "ERROR"
    assert "ValueError" in data["stack_trace"]
    assert "boom" in data["stack_trace"]


def test_json_formatter_does_not_escape_unicode():
    """Operators routinely grep for the Chinese operation name; the
    formatter must NOT ASCII-escape characters."""
    formatter = JSONFormatter()
    record = _build_record("中文消息", operation="扫描目录")
    line = formatter.format(record)
    assert "中文消息" in line
    assert "扫描目录" in line


# ---------------------------------------------------------------------------
# DailySizeRotatingFileHandler
# ---------------------------------------------------------------------------


def test_daily_rotating_handler_get_filename_uses_iso_date(tmp_path):
    """``_get_filename`` must embed the ISO date into the filename."""
    handler = DailySizeRotatingFileHandler(
        filename="server",
        log_dir=str(tmp_path),
        maxBytes=1024,
        backupCount=3,
    )
    handler.close()
    expected = str(tmp_path / "server-2026-07-31.log")
    assert handler._get_filename(date(2026, 7, 31)) == expected


def test_daily_rotating_handler_cleanup_deletes_oldest(tmp_path):
    """When more than ``backupCount`` files exist, the oldest ones get
    deleted in chronological order. ``os.utime`` forces deterministic
    mtimes so the sort is reproducible across platforms."""
    import os
    from datetime import timedelta
    handler = DailySizeRotatingFileHandler(
        filename="server",
        log_dir=str(tmp_path),
        maxBytes=1024,
        backupCount=2,
    )
    # Five older files (week-old names) plus the one opened by the handler init.
    base = time.time() - 1000
    today = date.today()
    fixture_oldest = today - timedelta(days=7)
    for i in range(5):
        p = tmp_path / f"server-{fixture_oldest.year}-{fixture_oldest.month:02d}-{fixture_oldest.day + i:02d}.log"
        p.write_text("log", encoding="utf-8")
        os.utime(p, (base + i * 60, base + i * 60))

    handler._cleanup_logs()

    remaining = sorted(p.name for p in tmp_path.glob("*.log"))
    # backupCount=2 -> only the two newest (one we created, one the handler opened) survive.
    # newest of the five fixtures is index 4 (highest mtime); today is the handler init file.
    newest_fixture = f"server-{fixture_oldest.year}-{fixture_oldest.month:02d}-{fixture_oldest.day + 4:02d}.log"
    today_file = f"server-{today.year}-{today.month:02d}-{today.day:02d}.log"
    assert remaining == [newest_fixture, today_file]
    handler.close()


def test_daily_rotating_handler_cleanup_noop_when_within_limit(tmp_path):
    """Less than ``backupCount`` files means no deletion."""
    handler = DailySizeRotatingFileHandler(
        filename="server",
        log_dir=str(tmp_path),
        maxBytes=1024,
        backupCount=10,
    )
    for i in range(3):
        (tmp_path / f"server-2026-07-{i:02d}.log").write_text("x")
    handler._cleanup_logs()
    assert len(list(tmp_path.glob("*.log*"))) == 4
    handler.close()


def test_daily_rotating_handler_cleanup_tolerates_missing_dir(tmp_path):
    """If the log directory vanishes, ``_cleanup_logs`` must NOT raise.
    On Windows the parent dir unlink may refuse if files are still open,
    so we discard the handler up-front to avoid PermissionError noise
    from the tempfile teardown instead of from ``_cleanup_logs`` itself."""
    handler = DailySizeRotatingFileHandler(
        filename="server",
        log_dir=str(tmp_path),
        maxBytes=1024,
        backupCount=1,
    )
    handler.close()
    # Remove the directory after closing the handler.
    import shutil
    shutil.rmtree(tmp_path, ignore_errors=True)
    # Recreating the handler against a dead path is fine -- it mkdirs --
    # but now DELETE the dir again so ``_cleanup_logs`` sees an empty glob.
    handler2 = DailySizeRotatingFileHandler(
        filename="server",
        log_dir=str(tmp_path),
        maxBytes=1024,
        backupCount=1,
    )
    handler2.close()
    shutil.rmtree(tmp_path, ignore_errors=True)

    # Build a fresh handler whose internal cleanup is invoked directly.
    handler3 = DailySizeRotatingFileHandler(
        filename="server",
        log_dir=str(tmp_path),
        maxBytes=1024,
        backupCount=1,
    )
    shutil.rmtree(tmp_path, ignore_errors=True)
    # The cleanup branch glob over a non-existent folder must not throw.
    handler3._cleanup_logs()
    handler3.close()


# ---------------------------------------------------------------------------
# log_operation helper
# ---------------------------------------------------------------------------


def test_log_operation_info_attaches_extra(caplog, restore_loggers):
    """``log_operation(..., level='info')`` calls ``logger.info`` and
    propagates the operation/params/result trio into extras."""
    caplog.set_level(logging.INFO, logger="app")

    log_operation(
        "info",
        "starting scan",
        operation="scan_folder",
        params={"path": "/photos"},
        result="started",
    )

    record = next(r for r in caplog.records if r.getMessage() == "starting scan")
    assert record.levelno == logging.INFO
    assert getattr(record, "operation") == "scan_folder"
    assert getattr(record, "params") == {"path": "/photos"}
    assert getattr(record, "result") == "started"


def test_log_operation_warning_and_debug_branches(caplog, restore_loggers):
    """Both 'warn' and 'debug' string aliases must reach their logger methods."""
    caplog.set_level(logging.DEBUG, logger="app")

    log_operation("warn", "rate limit hit", operation="api", params={}, result="429")
    warn_record = next(r for r in caplog.records if r.getMessage() == "rate limit hit")
    assert warn_record.levelno == logging.WARNING

    log_operation("debug", "step done", operation="api", params={}, result="ok")
    debug_record = next(r for r in caplog.records if r.getMessage() == "step done")
    assert debug_record.levelno == logging.DEBUG


def test_log_operation_error_attaches_exc_info(caplog, restore_loggers):
    """When an ``error=`` is passed, the helper must call
    ``logger.error(..., exc_info=...)`` so the traceback lands in the JSON output."""
    import traceback
    caplog.set_level(logging.ERROR, logger="app")

    try:
        raise RuntimeError("explode")
    except RuntimeError as exc:
        log_operation("error", "boom", operation="ocr", params={}, result="err", error=exc)

    record = next(r for r in caplog.records if r.getMessage() == "boom")
    assert record.levelno == logging.ERROR
    # exc_info gets serialised; the traceback's text mentions RuntimeError.
    assert record.exc_info is not None
    formatted = "".join(traceback.format_exception(*record.exc_info))
    assert "RuntimeError" in formatted
    assert "explode" in formatted
