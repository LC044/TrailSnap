"""Nightly guards for 2026-11-05 backend coverage gaps.

The nightly coverage scan found small edge branches in path aggregation,
logger rotation, database pool disposal, album task failures, and agent
photo-search validation.  These tests stay in-memory and mock persistence so
they remain fast and do not depend on a live stack.
"""

import asyncio
import logging
import os
import time
import uuid
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.core.logger import DailySizeRotatingFileHandler
from app.db import session as db_session
from app.service.agent import photo_search
from app.service.tasks import album as album_tasks
from app.utils.path import (
    build_folder_tree_level,
    compute_browse_path,
    compute_relative_path,
)

pytestmark = pytest.mark.smoke


def test_compute_relative_path_falls_back_to_parent_when_no_root_matches(tmp_path):
    root = tmp_path / "root"
    folder, filename = compute_relative_path(
        str(tmp_path / "unmanaged" / " Travel" / "photo.jpg"), ["", root.as_posix()]
    )
    assert folder == " Travel"
    assert filename == "photo.jpg"


def test_compute_browse_path_prefixes_longest_matching_root(tmp_path):
    parent = tmp_path / "roots"
    nested = parent / "nested"
    folder, filename = compute_browse_path(
        str(nested / "2026" / "photo.jpg"), [parent.as_posix(), nested.as_posix()]
    )
    assert folder == "nested/2026"
    assert filename == "photo.jpg"


def test_build_folder_tree_level_tolerates_bad_rows_and_counts_root_files(tmp_path):
    root = tmp_path / "root"
    rows = [
        None,
        42,
        (str(root / "photo.jpg"),),
        (str(root / "travel" / "hiking" / "a.jpg"),),
        (str(root / "travel" / "hiking" / "b.jpg"),),
        (str(tmp_path / "other" / "photo.jpg"),),
    ]
    tree = build_folder_tree_level(rows, [root.as_posix()], parent=root.name)
    assert tree["own_count"] == 1
    children = {child["name"]: child for child in tree["children"]}
    assert children["travel"]["count"] == 2
    assert children["travel"]["has_children"] is True


def test_daily_logger_rotates_date_and_prunes_oldest_files(tmp_path):
    for index, stamp in enumerate((100, 200, 300)):
        old = tmp_path / f"main-{date.fromordinal(1).isoformat()}.{index}.log"
        old.write_text("old", encoding="utf-8")
        os.utime(old, (stamp, stamp))

    handler = DailySizeRotatingFileHandler(
        "main", str(tmp_path), maxBytes=10000, backupCount=1
    )
    old_stream = MagicMock()
    handler.stream = old_stream
    record = logging.LogRecord(
        "nightly", logging.INFO, __file__, 1, "rotate", None, None
    )
    handler.current_date = date.today() - timedelta(days=1)
    handler.emit(record)
    try:
        assert old_stream.close.called
        assert handler.baseFilename == handler._get_filename(date.today())
        remaining = list(tmp_path.glob("*.log*"))
        assert len(remaining) == 1
        assert "2026-11-05" in remaining[0].name
    finally:
        handler.close()


def test_dispose_inherited_connections_keeps_parent_connections_open(monkeypatch):
    engine = MagicMock()
    monkeypatch.setattr(db_session, "engine", engine)
    db_session.dispose_inherited_connections()
    engine.dispose.assert_called_once_with(close=False)


def test_scan_album_rolls_back_when_album_lookup_fails():
    db = MagicMock()
    task = SimpleNamespace(payload={"album_id": uuid.uuid4().hex})
    with patch.object(
        album_tasks.crud_album, "get_album", side_effect=RuntimeError("db gone")
    ):
        with pytest.raises(RuntimeError, match="db gone"):
            asyncio.run(
                album_tasks.ScanAlbumStrategy().process(
                    worker=MagicMock(), task=task, db=db
                )
            )
    db.rollback.assert_called_once_with()


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        (
            {"start_date": "2026-11-06", "end_date": "2026-11-05"},
            "开始日期不能晚于结束日期",
        ),
        ({"min_people": -1}, "人数不能为负数"),
        (
            {"min_people": 3, "max_people": 2},
            "最少人数不能大于最多人数",
        ),
    ],
)
def test_search_photo_ids_rejects_invalid_ranges(kwargs, message):
    with pytest.raises(ValueError, match=message):
        photo_search.search_photo_ids(
            MagicMock(), str(uuid.uuid4()), **kwargs
        )


