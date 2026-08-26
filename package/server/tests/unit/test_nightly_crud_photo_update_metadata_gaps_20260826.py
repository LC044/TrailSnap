"""Round 2026-08-26 coverage gaps for app/crud/photo.py update_photo_metadata."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


def _make_photo(owner_id):
    return SimpleNamespace(id="photo-1", owner_id=owner_id)


def _make_metadata_obj():
    return SimpleNamespace(photo_id=None, exif_info=None)


def test_update_photo_metadata_updates_existing_row_and_skips_trigger_when_no_user():
    from app.crud import photo as crud

    db = MagicMock()
    existing = _make_metadata_obj()
    existing.exif_info = "old"

    update = SimpleNamespace(
        model_dump=lambda exclude_unset: {"exif_info": "new"},
    )

    with patch.object(crud, "get_photo_metadata", return_value=existing):
        result = crud.update_photo_metadata(db, "photo-1", update, user_id=None)

    assert result is existing
    assert existing.exif_info == "new"
    db.commit.assert_called_once()
    db.refresh.assert_called_once_with(existing)


def test_update_photo_metadata_returns_none_when_photo_missing():
    from app.crud import photo as crud

    db = MagicMock()

    update = SimpleNamespace(model_dump=lambda exclude_unset: {"exif_info": "x"})

    with patch.object(crud, "get_photo_metadata", return_value=None), \
         patch.object(crud, "get_photo", return_value=None):
        result = crud.update_photo_metadata(db, "missing", update, user_id="u")

    assert result is None
    db.commit.assert_not_called()


def test_update_photo_metadata_creates_new_row_when_metadata_missing():
    from app.crud import photo as crud

    db = MagicMock()
    photo_obj = _make_photo("user-x")

    update = SimpleNamespace(model_dump=lambda exclude_unset: {"exif_info": "fresh"})

    with patch.object(crud, "get_photo_metadata", return_value=None), \
         patch.object(crud, "get_photo", return_value=photo_obj), \
         patch.object(crud, "PhotoMetadata", SimpleNamespace):
        result = crud.update_photo_metadata(db, "photo-1", update, user_id=None)

    db.commit.assert_called_once()
    db.refresh.assert_called_once()
    assert result is not None


def test_update_photo_metadata_returns_none_when_user_does_not_own_photo():
    from app.crud import photo as crud

    db = MagicMock()
    photo_obj = _make_photo(owner_id="user-other")

    update = SimpleNamespace(model_dump=lambda exclude_unset: {"exif_info": "x"})

    with patch.object(crud, "get_photo_metadata", return_value=None), \
         patch.object(crud, "get_photo", return_value=photo_obj):
        result = crud.update_photo_metadata(db, "photo-1", update, user_id="user-self")

    assert result is None
    db.commit.assert_not_called()


def test_update_photo_metadata_triggers_conditional_albums_update_for_owned_photo():
    from app.crud import photo as crud

    db = MagicMock()
    existing = _make_metadata_obj()

    update = SimpleNamespace(model_dump=lambda exclude_unset: {"exif_info": "y"})

    with patch.object(crud, "get_photo_metadata", return_value=existing), \
         patch("app.crud.album.trigger_conditional_albums_update") as trigger:
        crud.update_photo_metadata(db, "photo-1", update, user_id="user-1")

    trigger.assert_called_once_with(db, "user-1", ["photo-1"])
