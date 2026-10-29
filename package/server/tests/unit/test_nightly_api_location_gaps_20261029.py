"""2026-10-29 nightly gap tests for the location REST router (app/api/location.py).

The router layer is exercised directly with ``crud`` / ``scene_crud`` /
``footprint_crud`` patched, so no database or HTTP stack is required.

Covered gaps:
* ``GET /map-routes`` -> ValueError is converted to a 422 business failure.
* ``GET /distribution`` forwards every query argument.
* ``GET /time-compare`` and ``GET /time-compare/photos`` guard clauses
  (missing identifiers -> 422, missing rows -> HTTP 404).
* ``GET /scenes/{id}`` success branch.
* ``GET /{name}/photos`` forwards ``place_key`` only when it is a string.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api import location as location_api


pytestmark = [pytest.mark.smoke, pytest.mark.module_album]


def _user(uid=None):
    return SimpleNamespace(id=uid or uuid4())


# ----------------------- GET /map-routes -----------------------


def test_map_routes_returns_422_when_crud_rejects_range():
    """An invalid date window is reported as a business failure, not a 500."""
    user = _user()
    db = MagicMock()

    with patch.object(location_api.footprint_crud, "get_map_routes", side_effect=ValueError("开始日期不能晚于结束日期")):
        response = location_api.get_map_routes(
            start_date=None, end_date=None, max_points=300, db=db, current_user=user
        )

    assert response.code == 422
    assert "开始日期" in response.msg
    assert response.data is None


def test_map_routes_forwards_filters_to_crud():
    """The success path passes the user id and the point budget through."""
    user = _user()
    db = MagicMock()
    expected = [{"city": "杭州", "points": []}]

    with patch.object(location_api.footprint_crud, "get_map_routes", return_value=expected) as crud_call:
        response = location_api.get_map_routes(
            start_date=None, end_date=None, max_points=300, db=db, current_user=user
        )

    crud_call.assert_called_once_with(db, user.id, None, None, 300)
    assert response.code == 0
    assert response.data == expected


# ----------------------- GET /distribution -----------------------


def test_location_distribution_forwards_level_and_dates():
    """Distribution view forwards the grouping level and the date window."""
    user = _user()
    db = MagicMock()
    expected = [{"name": "杭州", "count": 3}]

    with patch.object(location_api.crud, "get_location_distribution", return_value=expected) as crud_call:
        result = location_api.get_location_distribution(
            level="province", start_date="2026-01-01", end_date="2026-02-01", db=db, current_user=user
        )

    crud_call.assert_called_once_with(db, user.id, "province", "2026-01-01", "2026-02-01")
    assert result == expected


# ----------------------- GET /time-compare -----------------------


def test_time_compare_summary_requires_scene_or_photo():
    """Without any identifier the endpoint answers 422 instead of querying."""
    response = location_api.get_time_compare_summary(
        scene_id=None, photo_id=None, db=MagicMock(), current_user=_user()
    )

    assert response.code == 422
    assert "scene_id or photo_id is required" in response.msg


def test_time_compare_summary_returns_404_when_row_missing():
    """A ``None`` result means the place could not be resolved."""
    user = _user()
    db = MagicMock()

    with patch.object(location_api.crud, "get_time_compare_summary", return_value=None):
        with pytest.raises(HTTPException) as excinfo:
            location_api.get_time_compare_summary(scene_id=uuid4(), photo_id=None, db=db, current_user=user)

    assert excinfo.value.status_code == 404


def test_time_compare_summary_returns_payload():
    """The happy path wraps the crud payload into a success envelope."""
    user = _user()
    db = MagicMock()
    payload = {"summary": "同一地点的四季"}

    with patch.object(location_api.crud, "get_time_compare_summary", return_value=payload):
        response = location_api.get_time_compare_summary(scene_id=uuid4(), photo_id=None, db=db, current_user=user)

    assert response.code == 0
    assert response.data == payload


# ----------------------- GET /time-compare/photos -----------------------


def test_time_compare_photos_requires_scene_or_photo():
    """The photos variant shares the same identifier guard."""
    response = location_api.get_time_compare_photos(
        scene_id=None,
        photo_id=None,
        reference_photo_id=None,
        year=None,
        visit_date=None,
        skip=0,
        limit=100,
        db=MagicMock(),
        current_user=_user(),
    )

    assert response.code == 422
    assert "scene_id or photo_id is required" in response.msg


def test_time_compare_photos_returns_404_when_row_missing():
    """``None`` from crud means the anchor photo does not exist."""
    user = _user()
    db = MagicMock()

    with patch.object(location_api.crud, "get_time_compare_photos", return_value=None):
        with pytest.raises(HTTPException) as excinfo:
            location_api.get_time_compare_photos(
                scene_id=None,
                photo_id=uuid4(),
                reference_photo_id=None,
                year=None,
                visit_date=None,
                skip=0,
                limit=100,
                db=db,
                current_user=user,
            )

    assert excinfo.value.status_code == 404


def test_time_compare_photos_forwards_all_arguments():
    """Every optional filter is forwarded verbatim to the crud layer."""
    user = _user()
    db = MagicMock()
    scene_id, photo_id, reference_id = uuid4(), uuid4(), uuid4()
    photos = [{"id": str(photo_id)}]

    with patch.object(location_api.crud, "get_time_compare_photos", return_value=photos) as crud_call:
        response = location_api.get_time_compare_photos(
            scene_id=scene_id,
            photo_id=photo_id,
            reference_photo_id=reference_id,
            year=2026,
            visit_date=None,
            skip=5,
            limit=20,
            db=db,
            current_user=user,
        )

    crud_call.assert_called_once_with(
        db,
        user.id,
        scene_id=scene_id,
        photo_id=photo_id,
        reference_photo_id=reference_id,
        year=2026,
        skip=5,
        limit=20,
        visit_date=None,
    )
    assert response.data == photos


# ----------------------- GET /scenes/{id} -----------------------


def test_get_scene_details_returns_scene():
    """The scene detail view wraps the crud row into a success envelope."""
    user = _user()
    db = MagicMock()
    scene_id = uuid4()
    scene = SimpleNamespace(id=str(scene_id), name="西湖")

    with patch.object(location_api.scene_crud, "get_scene", return_value=scene) as crud_call:
        response = location_api.get_scene_details(scene_id=scene_id, db=db, current_user=user)

    crud_call.assert_called_once_with(db, scene_id, owner_id=user.id)
    assert response.code == 0
    assert response.data is scene


def test_get_scene_details_returns_404_when_missing():
    """A missing (or foreign) scene is a 404."""
    user = _user()
    db = MagicMock()

    with patch.object(location_api.scene_crud, "get_scene", return_value=None):
        with pytest.raises(HTTPException) as excinfo:
            location_api.get_scene_details(scene_id=uuid4(), db=db, current_user=user)

    assert excinfo.value.status_code == 404


# ----------------------- GET /{name}/photos -----------------------


def test_location_photos_forwards_place_key_when_string():
    """``place_key`` is only forwarded when it is a real string."""
    user = _user()
    db = MagicMock()
    photos = [{"id": "p1"}]

    with patch.object(location_api.crud, "get_location_photos", return_value=photos) as crud_call:
        result = location_api.get_location_photos(
            name="杭州",
            level="city",
            scene_id=None,
            place_key="310000",
            start_date=None,
            end_date=None,
            skip=0,
            limit=50,
            db=db,
            current_user=user,
        )

    assert crud_call.call_args.kwargs == {"place_key": "310000"}
    assert result == photos


def test_location_photos_omits_place_key_when_absent():
    """Without a place key the crud call must not receive the extra kwarg."""
    user = _user()
    db = MagicMock()

    with patch.object(location_api.crud, "get_location_photos", return_value=[]) as crud_call:
        location_api.get_location_photos(
            name="杭州",
            level="city",
            scene_id=None,
            place_key=None,
            start_date=None,
            end_date=None,
            skip=0,
            limit=50,
            db=db,
            current_user=user,
        )

    assert crud_call.call_args.kwargs == {}
