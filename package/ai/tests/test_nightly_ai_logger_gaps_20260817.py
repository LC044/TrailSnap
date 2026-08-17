"""Unit tests for app/core/logger.py (nightly round 13, 2026-08-17).

Targets:
  * JSONFormatter -- base fields, exc_info, defaults, UTF-8 message.
  * DailySizeRotatingFileHandler -- filename format, cleanup logic,
    date rollover behaviour.
  * setup_logging -- returns listener, attaches queue handler, configures
    uvicorn loggers.
  * log_operation -- info / warn / error helpers, error -> exc_info.

The full module is import-safe without GPU; tests pass a tmp_path as
LOG_DIR via ``monkeypatch.setenv`` to keep disk footprint contained.
"""
import json as _json
import logging
import logging.handlers
import os
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest


pytestmark = [pytest.mark.smoke]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _make_record(name="app", level=logging.INFO, msg="hello", exc_info=None,
                 args=()):
    logger = logging.getLogger(name)
    return logger.makeRecord(
        name=name,
        level=level,
        fn="x.py",
        lno=1,
        msg=msg,
        args=args,
        exc_info=exc_info,
    )


@pytest.fixture
def log_dir(monkeypatch, tmp_path):
    """Pin ``TS_AI_LOG_DIR`` to a fresh tmp_path for the duration of the
    test, so the handler does not touch the user's real log directory."""
    monkeypatch.setenv("TS_AI_LOG_DIR", str(tmp_path))
    return tmp_path


# ---------------------------------------------------------------------------
# JSONFormatter
# ---------------------------------------------------------------------------
class TestJSONFormatter:
    def test_basic_fields_present(self):
        from app.core.logger import JSONFormatter

        rec = _make_record(msg="basic")
        out = _json.loads(JSONFormatter().format(rec))
        assert out["level"] == "INFO"
        assert out["message"] == "basic"
        assert out["operation"] == "N/A"
        assert out["params"] == {}
        assert out["result"] == "N/A"
        assert "timestamp" in out

    def test_exc_info_adds_stack_trace(self):
        from app.core.logger import JSONFormatter

        try:
            raise RuntimeError("boom")
        except RuntimeError:
            import sys
            rec = _make_record(level=logging.ERROR, msg="err", exc_info=sys.exc_info())

        out = _json.loads(JSONFormatter().format(rec))
        assert out["level"] == "ERROR"
        assert "stack_trace" in out
        assert "RuntimeError" in out["stack_trace"]

    def test_extra_fields_propagate_to_output(self):
        from app.core.logger import JSONFormatter

        rec = _make_record(msg="hi")
        rec.operation = "scan"
        rec.params = {"foo": "bar"}
        rec.result = "ok"

        out = _json.loads(JSONFormatter().format(rec))
        assert out["operation"] == "scan"
        assert out["params"] == {"foo": "bar"}
        assert out["result"] == "ok"

    def test_utf8_message_preserved(self):
        from app.core.logger import JSONFormatter

        rec = _make_record(msg="中文日志")
        raw = JSONFormatter().format(rec)
        # ensure_ascii=False so message is preserved as-is in the JSON.
        assert "中文日志" in raw


# ---------------------------------------------------------------------------
# DailySizeRotatingFileHandler
# ---------------------------------------------------------------------------
class TestDailySizeRotatingHandler:
    def test_filename_format_uses_iso_date(self, log_dir):
        from app.core.logger import DailySizeRotatingFileHandler

        handler = DailySizeRotatingFileHandler(
            filename="main", log_dir=str(log_dir), maxBytes=1024, backupCount=5
        )
        try:
            expected = log_dir / f"main-{date.today().isoformat()}.log"
            assert handler.baseFilename == str(expected)
        finally:
            handler.close()

    def test_cleanup_no_op_when_under_limit(self, log_dir):
        from app.core.logger import DailySizeRotatingFileHandler

        handler = DailySizeRotatingFileHandler(
            filename="main",
            log_dir=str(log_dir),
            maxBytes=1024 * 1024,
            backupCount=10,
        )
        try:
            # Handler creates ``main-<today>.log`` on init. Add 2 more
            # historical files (total = 3 < backupCount=10).
            for i in range(2):
                (log_dir / f"main-2026-08-0{i}.log").write_text("x")

            before = sorted(p.name for p in log_dir.glob("*.log*"))
            handler._cleanup_logs()
            after = sorted(p.name for p in log_dir.glob("*.log*"))
            assert before == after
        finally:
            handler.close()

    def test_cleanup_deletes_oldest_when_over_limit(self, log_dir):
        from app.core.logger import DailySizeRotatingFileHandler

        handler = DailySizeRotatingFileHandler(
            filename="main",
            log_dir=str(log_dir),
            maxBytes=1024 * 1024,
            backupCount=2,
        )
        try:
            # Add 5 historical files with distinct mtimes -- ordered oldest
            # to newest. Handler's init-created file (today) is newer than
            # all of them, so cleanup will delete the 5 oldest of the 6
            # total files, leaving today's file + the newest historical.
            for i in range(5):
                p = log_dir / f"main-2026-08-0{i}.log"
                p.write_text("x")
                os.utime(p, (1_700_000_000 + i * 60, 1_700_000_000 + i * 60))

            handler._cleanup_logs()

            remaining = sorted(p.name for p in log_dir.glob("*.log*"))
            # backupCount=2 means keep the 2 newest files. The handler's
            # init file (``main-<today>.log``) has the latest mtime, then
            # ``main-2026-08-04.log`` is the most recent user file.
            assert len(remaining) == 2
            assert any("2026-08-04" in name for name in remaining)
        finally:
            handler.close()


# ---------------------------------------------------------------------------
# setup_logging
# ---------------------------------------------------------------------------
class TestSetupLogging:
    def test_returns_listener_and_attaches_queue_handler(self, log_dir, monkeypatch):
        import app.core.logger as logger_mod

        # Stub QueueListener so we don't actually spawn a thread.
        fake_listener = MagicMock()
        fake_listener_class = MagicMock(return_value=fake_listener)
        monkeypatch.setattr(
            logger_mod.logging.handlers, "QueueListener", fake_listener_class
        )

        root = logging.getLogger()
        saved_handlers = root.handlers[:]
        saved_level = root.level
        root.handlers = []
        try:
            listener = logger_mod.setup_logging(filename="probe")
            assert listener is fake_listener
            fake_listener.start.assert_called_once()
            handlers = root.handlers
            assert len(handlers) == 1
            assert isinstance(handlers[0], logging.handlers.QueueHandler)

            for name in ("uvicorn", "uvicorn.access", "uvicorn.error", "fastapi"):
                l = logging.getLogger(name)
                assert l.propagate is False
                assert l.handlers == handlers
        finally:
            root.handlers = saved_handlers
            root.level = saved_level


# ---------------------------------------------------------------------------
# log_operation helper
# ---------------------------------------------------------------------------
class TestLogOperation:
    def test_info_logs_without_error(self, caplog):
        from app.core.logger import log_operation

        caplog.set_level(logging.INFO, logger="app")
        log_operation("info", "did thing", operation="op", params={"k": 1}, result="ok")
        records = [r for r in caplog.records if r.name == "app"]
        assert any(r.levelno == logging.INFO for r in records)
        rec = next(r for r in records if r.levelno == logging.INFO)
        assert rec.operation == "op"
        assert rec.params == {"k": 1}
        assert rec.result == "ok"
        assert rec.message == "did thing"

    def test_warning_logs_at_warning_level(self, caplog):
        from app.core.logger import log_operation

        caplog.set_level(logging.WARNING, logger="app")
        log_operation("warn", "careful", operation="op")
        records = [r for r in caplog.records if r.name == "app"]
        assert any(r.levelno == logging.WARNING for r in records)

    def test_error_passes_exc_info(self, caplog):
        from app.core.logger import log_operation

        caplog.set_level(logging.ERROR, logger="app")
        try:
            raise RuntimeError("kaboom")
        except RuntimeError as e:
            log_operation("error", "failed", operation="op", error=e)

        records = [r for r in caplog.records if r.name == "app"]
        assert any(r.levelno == logging.ERROR for r in records)
        rec = next(r for r in records if r.levelno == logging.ERROR)
        assert rec.exc_info is not None
        assert rec.exc_info[0] is RuntimeError
