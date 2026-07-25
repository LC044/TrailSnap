"""Unit tests for the dashboard/stats REST router (app/api/stats.py).

Five thin handlers all delegate to ``app.crud.photo`` / ``app.crud.dashboard``:

* ``GET /timeline``       -- delegates to ``app.crud.photo.get_timeline_stats``;
                            resolves ``folder_roots`` only when ``folder_direct=True``
                            AND ``folder`` is empty/whitespace.
* ``GET /dashboard``      -- ``crud_dashboard.get_dashboard_stats``.
* ``GET /heatmap``        -- ``crud_dashboard.get_heatmap_stats`` (year passthrough).
* ``GET /emotion-calendar`` -- ``crud_dashboard.get_emotion_calendar_stats`` (year passthrough).
* ``GET /filters``        -- ``app.crud.photo.get_filter_options``.

DB access and helper functions are patched at the source module (so the lazy
imports inside ``stats.py`` resolve to our mock) and no Postgres connection
is established.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.api import stats as stats_api
from app.crud import dashboard as crud_dashboard
import app.crud.photo as crud_photo_mod


pytestmark = [pytest.mark.smoke, pytest.mark.module_stats]


def _user():
    return SimpleNamespace(id=uuid4())


# --------------------------- GET /timeline ---------------------------


def test_get_timeline_stats_passes_filters_and_user_id():
    db = MagicMock()
    user = _user()
    expected = SimpleNamespace(total_photos=12, timeline=[])

    with patch.object(crud_photo_mod, "get_timeline_stats", return_value=expected) as call:
        result = stats_api.get_timeline_stats(
            album_id=None,
            years=[2024, 2025],
            cities=["\u4e0a\u6d77"],
            makes=None,
            models=None,
            image_types=None,
            file_types=None,
            folder=None,
            folder_direct=False,
            db=db,
            current_user=user,
        )

    call.assert_called_once()
    args = call.call_args.args
    kwargs = call.call_args.kwargs
    assert args[0] is db
    assert kwargs["album_id"] is None
    assert kwargs["years"] == [2024, 2025]
    assert kwargs["cities"] == ["\u4e0a\u6d77"]
    assert kwargs["folder"] is None
    assert kwargs["folder_direct"] is False
    assert kwargs["folder_roots"] is None
    assert kwargs["user_id"] is user.id
    assert result is expected


def test_get_timeline_stats_resolves_folder_roots_when_folder_direct_and_blank_folder():
    db = MagicMock()
    user = _user()
    fake_roots = ["/Photos/A", "/Photos/B"]

    with patch("app.utils.path.get_user_roots", return_value=fake_roots) as roots:
        with patch.object(crud_photo_mod, "get_timeline_stats", return_value=SimpleNamespace()) as call:
            stats_api.get_timeline_stats(
                album_id=None, years=None, cities=None,
                makes=None, models=None, image_types=None, file_types=None,
                folder="   ",
                folder_direct=True,
                db=db,
                current_user=user,
            )

    roots.assert_called_once_with(user.id, db)
    assert call.call_args.kwargs["folder_roots"] == fake_roots


def test_get_timeline_stats_does_not_resolve_folder_roots_when_folder_is_provided():
    db = MagicMock()
    user = _user()

    with patch("app.utils.path.get_user_roots") as roots:
        with patch.object(crud_photo_mod, "get_timeline_stats", return_value=SimpleNamespace()):
            stats_api.get_timeline_stats(
                album_id=None, years=None, cities=None,
                makes=None, models=None, image_types=None, file_types=None,
                folder="Photos/2024",
                folder_direct=True,
                db=db,
                current_user=user,
            )

    roots.assert_not_called()


# ---------------------------- GET /dashboard --------------------------


def test_get_dashboard_overview_delegates_with_owner_id():
    db = MagicMock()
    user = _user()
    expected = SimpleNamespace(card=SimpleNamespace(total_media=10))

    with patch.object(crud_dashboard, "get_dashboard_stats", return_value=expected) as call:
        result = stats_api.get_dashboard_overview(db=db, current_user=user)

    call.assert_called_once_with(db, owner_id=user.id)
    assert result is expected


# ---------------------------- GET /heatmap ----------------------------


def test_get_heatmap_stats_passes_year_and_owner_id():
    db = MagicMock()
    user = _user()
    expected = SimpleNamespace(total_photos=42, available_years=[2024, 2025])

    with patch.object(crud_dashboard, "get_heatmap_stats", return_value=expected) as call:
        result = stats_api.get_heatmap_stats(year=2025, db=db, current_user=user)

    call.assert_called_once_with(db, owner_id=user.id, year=2025)
    assert result is expected


def test_get_heatmap_stats_year_none_is_passed_through():
    db = MagicMock()
    user = _user()

    with patch.object(crud_dashboard, "get_heatmap_stats") as call:
        stats_api.get_heatmap_stats(year=None, db=db, current_user=user)

    assert call.call_args.kwargs["year"] is None


# ----------------------- GET /emotion-calendar -----------------------


def test_get_emotion_calendar_passes_year_and_owner_id():
    db = MagicMock()
    user = _user()
    expected = SimpleNamespace(total_photos=99, data=[])

    with patch.object(crud_dashboard, "get_emotion_calendar_stats", return_value=expected) as call:
        result = stats_api.get_emotion_calendar(year=2024, db=db, current_user=user)

    call.assert_called_once_with(db, owner_id=user.id, year=2024)
    assert result is expected


# ----------------------------- GET /filters ---------------------------


def test_get_filter_options_delegates_with_user_id():
    db = MagicMock()
    user = _user()
    expected = SimpleNamespace(years=[2024], cities=["\u4e0a\u6d77"], makes=[], models=[], image_types=[], file_types=[])

    with patch.object(crud_photo_mod, "get_filter_options", return_value=expected) as call:
        result = stats_api.get_filter_options(db=db, current_user=user)

    call.assert_called_once_with(db, user_id=user.id)
    assert result is expected
