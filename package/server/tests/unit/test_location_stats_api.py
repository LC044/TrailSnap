"""Unit tests for the location-stats REST router (app/api/location_stats.py).

All five endpoints are pure CRUD passthroughs to ``app.crud.location_stats``.
We patch the helpers at the source module (because ``location_stats.py`` does
``from app.crud import location_stats as crud``) so no Postgres / vector store
is touched.

Endpoints:
* ``GET /overview``         -- ``crud.get_overview``.
* ``GET /annual-trend``     -- ``crud.get_annual_trend``.
* ``GET /monthly-radar``    -- ``crud.get_monthly_radar``.
* ``GET /places``           -- ``crud.get_places`` (level/parent_region/limit
                               passthrough; level regex enforced by FastAPI).
* ``GET /heatmap``          -- ``crud.get_heatmap_range``.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.api import location_stats as location_stats_api
from app.crud import location_stats as crud


pytestmark = [pytest.mark.smoke, pytest.mark.module_location_stats]


def _user():
    return SimpleNamespace(id=uuid4())


# ---------------------------- /overview ----------------------------


def test_get_overview_passes_dates_and_user_id():
    db = MagicMock()
    user = _user()
    expected = SimpleNamespace(total_distance_km=12.5, province_count=2)

    with patch.object(crud, "get_overview", return_value=expected) as call:
        result = location_stats_api.get_overview(
            start_date="2024-01-01",
            end_date="2024-12-31",
            db=db,
            current_user=user,
        )

    call.assert_called_once_with(db, user.id, "2024-01-01", "2024-12-31")
    assert result is expected


def test_get_overview_optional_dates_default_to_none():
    db = MagicMock()
    user = _user()

    with patch.object(crud, "get_overview") as call:
        location_stats_api.get_overview(
            start_date=None,
            end_date=None,
            db=db,
            current_user=user,
        )

    args = call.call_args.args
    assert args[1] is user.id
    assert args[2] is None
    assert args[3] is None


# --------------------------- /annual-trend --------------------------


def test_get_annual_trend_passes_dates_and_user_id():
    db = MagicMock()
    user = _user()
    expected = [SimpleNamespace(year=2024, photo_count=10, distance_km=100.0)]

    with patch.object(crud, "get_annual_trend", return_value=expected) as call:
        result = location_stats_api.get_annual_trend(
            start_date="2024-01-01",
            end_date="2024-12-31",
            db=db,
            current_user=user,
        )

    call.assert_called_once_with(db, user.id, "2024-01-01", "2024-12-31")
    assert result is expected


# -------------------------- /monthly-radar --------------------------


def test_get_monthly_radar_passes_dates_and_user_id():
    db = MagicMock()
    user = _user()
    expected = [SimpleNamespace(month=1, photo_count=3, activity_score=80)]

    with patch.object(crud, "get_monthly_radar", return_value=expected) as call:
        result = location_stats_api.get_monthly_radar(
            start_date=None,
            end_date=None,
            db=db,
            current_user=user,
        )

    call.assert_called_once_with(db, user.id, None, None)
    assert result is expected


# ----------------------------- /places ------------------------------


def test_get_places_default_level_city_and_limit_10():
    db = MagicMock()
    user = _user()
    expected = SimpleNamespace(top_places=[], revisits=[])

    with patch.object(crud, "get_places", return_value=expected) as call:
        result = location_stats_api.get_places(
            level="city",
            start_date=None,
            end_date=None,
            parent_region=None,
            limit=10,
            db=db,
            current_user=user,
        )

    call.assert_called_once_with(db, user.id, "city", None, None, None, 10)
    assert result is expected


def test_get_places_passes_scene_level_with_parent_region():
    db = MagicMock()
    user = _user()
    expected = SimpleNamespace(
        top_places=[SimpleNamespace(name="\u5916\u6ee9", level="scene")],
        revisits=[],
    )

    with patch.object(crud, "get_places", return_value=expected) as call:
        result = location_stats_api.get_places(
            level="scene",
            start_date="2025-05-01",
            end_date="2025-05-31",
            parent_region="\u4e0a\u6d77\u5e02",
            limit=25,
            db=db,
            current_user=user,
        )

    call.assert_called_once_with(
        db, user.id, "scene", "2025-05-01", "2025-05-31", "\u4e0a\u6d77\u5e02", 25,
    )
    assert len(result.top_places) == 1


# ---------------------------- /heatmap ------------------------------


def test_get_heatmap_passes_dates_and_user_id():
    db = MagicMock()
    user = _user()
    expected = SimpleNamespace(total_photos=8, total_days=4, data=[])

    with patch.object(crud, "get_heatmap_range", return_value=expected) as call:
        result = location_stats_api.get_heatmap(
            start_date="2024-06-01",
            end_date="2024-06-30",
            db=db,
            current_user=user,
        )

    call.assert_called_once_with(db, user.id, "2024-06-01", "2024-06-30")
    assert result is expected
