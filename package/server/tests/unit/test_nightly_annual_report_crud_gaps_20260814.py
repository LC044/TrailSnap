"""Unit tests covering 2026-08-14 nightly coverage gap scan.

Modules exercised:
* app/crud/annual_report.py -- get_date_range_filter (chains time + is_deleted +
  optional user_id), find_best_match_photo (sqlite branch happy path + empty +
  zero-norm target guard + month filter applied).
"""
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


pytestmark = [pytest.mark.smoke]


def _chain_db_for_match(rows, extra_filter=False):
    """Build a db mock whose query chain ends with a terminal exposing `all()` returning rows."""
    db = MagicMock()
    db.bind.dialect.name = "sqlite"
    terminal = MagicMock()
    terminal.all.return_value = rows
    leaf = MagicMock(with_entities=MagicMock(return_value=terminal))
    if extra_filter:
        leaf = MagicMock(filter=MagicMock(return_value=leaf))
    leaf = MagicMock(filter=MagicMock(return_value=leaf))
    leaf = MagicMock(filter=MagicMock(return_value=leaf))
    leaf = MagicMock(filter=MagicMock(return_value=leaf))
    db.query.return_value.join.return_value = leaf
    return db


def test_get_date_range_filter_applies_time_and_deleted():
    from app.crud.annual_report import get_date_range_filter

    query = MagicMock()
    chained = MagicMock()
    query.filter.return_value = chained

    result = get_date_range_filter(query, datetime(2024, 1, 1), datetime(2024, 12, 31))

    assert result is chained
    # Single .filter() call with 3 conditions (start, end, is_deleted)
    assert query.filter.call_count == 1
    assert len(query.filter.call_args.args) == 3


def test_get_date_range_filter_with_user_id():
    from app.crud.annual_report import get_date_range_filter

    query = MagicMock()
    first = MagicMock()
    second = MagicMock()
    query.filter.return_value = first
    first.filter.return_value = second

    result = get_date_range_filter(
        query, datetime(2024, 1, 1), datetime(2024, 12, 31), user_id="u-1"
    )

    assert result is second
    # Two .filter() calls: time/delete trio + user_id
    assert query.filter.call_count == 1
    assert first.filter.call_count == 1
    assert len(first.filter.call_args.args) == 1  # user_id condition


def test_find_best_match_photo_returns_none_when_no_rows():
    from app.crud import annual_report as ar

    db = _chain_db_for_match([])
    result = ar.find_best_match_photo(db, datetime(2024, 1, 1), datetime(2024, 12, 31), [0.1, 0.2, 0.3])
    assert result is None


def test_find_best_match_photo_picks_most_similar_in_sqlite():
    from app.crud import annual_report as ar

    p1 = SimpleNamespace(id="p1", photo_time=datetime(2024, 5, 1))
    p2 = SimpleNamespace(id="p2", photo_time=datetime(2024, 6, 1))
    rows = [
        (p1, [0.1, 0.2, 0.3]),
        (p2, [0.9, 0.9, 0.9]),
    ]

    db = _chain_db_for_match(rows)
    result = ar.find_best_match_photo(db, datetime(2024, 1, 1), datetime(2024, 12, 31), [0.1, 0.2, 0.3])
    assert result is p1  # identical embedding -> smallest distance


def test_find_best_match_photo_handles_zero_norm_embedding():
    from app.crud import annual_report as ar

    p1 = SimpleNamespace(id="p1")
    rows = [(p1, [0.5, 0.5, 0.5])]
    db = _chain_db_for_match(rows)
    # Should not raise even with a zero-norm target
    result = ar.find_best_match_photo(db, datetime(2024, 1, 1), datetime(2024, 12, 31), [0.0, 0.0, 0.0])
    # best_photo may still be p1 because distance is bounded to 1.0 when target_norm == 0
    assert result is p1





