"""Unit tests for the public ORM-bound functions in crud/location_stats.

Why this file exists:

* The nightly gap scan flagged ``app/crud/location_stats.py`` as 58.2%
  covered (56 missed lines out of 134). The pure helpers (``_haversine``,
  ``_apply_date_filter``, ``_travel_distance``) are covered in
  ``test_nightly_crud_location_stats_helpers_gaps_20260812.py``. This file
  focuses on the public surface that aggregates DB results into API
  responses: ``get_overview``, ``get_annual_trend``, ``get_monthly_radar``,
  ``get_places`` (with multiple level branches), and ``get_heatmap_range``.

We mock SQLAlchemy chain assembly with ``MagicMock`` so no Postgres is
required. Each function is exercised through its full control-flow path:
empty result set, populated result set, and the level-specific branches
in ``get_places``.
"""

from datetime import date as _date
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.crud import location_stats as crud_ls
from app.schemas.location_stats import (
    OverviewStats,
    AnnualTrendItem,
    MonthlyRadarItem,
    PlacesResponse,
    HeatmapItem,
    HeatmapRangeResponse,
)


pytestmark = [pytest.mark.smoke, pytest.mark.module_stats]


def _chained_query(*, terminal=None, all_rows=None):
    """Build a MagicMock whose every chainable call returns itself."""
    q = MagicMock(name="query")
    q.filter.return_value = q
    q.join.return_value = q
    q.outerjoin.return_value = q
    q.group_by.return_value = q
    q.order_by.return_value = q
    q.distinct.return_value = q
    q.offset.return_value = q
    q.limit.return_value = q
    q.scalar.return_value = terminal if terminal is not None else 0
    if all_rows is not None:
        q.all.return_value = all_rows
    return q


def _row(**kw):
    base = {
        "lat": 30.5,
        "lng": 114.3,
        "cnt": 1,
        "c": "Wuhan",
        "name": "Wuhan",
        "d": _date(2026, 8, 15),
        "y": 2026,
        "m": 8,
    }
    base.update(kw)
    return SimpleNamespace(**base)


# ---------------------------------------------------------------------------
# get_overview
# ---------------------------------------------------------------------------


def test_get_overview_returns_zeroed_stats_when_no_photos():
    """Empty DB -> OverviewStats with zero counts and has_location=False."""
    db = MagicMock()
    db.query.return_value = _chained_query()

    result = crud_ls.get_overview(db, owner_id="00000000-0000-0000-0000-000000000001")

    assert isinstance(result, OverviewStats)
    assert result.total_distance_km == 0
    assert result.province_count == 0
    assert result.city_count == 0
    assert result.scene_count == 0
    assert result.travel_days == 0
    assert result.farthest_place is None
    assert result.farthest_distance_km == 0
    assert result.has_location is False


def test_get_overview_with_location_picks_farthest_city():
    """When has_location>0, farthest_place is the city farthest from busiest centroid."""
    db = MagicMock()

    # has_location must be > 0 to enter the distance/farthest block.
    scalar_q = _chained_query(terminal=2)
    centroids_q = _chained_query(all_rows=[
        _row(c="Wuhan", lat=30.5, lng=114.3),
        _row(c="Beijing", lat=39.9, lng=116.4),
        _row(c="Urumqi", lat=43.8, lng=87.6),
    ])
    city_centroids = _chained_query(all_rows=[
        SimpleNamespace(c="Wuhan", lat=30.5, lng=114.3, cnt=10),
        SimpleNamespace(c="Urumqi", lat=43.8, lng=87.6, cnt=3),
    ])

    # Order: has_location (scalar), province_count, city_count, scene_count,
    # travel_days (all scalar), _day_city_centroids -> all rows, city_centroids.
    seq = [scalar_q, scalar_q, scalar_q, scalar_q, scalar_q, centroids_q, city_centroids]
    def _side_effect(*a, **kw):
        return seq.pop(0) if seq else _chained_query(terminal=0)
    db.query.side_effect = _side_effect

    result = crud_ls.get_overview(db, owner_id="00000000-0000-0000-0000-000000000001")

    assert result.has_location is True
    assert result.farthest_place == "Urumqi"
    assert result.farthest_distance_km > 2500


# ---------------------------------------------------------------------------
# get_annual_trend
# ---------------------------------------------------------------------------


def test_get_annual_trend_returns_year_and_distance():
    """Each year row yields an AnnualTrendItem with year/photo_count/distance."""
    db = MagicMock()
    year_q = _chained_query(all_rows=[
        _row(y=2024, cnt=120),
        _row(y=2025, cnt=200),
    ])
    centroids_q = _chained_query(all_rows=[])

    seq = [year_q, centroids_q]
    def _side_effect(*a, **kw):
        return seq.pop(0) if seq else _chained_query(terminal=0)
    db.query.side_effect = _side_effect

    result = crud_ls.get_annual_trend(db, owner_id="00000000-0000-0000-0000-000000000001")

    assert [item.year for item in result] == [2024, 2025]
    assert all(isinstance(item, AnnualTrendItem) for item in result)
    # Without centroids the per-year distance is 0.
    assert result[0].distance_km == 0


# ---------------------------------------------------------------------------
# get_monthly_radar
# ---------------------------------------------------------------------------


def test_get_monthly_radar_emits_all_twelve_months_with_zero_fill():
    """Months with no photos appear in the radar with count=0 and score=0."""
    db = MagicMock()
    db.query.return_value = _chained_query(all_rows=[
        _row(m=3, cnt=5),
        _row(m=7, cnt=10),
    ])

    result = crud_ls.get_monthly_radar(db, owner_id="00000000-0000-0000-0000-000000000001")

    assert len(result) == 12
    by_month = {item.month: item for item in result}
    assert by_month[1].photo_count == 0
    assert by_month[1].activity_score == 0
    assert by_month[3].photo_count == 5
    assert by_month[7].photo_count == 10
    assert by_month[7].activity_score == 100
    assert by_month[3].activity_score == 50


def test_get_monthly_radar_empty_db_returns_all_zero():
    """Empty DB -> 12 zeroed MonthlyRadarItems (max_count==0 path)."""
    db = MagicMock()
    db.query.return_value = _chained_query(all_rows=[])

    result = crud_ls.get_monthly_radar(db, owner_id="00000000-0000-0000-0000-000000000001")

    assert len(result) == 12
    assert all(item.photo_count == 0 for item in result)
    assert all(item.activity_score == 0 for item in result)


# ---------------------------------------------------------------------------
# get_places -- level branches
# ---------------------------------------------------------------------------


def _named_row(name, date_obj, cnt=1):
    return SimpleNamespace(name=name, d=date_obj, cnt=cnt)


def test_get_places_city_level_groups_by_name_and_returns_top_n():
    """city level: top_places capped by limit, revisits from visit_count>1."""
    db = MagicMock()
    db.query.return_value = _chained_query(all_rows=[
        _named_row("Wuhan", _date(2026, 8, 15), cnt=5),
        _named_row("Wuhan", _date(2026, 9, 1), cnt=2),
        _named_row("Beijing", _date(2026, 9, 10), cnt=3),
    ])

    result = crud_ls.get_places(
        db, owner_id="00000000-0000-0000-0000-000000000001", level="city", limit=5
    )

    assert isinstance(result, PlacesResponse)
    assert len(result.top_places) == 2
    assert len(result.revisits) == 1
    assert result.revisits[0].name == "Wuhan"
    assert result.revisits[0].visit_count == 2
    assert result.top_places[0].name == "Wuhan"
    assert result.top_places[0].photo_count == 7


def test_get_places_province_level_returns_response():
    """province level uses PhotoMetadata.province and skips the Scene join."""
    db = MagicMock()
    db.query.return_value = _chained_query(all_rows=[])

    result = crud_ls.get_places(
        db, owner_id="00000000-0000-0000-0000-000000000001", level="province"
    )

    assert isinstance(result, PlacesResponse)
    assert result.top_places == []
    assert result.revisits == []


def test_get_places_scene_level_joins_scene_table():
    """scene level joins Scene via PhotoMetadata.scene_id and groups by Scene.name."""
    db = MagicMock()
    db.query.return_value = _chained_query(all_rows=[
        _named_row("Bund", _date(2026, 10, 1), cnt=4),
    ])

    result = crud_ls.get_places(
        db, owner_id="00000000-0000-0000-0000-000000000001", level="scene"
    )

    assert len(result.top_places) == 1
    assert result.top_places[0].name == "Bund"
    assert result.top_places[0].level == "scene"


def test_get_places_invalid_level_falls_back_to_city():
    """Unknown level -> defaults to PhotoMetadata.city grouping."""
    db = MagicMock()
    db.query.return_value = _chained_query(all_rows=[])

    result = crud_ls.get_places(
        db, owner_id="00000000-0000-0000-0000-000000000001", level="galaxy"
    )

    assert isinstance(result, PlacesResponse)


def test_get_places_respects_limit_argument():
    """limit caps top_places length."""
    db = MagicMock()
    db.query.return_value = _chained_query(all_rows=[
        _named_row("Wuhan", _date(2026, 8, 1), cnt=10),
        _named_row("Beijing", _date(2026, 8, 2), cnt=5),
        _named_row("Shanghai", _date(2026, 8, 3), cnt=3),
    ])

    result = crud_ls.get_places(
        db,
        owner_id="00000000-0000-0000-0000-000000000001",
        level="city",
        limit=2,
    )

    assert len(result.top_places) == 2


# ---------------------------------------------------------------------------
# get_heatmap_range
# ---------------------------------------------------------------------------


def test_get_heatmap_range_sums_total_photos_and_returns_data():
    """The function iterates rows, sums total_photos, and emits HeatmapItems."""
    db = MagicMock()
    db.query.return_value = _chained_query(all_rows=[
        SimpleNamespace(d=_date(2026, 8, 15), cnt=3),
        SimpleNamespace(d=_date(2026, 8, 16), cnt=5),
        SimpleNamespace(d=_date(2026, 8, 17), cnt=2),
    ])

    result = crud_ls.get_heatmap_range(
        db, owner_id="00000000-0000-0000-0000-000000000001"
    )

    assert isinstance(result, HeatmapRangeResponse)
    assert result.total_photos == 10
    assert result.total_days == 3
    assert all(isinstance(item, HeatmapItem) for item in result.data)


def test_get_heatmap_range_empty_db_returns_zero():
    """Empty DB -> total_photos=0, total_days=0, empty data list."""
    db = MagicMock()
    db.query.return_value = _chained_query(all_rows=[])

    result = crud_ls.get_heatmap_range(
        db, owner_id="00000000-0000-0000-0000-000000000001"
    )

    assert result.total_photos == 0
    assert result.total_days == 0
    assert result.data == []
