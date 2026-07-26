"""Unit tests for the location REST router (app/api/location.py).

Covers the search/list endpoints and the scene CRUD endpoints. ``crud``,
``scene_crud`` and the auth dependency are patched so no DB is touched.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.api import location as location_api


pytestmark = [pytest.mark.smoke, pytest.mark.module_album]


def _user(uid=None):
    return SimpleNamespace(id=uid or uuid4())


# ----------------------- GET /locations/search -----------------------


def test_search_locations_returns_crud_results():
    """``search`` simply forwards to crud.search_locations with the user's id."""
    user = _user()
    db = MagicMock()
    expected = [
        SimpleNamespace(name="Beijing", level="city", photo_count=10),
        SimpleNamespace(name="Shanghai", level="city", photo_count=8),
    ]

    with patch.object(location_api.crud, "search_locations", return_value=expected) as crud_call:
        response = location_api.search_locations(q="bei", db=db, current_user=user)

    crud_call.assert_called_once_with(db, user.id, "bei")
    assert response == expected


# ----------------------- GET /locations -----------------------


def test_get_locations_passes_query_params_through():
    """List view forwards level/dates/skip/limit plus user.id to crud."""
    user = _user()
    db = MagicMock()
    expected = [SimpleNamespace(name="Beijing", level="city", photo_count=10)]

    with patch.object(location_api.crud, "get_locations", return_value=expected) as crud_call:
        response = location_api.get_locations(
            level="province", start_date="2024-01-01", end_date="2024-12-31",
            skip=10, limit=25, db=db, current_user=user,
        )

    crud_call.assert_called_once_with(db, user.id, "province", 10, 25, "2024-01-01", "2024-12-31")
    assert response == expected


# ----------------------- GET /locations/scenes/list -----------------------


def test_get_scenes_list_wraps_in_base_response():
    """Scene list returns a BaseResponse envelope around crud results."""
    user = _user()
    db = MagicMock()
    expected = [SimpleNamespace(id=uuid4(), name="Great Wall", owner_id=user.id)]

    with patch.object(location_api.scene_crud, "get_scenes", return_value=expected) as crud_call:
        response = location_api.get_scenes_list(
            skip=0, limit=100, start_date=None, end_date=None,
            db=db, current_user=user,
        )

    crud_call.assert_called_once_with(db, 0, 100, None, None, owner_id=user.id)
    assert response.code == 0
    assert response.data == expected


# ----------------------- GET /locations/scenes/{scene_id} -----------------------


def test_get_scene_details_404_when_missing():
    """Missing scene raises HTTPException(404) and never calls the formatter."""
    user = _user()
    db = MagicMock()
    scene_id = uuid4()

    with patch.object(location_api.scene_crud, "get_scene", return_value=None):
        with pytest.raises(Exception) as exc_info:
            location_api.get_scene_details(scene_id=scene_id, db=db, current_user=user)

    # FastAPI HTTPException carries status_code on the exception itself.
    assert getattr(exc_info.value, "status_code", None) == 404


# ----------------------- DELETE /locations/scenes/{scene_id} -----------------------


def test_delete_scene_403_on_value_error():
    """``ValueError`` from crud (system scene) becomes HTTPException(403)."""
    user = _user()
    db = MagicMock()
    scene_id = uuid4()

    with patch.object(
        location_api.scene_crud,
        "delete_scene",
        side_effect=ValueError("cannot delete system scene"),
    ):
        with pytest.raises(Exception) as exc_info:
            location_api.delete_scene(scene_id=scene_id, db=db, current_user=user)

    assert getattr(exc_info.value, "status_code", None) == 403
