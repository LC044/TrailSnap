"""Additional nightly coverage for the photo router's filtering branches."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

import app.crud.photo
from app.api import photo as photo_api
from app.schemas.photo import BatchPhotoUpdate


pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


def _user():
    return SimpleNamespace(id=uuid4())


def test_read_all_photos_forwards_filter_groups_and_paging():
    db = MagicMock()
    user = _user()
    rows = [SimpleNamespace(id=uuid4())]

    with patch.object(app.crud.photo, "get_all_photos", return_value=rows) as crud_call:
        result = photo_api.read_all_photos(
            skip=4,
            limit=12,
            album_ids=[uuid4()],
            years=[2024, 2025],
            cities=["武汉市", "上海市"],
            file_types=["image"],
            order_by="photo_time",
            order_dir="desc",
            folder="Trips",
            folder_direct=True,
            db=db,
            current_user=user,
        )

    assert result is rows
    kwargs = crud_call.call_args.kwargs
    assert kwargs["skip"] == 4
    assert kwargs["limit"] == 12
    assert kwargs["album_ids"]
    assert kwargs["years"] == [2024, 2025]
    assert kwargs["cities"] == ["武汉市", "上海市"]
    assert kwargs["file_types"] == ["image"]
    assert kwargs["order_by"] == "photo_time"
    assert kwargs["order_dir"] == "desc"
    assert kwargs["folder"] == "Trips"
    assert kwargs["folder_direct"] is True
    assert kwargs["user_id"] == user.id


def test_read_all_photos_deduplicates_similar_results_after_query():
    db = MagicMock()
    user = _user()
    kept = uuid4()
    removed = uuid4()
    rows = [SimpleNamespace(id=kept), SimpleNamespace(id=removed)]

    with patch.object(app.crud.photo, "get_all_photos", return_value=rows), patch(
        "app.service.moment.day_highlight_service.dedup_photo_ids", return_value={kept}
    ) as dedup:
        result = photo_api.read_all_photos(
            dedup_similar=True, db=db, current_user=user
        )

    dedup.assert_called_once_with(db, user.id, [kept, removed])
    assert result == [rows[0]]


def test_batch_update_photos_rejects_unknown_action():
    payload = BatchPhotoUpdate(photo_ids=[uuid4()], action="unsupported")

    with pytest.raises(HTTPException) as exc_info:
        photo_api.batch_update_photos(
            batch_data=payload, db=MagicMock(), current_user=_user()
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Invalid action"
