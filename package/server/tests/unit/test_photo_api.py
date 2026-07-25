"""Unit tests for the photo REST router (app/api/photo.py).

Coverage targets are the CRUD wrappers / simple endpoints that have no
external dependencies:

* GET    /recycle-bin                       -> crud.get_recycle_bin_photos
* POST   /recycle-bin/restore               -> crud.restore_photos
* DELETE /recycle-bin/permanent             -> crud.batch_delete_photos_db
* GET    /random                            -> crud.get_random_photos
* GET    /on-this-day                       -> crud.get_on_this_day_photos
                                               + DEMO_MODE fallback to random

Scenarios:
* recycle-bin list passes user_id / skip / limit to the CRUD layer
* restore rejects empty photo_ids with 400
* restore succeeds when the CRUD returns the count
* permanent delete rejects empty photo_ids with 400
* permanent delete passes is_delete_file=True to the CRUD
* random returns the CRUD list wrapped in a BaseResponse
* on-this-day uses the explicit month/day/year without consulting datetime.now
* on-this-day falls back to today when only limit is provided
* on-this-day in DEMO_MODE pads short lists with random photos (no duplicates)
* on-this-day in non-DEMO_MODE never calls the random fallback
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

import app.crud.photo
from app.api import photo as photo_api
from app.schemas.photo import BatchPhotoDelete


pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


def _user(uid=None):
    return SimpleNamespace(id=uid or uuid4())


# ----------------------- GET /recycle-bin -----------------------


def test_get_recycle_bin_passes_user_and_paging():
    db = MagicMock()
    user = _user()
    rows = [SimpleNamespace(id=str(uuid4()))]

    with patch.object(
        app.crud.photo, "get_recycle_bin_photos", return_value=rows
    ) as crud_call:
        response = photo_api.get_recycle_bin(skip=5, limit=25, db=db, current_user=user)

    crud_call.assert_called_once_with(db, user_id=user.id, skip=5, limit=25)
    assert response.code == 0
    assert response.data is rows


def test_get_recycle_bin_default_paging():
    db = MagicMock()
    user = _user()

    with patch.object(
        app.crud.photo, "get_recycle_bin_photos", return_value=[]
    ) as crud_call:
        photo_api.get_recycle_bin(db=db, current_user=user)

    crud_call.assert_called_once_with(db, user_id=user.id, skip=0, limit=100)


# ----------------------- POST /recycle-bin/restore -----------------------


def test_restore_rejects_empty_photo_ids():
    db = MagicMock()
    user = _user()
    payload = BatchPhotoDelete(photo_ids=[])

    with pytest.raises(HTTPException) as exc_info:
        photo_api.restore_recycle_bin_photos(batch_data=payload, db=db, current_user=user)

    assert exc_info.value.status_code == 400


def test_restore_returns_count_on_success():
    db = MagicMock()
    user = _user()
    photo_ids = [uuid4(), uuid4()]
    payload = BatchPhotoDelete(photo_ids=photo_ids)

    with patch.object(app.crud.photo, "restore_photos", return_value=3) as crud_call:
        response = photo_api.restore_recycle_bin_photos(
            batch_data=payload, db=db, current_user=user
        )

    crud_call.assert_called_once()
    args = crud_call.call_args.args
    assert args[0] is db
    assert list(args[1]) == photo_ids
    assert crud_call.call_args.kwargs["user_id"] == user.id
    assert response.code == 0
    assert "3" in response.data["message"]


# ----------------------- DELETE /recycle-bin/permanent -----------------------


def test_permanent_delete_rejects_empty_photo_ids():
    db = MagicMock()
    user = _user()
    payload = BatchPhotoDelete(photo_ids=[])

    with pytest.raises(HTTPException) as exc_info:
        photo_api.permanently_delete_recycle_bin_photos(
            batch_data=payload, db=db, current_user=user
        )

    assert exc_info.value.status_code == 400


def test_permanent_delete_passes_is_delete_file_true():
    db = MagicMock()
    user = _user()
    photo_ids = [uuid4()]
    payload = BatchPhotoDelete(photo_ids=photo_ids)

    with patch.object(
        app.crud.photo, "batch_delete_photos_db", return_value=1
    ) as crud_call:
        response = photo_api.permanently_delete_recycle_bin_photos(
            batch_data=payload, db=db, current_user=user
        )

    crud_call.assert_called_once_with(
        db, list(photo_ids), is_delete_file=True, user_id=user.id
    )
    assert response.code == 0
    assert "1" in response.data["message"]


# ----------------------- GET /random -----------------------


def test_get_random_photos_returns_crud_payload_wrapped():
    db = MagicMock()
    user = _user()
    photos = [SimpleNamespace(id=str(uuid4()))]

    with patch.object(app.crud.photo, "get_random_photos", return_value=photos) as crud_call:
        response = photo_api.get_random_photos(limit=7, db=db, current_user=user)

    crud_call.assert_called_once_with(db, user_id=user.id, limit=7)
    assert response.code == 0
    assert response.data is photos


# ----------------------- GET /on-this-day -----------------------


def test_on_this_day_uses_explicit_dates():
    db = MagicMock()
    user = _user()
    rows = [SimpleNamespace(id=str(uuid4()))]

    with patch.object(
        app.crud.photo, "get_on_this_day_photos", return_value=rows
    ) as crud_call:
        result = photo_api.get_on_this_day_photos(
            month=8, day=15, year=2024, limit=12, db=db, current_user=user
        )

    crud_call.assert_called_once_with(
        db, user_id=user.id, month=8, day=15, year=2024, limit=12
    )
    assert result is rows


def test_on_this_day_defaults_to_today(monkeypatch):
    db = MagicMock()
    user = _user()

    fake_now = MagicMock()
    fake_now.month = 3
    fake_now.day = 7
    fake_now.year = 2026
    monkeypatch.setattr(photo_api, "datetime", MagicMock(now=lambda: fake_now))

    with patch.object(
        app.crud.photo, "get_on_this_day_photos", return_value=[]
    ) as crud_call:
        photo_api.get_on_this_day_photos(db=db, current_user=user, limit=10)

    crud_call.assert_called_once_with(
        db, user_id=user.id, month=3, day=7, year=2026, limit=10
    )


def test_on_this_day_demo_mode_pads_with_random_no_duplicates(monkeypatch):
    db = MagicMock()
    user = _user()
    existing_id = uuid4()
    extra_id = uuid4()
    dup_id = existing_id  # already-excluded
    other_id = uuid4()
    photos_from_day = [SimpleNamespace(id=existing_id)]
    random_pool = [
        SimpleNamespace(id=existing_id),  # dup, must skip
        SimpleNamespace(id=extra_id),
        SimpleNamespace(id=dup_id),        # dup again
        SimpleNamespace(id=other_id),
    ]

    monkeypatch.setattr("app.middleware.demo_mode.DEMO_MODE", True)

    with patch.object(
        app.crud.photo, "get_on_this_day_photos", return_value=photos_from_day
    ), patch.object(
        app.crud.photo, "get_random_photos", return_value=random_pool
    ) as random_call:
        result = photo_api.get_on_this_day_photos(
            month=5, day=20, year=2025, limit=3, db=db, current_user=user
        )

    random_call.assert_called_once()
    assert random_call.call_args.kwargs["limit"] >= 5  # need=2 + 10 buffer = 12
    ids = [p.id for p in result]
    # existing_id is preserved, and we padded 2 distinct new photos (no duplicates)
    assert ids[0] == existing_id
    assert len(ids) == 3
    assert len(set(ids)) == 3


def test_on_this_day_non_demo_mode_does_not_pad(monkeypatch):
    db = MagicMock()
    user = _user()
    photos_from_day = [SimpleNamespace(id=uuid4())]

    monkeypatch.setattr("app.middleware.demo_mode.DEMO_MODE", False)

    with patch.object(
        app.crud.photo, "get_on_this_day_photos", return_value=photos_from_day
    ), patch.object(
        app.crud.photo, "get_random_photos"
    ) as random_call:
        result = photo_api.get_on_this_day_photos(
            month=5, day=20, year=2025, limit=3, db=db, current_user=user
        )

    random_call.assert_not_called()
    assert result is photos_from_day
