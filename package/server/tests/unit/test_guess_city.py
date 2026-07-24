"""Unit tests for the guess-city game REST router (app/api/guess_city.py).

Covers the three endpoints used by ``/api/games/guess-city``:

* ``GET /random`` returns a random photo id (the top city is filtered out
  and >1y-old photos are prioritised before falling back to the whole set).
* ``GET /cities`` aggregates unique cities with their averaged lat/lon.
* ``POST /guess`` validates the guess; the haversine / bearing helpers
  are only invoked when the guess is wrong AND the guessed city has coords.

DB access is mocked through ``side_effect`` chains on ``db.query`` so the
test does not require real Postgres.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.api import guess_city as guess_city_api


pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


def _photo(pid=None, photo_time=None):
    return SimpleNamespace(id=pid or uuid4(), photo_time=photo_time)


def _query_mock(*, side_returns):
    """Build a ``db.query`` callable whose first ``.all()`` / ``.first()`` returns the stub."""
    q = MagicMock()
    q.all.return_value = side_returns if isinstance(side_returns, list) else [side_returns]
    q.first.return_value = side_returns if not isinstance(side_returns, list) else (side_returns[0] if side_returns else None)
    # Filter / group_by / order_by / join all return the same mock so the chain
    # is transparent regardless of how many of them the router chains together.
    q.filter.return_value = q
    q.group_by.return_value = q
    q.order_by.return_value = q
    q.join.return_value = q
    return q


# ----------------------- GET /random -----------------------


def test_random_photo_picks_old_photo_when_old_list_nonempty():
    """``get_random_photo`` must surface a >1y-old photo from the old list."""
    old_photo = _photo(photo_time=__import__("datetime").datetime(2020, 6, 1))

    db = MagicMock()
    db.query.side_effect = [
        # First call: top_city_row lookup -> returns None -> top_city = None
        _query_mock(side_returns=None),
        # Second call: old-photos chain -> the chosen photo
        _query_mock(side_returns=old_photo),
    ]

    with patch_random_choice_first():
        response = guess_city_api.get_random_photo(db=db)

    assert response.code == 0
    assert response.data["id"] == str(old_photo.id)


def test_random_photo_404_when_no_suitable_photos():
    """Empty photo set -> 404 surfaced to the UI."""
    db = MagicMock()
    empty_mock = _query_mock(side_returns=[])
    db.query.side_effect = [
        # top city row -> None so we don't add another filter
        _query_mock(side_returns=None),
        # old-photos chain -> [] so we fall through to query.all() -> []
        empty_mock,
        empty_mock,
    ]

    response = guess_city_api.get_random_photo(db=db)
    assert response.code == 404
    assert "No suitable photos" in response.msg


# ----------------------- GET /cities -----------------------


def test_get_cities_returns_averaged_coordinates():
    db = MagicMock()
    db.query.return_value.filter.return_value.group_by.return_value.all.return_value = [
        SimpleNamespace(city="上海", avg_lat=31.2, avg_lon=121.5),
        SimpleNamespace(city="北京", avg_lat=39.9, avg_lon=116.4),
    ]

    response = guess_city_api.get_cities(db=db)
    assert response.data == [
        {"city": "上海", "latitude": 31.2, "longitude": 121.5},
        {"city": "北京", "latitude": 39.9, "longitude": 116.4},
    ]


def test_get_cities_handles_null_coords_as_zero():
    db = MagicMock()
    db.query.return_value.filter.return_value.group_by.return_value.all.return_value = [
        SimpleNamespace(city="未知", avg_lat=None, avg_lon=None),
    ]

    response = guess_city_api.get_cities(db=db)
    assert response.data == [{"city": "未知", "latitude": 0.0, "longitude": 0.0}]


# ----------------------- POST /guess -----------------------


def _metadata_row(city=None, lat=31.0, lon=121.0):
    return SimpleNamespace(photo_id=uuid4(), city=city, latitude=lat, longitude=lon)


def test_guess_correct_returns_correct_flag_without_distance():
    """Exact match: distance = 0 and direction is empty."""
    db = MagicMock()
    actual = _metadata_row(city="上海", lat=31.2, lon=121.5)
    db.query.return_value.filter.return_value.first.return_value = actual

    request = SimpleNamespace(photo_id=str(actual.photo_id), guess_city="上海")

    import app.api.guess_city as gc
    with __import__("unittest.mock").mock.patch.object(gc, "calculate_haversine_distance") as haversine:
        result = guess_city_api.guess_city(req=request, db=db)

    assert result.code == 0
    assert result.data["correct"] is True
    assert result.data["actual_city"] == "上海"
    assert result.data["distance_km"] == 0.0
    assert result.data["direction"] == ""
    haversine.assert_not_called()


def test_guess_wrong_calls_haversine_bearing_direction():
    """Wrong guess surfaces distance / bearing / direction."""
    actual = _metadata_row(city="北京", lat=39.9, lon=116.4)
    coords = SimpleNamespace(lat=31.2, lon=121.5)

    db = MagicMock()
    metadata_mock = MagicMock(); metadata_mock.filter.return_value.first.return_value = actual
    coords_mock = MagicMock(); coords_mock.filter.return_value.first.return_value = coords
    db.query.side_effect = [metadata_mock, coords_mock]

    request = SimpleNamespace(photo_id=str(actual.photo_id), guess_city="上海")

    import app.api.guess_city as gc
    with __import__("unittest.mock").mock.patch.object(gc, "calculate_haversine_distance", return_value=1067.0):
        with __import__("unittest.mock").mock.patch.object(gc, "calculate_bearing", return_value=336.0):
            with __import__("unittest.mock").mock.patch.object(gc, "get_compass_direction", return_value="NNW"):
                result = guess_city_api.guess_city(req=request, db=db)

    assert result.code == 0
    assert result.data["correct"] is False
    assert result.data["actual_city"] == "北京"
    assert result.data["distance_km"] == 1067.0
    assert result.data["bearing"] == 336.0
    assert result.data["direction"] == "NNW"


def test_guess_404_when_metadata_missing():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None

    request = SimpleNamespace(photo_id=str(uuid4()), guess_city="上海")
    result = guess_city_api.guess_city(req=request, db=db)
    assert result.code == 404
    assert "Photo or location" in result.msg


# ----------------------- helpers -----------------------


def patch_random_choice_first():
    """Context manager that makes ``random.choice`` return ``lst[0]`` deterministically."""
    import unittest.mock
    return unittest.mock.patch("app.api.guess_city.random.choice", side_effect=lambda lst: lst[0])
