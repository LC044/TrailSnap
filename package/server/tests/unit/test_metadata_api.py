"""Unit tests for the photo-metadata REST router (app/api/metadata.py).

Covers the three endpoints:

* ``GET  ""`` enriches the metadata row with file_path / albums / faces / tags.
* ``PUT  ""`` updates metadata via ``crud.photo.update_photo_metadata``
  and 404s when the helper returns ``None``.
* ``POST /batch-location`` short-circuits empty inputs and counts partial
  successes so the client can show a partial-success toast.

All DB access is mocked via ``MagicMock`` / ``patch`` so no Postgres or
vector store is required.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api import metadata as metadata_api


pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


def _user():
    return SimpleNamespace(id=uuid4())


# ----------------------------- GET metadata ------------------------------


def test_get_photo_metadata_merges_albums_faces_tags():
    photo_id = uuid4()
    db = MagicMock()
    user = _user()
    db_row = SimpleNamespace(
        exif_info=None, make=None, model=None, shooting_params=None,
        longitude=None, latitude=None, city=None, district=None,
        province=None, country=None, address=None, photo_id=uuid4(),
    )
    photo = SimpleNamespace(file_path="D:/Photos/test.jpg")
    albums = [SimpleNamespace(id=uuid4(), name="Vacation")]
    faces = [SimpleNamespace(id=uuid4(), identity_name="Alice")]
    tags = [SimpleNamespace(id=uuid4(), tag_name="beach")]

    with patch("app.api.metadata.crud_photo.get_photo_metadata", return_value=db_row) as g_meta:
        with patch("app.api.metadata.crud_photo.get_photo", return_value=photo) as g_photo:
            with patch("app.api.metadata.crud_album.get_albums_by_photo_id", return_value=albums) as g_albums:
                with patch("app.api.metadata.crud_face.get_identities_by_photo_id", return_value=faces) as g_faces:
                    with patch("app.api.metadata.crud_tag.get_photo_tags", return_value=tags) as g_tags:
                        result = metadata_api.get_photo_metadata(
                            photo_id=photo_id, db=db, current_user=user,
                        )

    g_meta.assert_called_once_with(db, photo_id=photo_id, user_id=user.id)
    g_photo.assert_called_once_with(db, photo_id=photo_id, include_deleted=True)
    g_albums.assert_called_once_with(db, photo_id=photo_id)
    g_faces.assert_called_once_with(db, photo_id=photo_id)
    g_tags.assert_called_once_with(db, photo_id=photo_id, owner_id=user.id)

    assert result.file_path == "D:/Photos/test.jpg"
    assert result.albums == albums
    assert result.faces_identities == faces
    assert result.tags == tags


def test_get_photo_metadata_404_when_row_missing():
    photo_id = uuid4()
    db = MagicMock()
    user = _user()

    with patch("app.api.metadata.crud_photo.get_photo_metadata", return_value=None):
        with pytest.raises(HTTPException) as exc_info:
            metadata_api.get_photo_metadata(photo_id=photo_id, db=db, current_user=user)

    assert exc_info.value.status_code == 404
    assert "Metadata not found" in exc_info.value.detail


# ----------------------------- PUT metadata ------------------------------


def test_update_photo_metadata_returns_wrapped_result():
    photo_id = uuid4()
    db = MagicMock()
    user = _user()
    payload = SimpleNamespace(
        longitude=121.0, latitude=31.0, city="上海",
        address="外滩", province="上海市", district=None,
        country="中国", make=None, model=None,
        shooting_params=None, exif_info=None,
    )
    fake_result = SimpleNamespace(id=photo_id, city="上海")

    with patch("app.api.metadata.crud_photo.update_photo_metadata", return_value=fake_result) as update:
        with patch("app.api.metadata.BaseResponse.success") as success:
            metadata_api.update_photo_metadata(
                photo_id=photo_id, metadata=payload, db=db, current_user=user,
            )

    update.assert_called_once_with(db, photo_id=photo_id, metadata=payload, user_id=user.id)
    success.assert_called_once()
    assert success.call_args.kwargs["data"] is fake_result


def test_update_photo_metadata_404_when_helper_returns_none():
    photo_id = uuid4()
    db = MagicMock()
    user = _user()
    payload = SimpleNamespace(
        longitude=None, latitude=None, city=None,
        address=None, province=None, district=None,
        country=None, make=None, model=None,
        shooting_params=None, exif_info=None,
    )

    with patch("app.api.metadata.crud_photo.update_photo_metadata", return_value=None):
        with pytest.raises(HTTPException) as exc_info:
            metadata_api.update_photo_metadata(
                photo_id=photo_id, metadata=payload, db=db, current_user=user,
            )

    assert exc_info.value.status_code == 404
    assert "Photo not found" in exc_info.value.detail


# --------------------------- POST batch-location -------------------------


def test_batch_update_location_400_on_empty_photo_ids():
    db = MagicMock()
    user = _user()
    payload = SimpleNamespace(
        photo_ids=[],
        latitude=10.0, longitude=20.0,
        formatted_address=None, province=None, city=None,
        district=None, country=None,
    )

    with patch("app.api.metadata.crud_photo.update_photo_metadata") as update:
        with pytest.raises(HTTPException) as exc_info:
            metadata_api.batch_update_location(
                batch_data=payload, db=db, current_user=user,
            )

    assert exc_info.value.status_code == 400
    detail = exc_info.value.detail
    assert "photo ids" in str(detail).lower() or "photo" in str(detail).lower()
    update.assert_not_called()


def test_batch_update_location_counts_only_successful_rows():
    db = MagicMock()
    user = _user()
    payload = SimpleNamespace(
        photo_ids=[uuid4(), uuid4(), uuid4()],
        latitude=31.2304, longitude=121.4737,
        formatted_address="上海市 黄浦区",
        province="上海市", city="上海市", district="黄浦区", country="中国",
    )

    def _fake_update(db_inner, photo_id, metadata, user_id):
        if str(photo_id) == str(payload.photo_ids[2]):
            return None
        return SimpleNamespace(id=photo_id)

    with patch("app.api.metadata.crud_photo.update_photo_metadata", side_effect=_fake_update) as update:
        result = metadata_api.batch_update_location(
            batch_data=payload, db=db, current_user=user,
        )

    assert update.call_count == 3
    for call in update.call_args_list:
        meta = call.kwargs["metadata"]
        assert meta.latitude == 31.2304
        assert meta.longitude == 121.4737
        assert meta.city == "上海市"
        assert meta.country == "中国"

    assert result.data["count"] == 2
    assert "Successfully updated location for 2 photos" in result.data["message"]


def test_batch_update_location_omits_unset_optional_fields():
    db = MagicMock()
    user = _user()
    payload = SimpleNamespace(
        photo_ids=[uuid4()],
        latitude=10.0, longitude=20.0,
        formatted_address=None, province=None, city=None,
        district=None, country=None,
    )
    captured = []

    def _capture(db_inner, photo_id, metadata, user_id):
        captured.append(metadata)
        return SimpleNamespace(id=photo_id)

    with patch("app.api.metadata.crud_photo.update_photo_metadata", side_effect=_capture):
        result = metadata_api.batch_update_location(
            batch_data=payload, db=db, current_user=user,
        )

    assert len(captured) == 1
    meta = captured[0]
    assert meta.latitude == 10.0
    assert meta.longitude == 20.0
    assert meta.city is None
    assert meta.province is None
    assert meta.country is None
    assert meta.address is None
    assert result.data["count"] == 1


