import json
import logging
import os
import time
from datetime import datetime

import pytest

from app.core.logger import DailySizeRotatingFileHandler, JSONFormatter

pytestmark = [pytest.mark.smoke]


def _record(message="hello %s", *args):
    return logging.LogRecord(
        name="app",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=args,
        exc_info=None,
        func="test",
    )


def test_json_formatter_outputs_operation_context():
    record = _record("hello %s", "world")
    setattr(record, "operation", "unit-test")
    setattr(record, "params", {"key": "value"})
    setattr(record, "result", "ok")

    payload = json.loads(JSONFormatter().format(record))

    assert payload["level"] == "INFO"
    assert payload["message"] == "hello world"
    assert payload["operation"] == "unit-test"
    assert payload["params"] == {"key": "value"}
    assert payload["result"] == "ok"
    assert "timestamp" in payload


def test_daily_rotating_handler_uses_dated_filename_and_cleans_old_logs(tmp_path):
    handler = DailySizeRotatingFileHandler(
        filename="unit-app",
        log_dir=str(tmp_path),
        maxBytes=128,
        backupCount=2,
    )
    try:
        expected_name = f"unit-app-{datetime.now().date():%Y-%m-%d}.log"
        assert (tmp_path / expected_name).exists()

        old_files = [
            tmp_path / "unit-app-2000-01-01.log",
            tmp_path / "unit-app-2000-01-02.log",
            tmp_path / "unit-app-2000-01-03.log",
        ]
        for index, path in enumerate(old_files):
            path.write_text("old", encoding="utf-8")
            stamp = time.mktime((2000, 1, index + 1, 0, 0, 0, 0, 0, -1))
            os.utime(path, (stamp, stamp))

        handler._cleanup_logs()

        assert not old_files[0].exists()
        assert not old_files[1].exists()
        assert old_files[2].exists()
        assert (tmp_path / expected_name).exists()
    finally:
        handler.close()