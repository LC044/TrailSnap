"""Focused unit coverage for API modules found by the nightly gap scan."""

from math import isclose
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.api import annual_report, auth, guess_city, location_stats, storage


pytestmark = pytest.mark.smoke


@pytest.mark.parametrize(
    ("handler", "crud_name", "dates"),
    [
        (location_stats.get_overview, "get_overview", ("2026-01-01", "2026-12-31")),
        (location_stats.get_annual_trend, "get_annual_trend", (None, None)),
        (location_stats.get_monthly_radar, "get_monthly_radar", (None, None)),
        (location_stats.get_heatmap, "get_heatmap_range", (None, None)),
    ],
)
def test_location_stats_delegates_user_and_date_filters(handler, crud_name, dates):
    db = MagicMock()
    user = SimpleNamespace(id="user-1")
    result = {"ok": True}

    with patch.object(location_stats.crud, crud_name, return_value=result) as crud_call:
        actual = handler(
            start_date=dates[0], end_date=dates[1], db=db, current_user=user
        )

    crud_call.assert_called_once_with(db, user.id, *dates)
    assert actual is result


def test_location_places_forwards_all_filters_and_limit():
    db = MagicMock()
    user = SimpleNamespace(id="user-2")

    with patch.object(location_stats.crud, "get_places", return_value={"items": []}) as get_places:
        result = location_stats.get_places(
            level="district", start_date="2026-01-01", end_date="2026-01-31",
            parent_region="湖北省", limit=5, db=db, current_user=user,
        )

    get_places.assert_called_once_with(
        db, user.id, "district", "2026-01-01", "2026-01-31", "湖北省", 5
    )
    assert result == {"items": []}


def test_haversine_distance_is_zero_for_same_point():
    assert annual_report.haversine_distance(30.5, 114.3, 30.5, 114.3) == 0


def test_haversine_distance_matches_known_city_distance():
    distance = annual_report.haversine_distance(31.2304, 121.4737, 39.9042, 116.4074)
    assert isclose(distance, 1067, rel_tol=0.02)


def test_annual_report_photos_forwards_current_user_id():
    db = MagicMock()
    user = SimpleNamespace(id="owner-9")
    start = SimpleNamespace()
    end = SimpleNamespace()

    with patch.object(
        annual_report.crud_annual_report, "get_annual_report_photos", return_value={}
    ) as get_photos:
        result = annual_report.get_annual_report_photos(start, end, db, user)

    get_photos.assert_called_once_with(start, end, db, user_id=user.id)
    assert result == {}


def test_guess_cities_serializes_coordinates_and_missing_values():
    rows = [
        SimpleNamespace(city="武汉市", avg_lat=30.59, avg_lon=114.30),
        SimpleNamespace(city="未知", avg_lat=None, avg_lon=None),
    ]
    db = MagicMock()
    db.query.return_value.filter.return_value.group_by.return_value.all.return_value = rows

    response = guess_city.get_cities(db=db)

    assert response.code == 0
    assert response.data[0] == {"city": "武汉市", "latitude": 30.59, "longitude": 114.3}
    assert response.data[1]["latitude"] == 0.0
    assert response.data[1]["longitude"] == 0.0


def test_guess_city_returns_not_found_when_photo_has_no_metadata():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    request = guess_city.GuessRequest(photo_id="missing", guess_city="武汉市")

    response = guess_city.guess_city(request, db=db)

    assert response.code == 404
    assert response.msg == "Photo or location not found"


def test_storage_folder_stats_aggregates_duplicate_folders_and_empty_path():
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [
        ("C:/photos/a.jpg", 10), ("C:/photos/b.jpg", None), (None, 5),
    ]

    response = storage.get_storage_folder_stats(
        db=db, current_user=SimpleNamespace(id="owner-1")
    )

    by_name = {item["name"]: item for item in response.data}
    assert by_name["C:/photos"] == {"name": "C:/photos", "size": 10, "count": 2}
    assert by_name["未知"] == {"name": "未知", "size": 5, "count": 1}


def test_storage_folder_stats_returns_empty_list_without_photos():
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = []

    response = storage.get_storage_folder_stats(
        db=db, current_user=SimpleNamespace(id="owner-1")
    )

    assert response.code == 0
    assert response.data == []


def test_auth_status_reports_user_presence_and_registration_flag():
    db = MagicMock()
    db.query.return_value.count.return_value = 2

    with patch.object(auth.system_config.config.security, "allow_registration", False):
        result = auth.get_auth_status(db=db)

    assert result["has_users"] is True
    assert result["allow_registration"] is False
    assert isinstance(result["demo_mode"], bool)


def test_auth_status_allows_empty_installation_state():
    db = MagicMock()
    db.query.return_value.count.return_value = 0

    result = auth.get_auth_status(db=db)

    assert result["has_users"] is False