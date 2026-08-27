"""Unit tests for the gap-remaining branches in app/service/agent/tools.py.

Why this file exists:

* The nightly gap scan flagged app/service/agent/tools.py as 64.3 percent
  covered (81 missed lines out of 227). The pre-existing
  test_nightly_agent_tools_gaps_20260814.py covers the happy paths for
  search_photos_tool and the other tool wrappers. This file fills the
  remaining uncovered surface in _build_search_summary.
"""

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from app.service.agent import tools as tools_module


pytestmark = [pytest.mark.smoke, pytest.mark.module_agent]


def _chained(*, first=None, all_rows=None):
    """Chainable MagicMock with optional first()/all() terminals."""
    q = MagicMock()
    q.filter.return_value = q
    q.join.return_value = q
    q.group_by.return_value = q
    q.order_by.return_value = q
    q.limit.return_value = q
    if first is not None:
        q.first.return_value = first
    if all_rows is not None:
        q.all.return_value = all_rows
    return q


# _build_search_summary -- success path
# ---------------------------------------------------------------------------


def test_build_search_summary_populates_all_three_sub_aggregations():
    """When every sub-query returns rows the summary dict carries all three."""
    db = MagicMock()
    id_subq = MagicMock(name="id_subq")
    id_subq.c.id = MagicMock(name="id")
    filtered_query = MagicMock(name="filtered_query")
    filtered_query.with_entities.return_value.order_by.return_value.subquery.return_value = id_subq

    # 6 db.query() calls per execution: each of date_range / top_locations /
    # top_tags builds a query with a .in_(subquery) filter, so each block
    # produces two db.query() calls (outer + the in_() subquery).
    date_q = _chained(first=(datetime(2026, 1, 1), datetime(2026, 12, 31)))
    in_subq_a = _chained()
    loc_q = _chained(all_rows=[("Wuhan", 10), ("Beijing", 5)])
    in_subq_b = _chained()
    tag_q = _chained(all_rows=[("travel", 8), ("citywalk", 3)])
    in_subq_c = _chained()
    queue = [date_q, in_subq_a, loc_q, in_subq_b, tag_q, in_subq_c]
    db.query.side_effect = lambda *_a, **_kw: queue.pop(0)

    summary = tools_module._build_search_summary(db, filtered_query, distance=None)

    assert summary["date_range"] == ["2026-01-01", "2026-12-31"]
    assert summary["top_locations"] == {"Wuhan": 10, "Beijing": 5}
    assert summary["top_tags"] == {"travel": 8, "citywalk": 3}


def test_build_search_summary_swallows_top_level_exception():
    """If the outer db.query itself raises, the function returns an empty dict."""
    db = MagicMock()
    filtered_query = MagicMock(name="filtered_query")
    filtered_query.with_entities.return_value.order_by.return_value.subquery.side_effect = RuntimeError("boom")

    summary = tools_module._build_search_summary(db, filtered_query, distance=None)

    assert summary == {}


def test_build_search_summary_skips_date_range_when_no_rows():
    """When the date_range query returns None the key is not added."""
    db = MagicMock()
    id_subq = MagicMock(name="id_subq")
    id_subq.c.id = MagicMock(name="id")
    filtered_query = MagicMock(name="filtered_query")
    filtered_query.with_entities.return_value.order_by.return_value.subquery.return_value = id_subq
    date_q = _chained(first=None)
    in_subq_a = _chained()
    loc_q = _chained(all_rows=[("Wuhan", 10)])
    in_subq_b = _chained()
    tag_q = _chained(all_rows=[("travel", 5)])
    in_subq_c = _chained()
    queue = [date_q, in_subq_a, loc_q, in_subq_b, tag_q, in_subq_c]
    db.query.side_effect = lambda *_a, **_kw: queue.pop(0)

    summary = tools_module._build_search_summary(db, filtered_query, distance=None)

    assert "date_range" not in summary
    assert summary["top_locations"] == {"Wuhan": 10}
    assert summary["top_tags"] == {"travel": 5}
