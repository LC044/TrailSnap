"""2026-09-13 nightly test for AI logger date rollover."""

from datetime import date, timedelta
from pathlib import Path
import logging

import pytest


pytestmark = [pytest.mark.smoke]


def test_daily_rotating_handler_changes_file_when_date_changes(tmp_path: Path):
    from app.core.logger import DailySizeRotatingFileHandler

    handler = DailySizeRotatingFileHandler(
        filename="main",
        log_dir=str(tmp_path),
        maxBytes=1024 * 1024,
        backupCount=10,
    )
    try:
        yesterday = date.today() - timedelta(days=1)
        handler.current_date = yesterday
        handler.baseFilename = handler._get_filename(yesterday)

        record = logging.LogRecord(
            name="nightly",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="date rollover",
            args=(),
            exc_info=None,
        )
        handler.emit(record)

        today_name = handler._get_filename(date.today())
        assert handler.current_date == date.today()
        assert handler.baseFilename == today_name
        assert "date rollover" in Path(today_name).read_text(encoding="utf-8")
    finally:
        handler.close()
