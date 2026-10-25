"""Nightly coverage for ``app/core/logger.py`` and ``app/services/model_manager.py``
(2026-10-26).

The 2026-10-26 AI coverage scan listed

* ``core/logger.py`` at 87.9% -- the failure paths of the rotating file
  handler (un-creatable log directory, failing ``emit``, failing cleanup) and
  the level dispatch of ``log_operation`` were never exercised;
* ``services/model_manager.py`` at 87.3% -- the "a release is in flight"
  wait, the failing ``release_func``, the family filters of
  ``release_except`` and the idle-eviction of the monitor loop were never
  exercised.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

import pytest

pytestmark = [pytest.mark.smoke]


# ---------------------------------------------------------------------------
# core/logger.py
# ---------------------------------------------------------------------------


def test_handler_survives_an_unusable_log_directory(monkeypatch, tmp_path, capsys):
    """A log directory that cannot be created must not crash the handler."""
    from app.core import logger as logger_mod

    log_dir = tmp_path / "logs"
    log_dir.mkdir()

    real_path = logger_mod.Path

    class _FailingPath(real_path):
        def mkdir(self, *args, **kwargs):
            raise OSError("read-only file system")

    monkeypatch.setattr(logger_mod, "Path", _FailingPath)

    handler = logger_mod.DailySizeRotatingFileHandler(
        filename="main",
        log_dir=str(log_dir),
        maxBytes=1024,
        backupCount=2,
    )

    assert "Failed to create log directory" in capsys.readouterr().out
    handler.close()


def test_emit_falls_back_to_handle_error(monkeypatch, tmp_path):
    from app.core.logger import DailySizeRotatingFileHandler

    handler = DailySizeRotatingFileHandler(
        filename="main",
        log_dir=str(tmp_path / "logs"),
        maxBytes=1024,
        backupCount=2,
    )
    handled = []
    monkeypatch.setattr(handler, "handleError", lambda record: handled.append(record))
    monkeypatch.setattr(handler, "_cleanup_logs", lambda: (_ for _ in ()).throw(RuntimeError("cleanup broke")))

    record = logging.LogRecord("test", logging.INFO, __file__, 1, "hello", None, None)
    handler.emit(record)

    assert handled == [record]
    handler.close()


def test_cleanup_ignores_files_it_cannot_delete(monkeypatch, tmp_path):
    from app.core.logger import DailySizeRotatingFileHandler

    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    for index in range(4):
        (log_dir / f"main-2026-01-0{index}.log").write_text("x", encoding="utf-8")

    handler = DailySizeRotatingFileHandler(
        filename="main",
        log_dir=str(log_dir),
        maxBytes=1024,
        backupCount=2,
    )
    monkeypatch.setattr(Path, "unlink", lambda self: (_ for _ in ()).throw(OSError("still open")))

    handler._cleanup_logs()  # must not raise

    handler.close()


def test_cleanup_swallows_unexpected_errors(monkeypatch, tmp_path):
    from app.core.logger import DailySizeRotatingFileHandler

    log_dir = tmp_path / "logs"
    log_dir.mkdir()

    handler = DailySizeRotatingFileHandler(
        filename="main",
        log_dir=str(log_dir),
        maxBytes=1024,
        backupCount=2,
    )
    monkeypatch.setattr(Path, "glob", lambda self, pattern: (_ for _ in ()).throw(RuntimeError("glob broke")))

    handler._cleanup_logs()  # must not raise

    handler.close()


def test_cleanup_keeps_the_newest_files(monkeypatch, tmp_path):
    from app.core.logger import DailySizeRotatingFileHandler

    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    files = []
    for index in range(4):
        path = log_dir / f"main-2026-01-0{index}.log"
        path.write_text("x", encoding="utf-8")
        files.append(path)
        # keep the modification times strictly increasing
        import os as _os

        _os.utime(path, (1_700_000_000 + index, 1_700_000_000 + index))

    handler = DailySizeRotatingFileHandler(
        filename="main",
        log_dir=str(log_dir),
        maxBytes=1024,
        backupCount=2,
    )
    handler._cleanup_logs()

    # The handler keeps `backupCount` newest files; its own log file is the newest.
    remaining = sorted(path.name for path in log_dir.glob("*.log*"))
    assert len(remaining) == 2
    assert "main-2026-01-00.log" not in remaining
    assert "main-2026-01-01.log" not in remaining
    handler.close()


@pytest.mark.parametrize(
    ("level", "expected"),
    [
        ("info", "INFO"),
        ("INFO", "INFO"),
        ("warn", "WARNING"),
        ("warning", "WARNING"),
        ("debug", "DEBUG"),
        ("error", "ERROR"),
    ],
)
def test_log_operation_dispatches_on_level(level, expected):
    from app.core.logger import log_operation

    records = []

    class Capture(logging.Handler):
        def emit(self, record):
            records.append(record)

    logger = logging.getLogger("app")
    capture = Capture()
    logger.addHandler(capture)
    previous_level = logger.level
    logger.setLevel(logging.DEBUG)
    try:
        log_operation(level, "hello", operation="op")
    finally:
        logger.removeHandler(capture)
        logger.setLevel(previous_level)

    assert [record.levelname for record in records] == [expected]


def test_log_operation_with_an_error_uses_the_error_level():
    from app.core.logger import log_operation

    records = []

    class Capture(logging.Handler):
        def emit(self, record):
            records.append(record)

    logger = logging.getLogger("app")
    capture = Capture()
    logger.addHandler(capture)
    previous_level = logger.level
    logger.setLevel(logging.DEBUG)
    try:
        log_operation("info", "boom", error=ValueError("nope"))
    finally:
        logger.removeHandler(capture)
        logger.setLevel(previous_level)

    assert records[0].levelname == "ERROR"
    assert records[0].exc_info is not None


# ---------------------------------------------------------------------------
# services/model_manager.py
# ---------------------------------------------------------------------------


def test_get_waits_for_an_in_flight_release():
    """``get()`` must not hand out a model that is being released."""
    from app.services.model_manager import ModelWrapper

    wrapper = ModelWrapper("slow", lambda: "model")
    wrapper.model = "model"
    wrapper.releasing = True

    def finish():
        time.sleep(0.05)
        with wrapper.condition:
            wrapper.releasing = False
            wrapper.condition.notify_all()

    thread = threading.Thread(target=finish)
    thread.start()

    assert wrapper.get() == "model"
    thread.join()


def test_release_survives_a_failing_release_func(caplog):
    from app.services.model_manager import ModelWrapper

    def broken(_model):
        raise RuntimeError("release exploded")

    wrapper = ModelWrapper("broken", lambda: "model", release_func=broken)
    wrapper.get()

    with caplog.at_level(logging.ERROR):
        wrapper.release()

    assert wrapper.model is None
    assert any("release exploded" in record.getMessage() for record in caplog.records)


def test_release_async_is_a_noop_without_a_model():
    from app.services.model_manager import ModelWrapper

    wrapper = ModelWrapper("empty", lambda: "model")
    assert wrapper.release_async() is False


def test_release_async_frees_the_model():
    from app.services.model_manager import ModelWrapper

    wrapper = ModelWrapper("busy", lambda: "model")
    wrapper.get()

    assert wrapper.release_async() is True
    for _ in range(100):
        if wrapper.model is None:
            break
        time.sleep(0.01)

    assert wrapper.model is None
    assert wrapper.releasing is False


def test_release_except_keeps_the_requested_family():
    from app.services.model_manager import model_manager

    model_manager.models.clear()
    released = []

    def register(name):
        wrapper = SimpleWrapper(name, released)
        model_manager.models[name] = wrapper
        return wrapper

    register("yolo_photo_cls_a")
    register("yolo_photo_cls_b")
    register("clip_text")
    register("tickets_yolo")
    register("unrelated")

    try:
        model_manager.release_except("classification")
        assert sorted(released) == ["clip_text", "tickets_yolo", "unrelated"]

        released.clear()
        model_manager.release_except("embedding")
        assert sorted(released) == ["tickets_yolo", "unrelated", "yolo_photo_cls_a", "yolo_photo_cls_b"]

        released.clear()
        model_manager.release_except("tickets")
        assert sorted(released) == ["clip_text", "unrelated", "yolo_photo_cls_a", "yolo_photo_cls_b"]

        released.clear()
        model_manager.release_except("unrelated")
        assert sorted(released) == ["clip_text", "tickets_yolo", "yolo_photo_cls_a", "yolo_photo_cls_b"]
    finally:
        model_manager.models.clear()


class SimpleWrapper:
    """Minimal stand-in for ``ModelWrapper`` recording release calls."""

    def __init__(self, name, released):
        self.name = name
        self._released = released

    def release(self):
        self._released.append(self.name)


def test_monitor_loop_evicts_idle_models(monkeypatch):
    from app.services.model_manager import ModelManager

    manager = ModelManager.__new__(ModelManager)
    manager.models = {}
    manager.idle_timeout = 0
    manager.running = True

    released = []

    class IdleWrapper:
        name = "idle"
        model = "model"
        last_used = 0

        def release(self):
            released.append(self.name)

    manager.models["idle"] = IdleWrapper()

    def stop_after_one_sleep(_seconds):
        manager.running = False

    monkeypatch.setattr(time, "sleep", stop_after_one_sleep)
    monkeypatch.setattr(time, "time", lambda: 1_000_000.0)

    manager._monitor_loop()

    assert released == ["idle"]
    assert manager.running is False
