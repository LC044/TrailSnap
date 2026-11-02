"""Focused API coverage from the 2026-11-02 nightly gap scan.

The frontend view-gap scan was empty, so these tests target the five lowest
coverage API modules reported by pytest-cov: media, photo, settings,
train_ticket, and panorama.  External services, filesystems, and CRUD state
are mocked; each test only pins the router contract.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api import media as media_api
from app.api import panorama as panorama_api
from app.api import photo as photo_api
from app.api import settings as settings_api
from app.api import train_ticket as train_api
from app.schemas.photo import BatchPhotoTagsUpdate


pytestmark = pytest.mark.smoke


def _user(superuser=False):
    return SimpleNamespace(id=uuid4(), is_superuser=superuser)


# --------------------------- app/api/media.py ---------------------------


def test_check_live_backup_content_rejects_invalid_hash():
    payload = {"pairs": [{"key": "live-1", "image_md5": "a" * 32, "video_md5": ""}]}

    with pytest.raises(HTTPException) as exc:
        media_api.check_live_backup_content(
            payload=payload, db=MagicMock(), current_user=_user()
        )

    assert exc.value.status_code == 400
    assert exc.value.detail == "content_md5 must be a 32-character hexadecimal MD5"


def test_check_mobile_backup_assets_reports_hashes_without_keys():
    payload = {"keys": [], "hashes": ["a" * 32], "source_times": {}}
    user = _user()
    db = MagicMock()

    with patch.object(media_api, "_existing_content_hashes", return_value=["a" * 32]) as hashes:
        result = media_api.check_mobile_backup_assets(
            payload=payload, db=db, current_user=user
        )

    hashes.assert_called_once_with(db, user.id, ["a" * 32])
    assert result.code == 0
    assert result.data == {
        "existing": [],
        "complete": [],
        "live_photos": [],
        "hashes": ["a" * 32],
    }


# --------------------------- app/api/photo.py ---------------------------


def test_read_all_photos_with_detail_forwards_user_and_filters():
    user = _user()
    expected = {"items": []}
    filters = {
        "skip": 3,
        "limit": 7,
        "years": [2025, 2026],
        "cities": ["武汉"],
        "file_types": ["image"],
        "album_id": uuid4(),
        "face_ids": [uuid4()],
        "lat_min": 30.0,
        "lat_max": 31.0,
        "order_by": "photo_time",
    }

    with patch.object(photo_api.app.crud.photo, "get_all_photos", return_value=expected) as crud:
        result = photo_api.read_all_photos_with_detail(
            db=MagicMock(), current_user=user, **filters
        )

    assert result is expected
    assert crud.call_args.kwargs["user_id"] == user.id
    for key, value in filters.items():
        assert crud.call_args.kwargs[key] == value


def test_batch_update_photos_tags_skips_photos_from_other_users():
    user = _user()
    owned = SimpleNamespace(id=uuid4(), owner_id=user.id)
    foreign = SimpleNamespace(id=uuid4(), owner_id=uuid4())
    payload = BatchPhotoTagsUpdate(
        photo_ids=[owned.id, foreign.id], action="add", tags=["旅行"]
    )
    db = MagicMock()

    with patch.object(
        photo_api.app.crud.photo, "get_photo", side_effect=[owned, foreign]
    ) as get_photo, patch.object(
        photo_api.crud_tag, "add_tag_to_photo"
    ) as add_tag:
        result = photo_api.batch_update_photos_tags(
            data=payload, db=db, current_user=user
        )

    assert get_photo.call_count == 2
    add_tag.assert_called_once_with(db, owned.id, "旅行", 1.0, owner_id=user.id)
    assert result.code == 0
    assert result.data == {"message": "Successfully updated tags for 1 photos"}


# --------------------------- app/api/settings.py ---------------------------


def test_directory_candidates_allow_superuser_to_target_user():
    admin = _user(superuser=True)
    target = _user()
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = target
    candidates = [{"path": "/photos", "name": "photos"}]

    with patch.object(
        settings_api.gallery_service, "list_candidates", return_value=candidates
    ) as list_candidates:
        result = settings_api.get_directory_candidates(
            db=db, current_user=admin, user_id=str(target.id)
        )

    list_candidates.assert_called_once_with(str(target.id), db)
    assert result.code == 0
    assert result.data is candidates


def test_validate_directory_ignores_user_id_for_regular_user():
    user = _user(superuser=False)
    db = MagicMock()
    expected = {"valid": True, "path": "/photos"}

    with patch.object(
        settings_api.gallery_service, "validate_path", return_value=expected
    ) as validate:
        result = settings_api.validate_directory(
            payload={"user_id": str(uuid4()), "path": "/photos"},
            db=db,
            current_user=user,
        )

    validate.assert_called_once_with("/photos", str(user.id), db)
    assert result.code == 0
    assert result.data is expected


# --------------------------- app/api/train_ticket.py ---------------------------


@pytest.mark.asyncio
async def test_recognize_ticket_normalizes_price_from_ai_payload():
    class FakeResponse:
        status = 200

        async def json(self):
            return {
                "results": [
                    {
                        "tickets": [
                            {
                                "type": "train",
                                "train_code": "G1234",
                                "datetime": "2026年11月02日 08:30",
                                "price": "553.50元",
                            }
                        ]
                    }
                ]
            }

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        def post(self, *args, **kwargs):
            return FakeResponse()

    upload = SimpleNamespace(filename="ticket.jpg")
    upload.read = AsyncMock(return_value=b"image")
    config = MagicMock()
    config.get_user_config.return_value = SimpleNamespace(
        ai=SimpleNamespace(ai_api_url="http://ai.test")
    )

    with patch.object(train_api, "config_manager", config), patch(
        "aiohttp.ClientSession", new=FakeSession
    ):
        result = await train_api.recognize_ticket(
            file=upload, db=MagicMock(), current_user=_user()
        )

    assert result.code == 200
    assert result.data["train_code"] == "G1234"
    assert result.data["price"] == 553.50
    assert result.data["year_source"] == "explicit"


# --------------------------- app/api/panorama.py ---------------------------


@pytest.mark.parametrize(
    "projection,metadata,expected_code",
    [
        (None, None, 404),
        ("equirectangular", {"fullWidth": 9000, "fullHeight": 100}, 400),
    ],
)
def test_panorama_image_rejects_missing_or_oversized_high_quality(
    projection, metadata, expected_code
):
    photo = SimpleNamespace(panorama_projection=projection, panorama_metadata=metadata)

    with patch.object(panorama_api, "owned_photo", return_value=photo), patch.object(
        panorama_api, "derivative"
    ) as derivative:
        result = panorama_api.panorama_image(
            photo_id=uuid4(), high=True, db=MagicMock(), user=_user()
        )

    assert result.code == expected_code
    derivative.assert_not_called()

