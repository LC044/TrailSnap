"""Unit tests for the classification REST router (app/api/classification.py).

Covers all four endpoints with their response semantics:

- GET  /                          -- tag list with stats, wrapped in BaseResponse.
- GET  /{path:path}/photos        -- photo list for a given tag path.
- POST /{path:path}/remove-photos -- bulk-remove photos from a tag;
                                    raises HTTPException(404) when nothing was removed
                                    and otherwise triggers the conditional album updater.
- POST /{path:path}/cover         -- sets the cover photo; returns BaseResponse(code=404)
                                    when the tag or photo is missing.

We patch ``app.crud.tag`` and ``app.crud.album.trigger_conditional_albums_update``
so no real database session or album-side-effects are required.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api import classification as classification_api
from app.crud import tag as crud_tag


pytestmark = [pytest.mark.smoke, pytest.mark.module_classification]


def _user():
    return SimpleNamespace(id="owner-1")


# ------------------------------- GET / -----------------------------------


def test_get_tags_returns_wrapped_stats():
    db = MagicMock()
    user = _user()
    expected = [SimpleNamespace(tag_name="动物"), SimpleNamespace(tag_name="风景")]

    with patch.object(crud_tag, "get_tags_with_stats", return_value=expected) as get_call:
        response = classification_api.get_tags(skip=10, limit=25, db=db, current_user=user)

    get_call.assert_called_once_with(db, user.id, 10, 25)
    assert response.code == 0
    assert response.data is expected


# --------------------- GET /{path:path}/photos ----------------------------


def test_get_tag_photos_supports_multi_level_path():
    db = MagicMock()
    user = _user()
    photos = [SimpleNamespace(id=uuid4()), SimpleNamespace(id=uuid4())]

    with patch.object(crud_tag, "get_photos_by_tag_name", return_value=photos) as get_call:
        response = classification_api.get_tag_photos(
            path="动物/猫", skip=0, limit=50, db=db, current_user=user
        )

    get_call.assert_called_once_with(db, user.id, "动物/猫", 0, 50)
    assert response.data is photos


def test_get_tag_photos_empty_returns_empty_list():
    db = MagicMock()
    user = _user()

    with patch.object(crud_tag, "get_photos_by_tag_name", return_value=[]):
        response = classification_api.get_tag_photos(
            path="不存在的分类", skip=0, limit=50, db=db, current_user=user
        )

    assert response.data == []


# -------------------- POST /{path:path}/remove-photos ---------------------


def test_remove_photos_from_tag_zero_count_raises_404():
    db = MagicMock()
    user = _user()
    payload = classification_api.RemovePhotosRequest(photo_ids=[uuid4(), uuid4()])

    with patch.object(crud_tag, "remove_photos_from_tag", return_value=0) as remove_call, \
         patch("app.crud.album.trigger_conditional_albums_update") as trigger:
        with pytest.raises(HTTPException) as exc_info:
            classification_api.remove_photos_from_tag(
                payload=payload, path="动物", db=db, current_user=user
            )

    remove_call.assert_called_once_with(db, user.id, "动物", payload.photo_ids)
    assert exc_info.value.status_code == 404
    # No album refresh on the failure path.
    trigger.assert_not_called()


def test_remove_photos_from_tag_success_triggers_album_refresh():
    db = MagicMock()
    user = _user()
    payload = classification_api.RemovePhotosRequest(photo_ids=[uuid4(), uuid4()])

    with patch.object(crud_tag, "remove_photos_from_tag", return_value=2) as remove_call, \
         patch("app.crud.album.trigger_conditional_albums_update") as trigger:
        result = classification_api.remove_photos_from_tag(
            payload=payload, path="风景", db=db, current_user=user
        )

    remove_call.assert_called_once_with(db, user.id, "风景", payload.photo_ids)
    trigger.assert_called_once_with(db, user.id, payload.photo_ids)
    assert result == {"status": "success", "count": 2}


# ---------------------- POST /{path:path}/cover --------------------------


def test_set_tag_cover_missing_tag_or_photo_returns_404_response():
    db = MagicMock()
    user = _user()
    payload = classification_api.SetCoverRequest(photo_id=uuid4())

    with patch.object(crud_tag, "set_tag_cover", return_value=False) as set_call:
        response = classification_api.set_tag_cover(
            payload=payload, path="动物", db=db, current_user=user
        )

    set_call.assert_called_once_with(db, user.id, "动物", payload.photo_id)
    assert response.code == 404
    assert response.msg == "Tag or photo not found"


def test_set_tag_cover_success_returns_success_response():
    db = MagicMock()
    user = _user()
    payload = classification_api.SetCoverRequest(photo_id=uuid4())

    with patch.object(crud_tag, "set_tag_cover", return_value=True) as set_call:
        response = classification_api.set_tag_cover(
            payload=payload, path="风景", db=db, current_user=user
        )

    set_call.assert_called_once_with(db, user.id, "风景", payload.photo_id)
    assert response.code == 0
    assert response.msg == "success"
    assert response.data is None
