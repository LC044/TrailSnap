"""Nightly gap tests for Agent photo-search helpers (2026-09-08)."""
from datetime import datetime
from unittest.mock import MagicMock

import pytest

pytestmark = [pytest.mark.smoke]


def test_base_agent_photo_search_query_builds_safe_projection():
    from app.service.agent import tools as agent_tools
    from app.db.models.photo import Photo

    db = MagicMock()
    query = MagicMock()
    query.outerjoin.return_value = query
    db.query.return_value = query

    result = agent_tools._base_agent_photo_search_query(db, "user-1")

    assert result is query.filter.return_value
    db.query.assert_called_once_with(Photo.id, Photo.photo_time)
    assert query.outerjoin.call_count == 2
    query.filter.assert_called_once()


def test_build_search_summary_aggregates_dates_locations_and_tags():
    from app.service.agent import tools as agent_tools

    db = MagicMock()
    date_query = MagicMock()
    date_query.filter.return_value.first.return_value = (datetime(2026, 9, 1), datetime(2026, 9, 7))
    city_query = MagicMock()
    city_query.filter.return_value.group_by.return_value.order_by.return_value.limit.return_value.all.return_value = [("北京", 3), ("杭州", 2)]
    tag_query = MagicMock()
    tag_query.join.return_value.filter.return_value.group_by.return_value.order_by.return_value.limit.return_value.all.return_value = [("旅行", 4)]
    db.query.side_effect = [date_query, MagicMock(), city_query, MagicMock(), tag_query, MagicMock()]

    filtered = MagicMock()
    id_subquery = filtered.with_entities.return_value.order_by.return_value.subquery.return_value

    summary = agent_tools._build_search_summary(db, filtered, None)

    assert summary == {
        "date_range": ["2026-09-01", "2026-09-07"],
        "top_locations": {"北京": 3, "杭州": 2},
        "top_tags": {"旅行": 4},
    }
    assert id_subquery is not None


def test_build_search_summary_returns_empty_when_projection_fails():
    from app.service.agent import tools as agent_tools

    db = MagicMock()
    filtered = MagicMock()
    filtered.with_entities.side_effect = RuntimeError("projection failed")

    assert agent_tools._build_search_summary(db, filtered, None) == {}

