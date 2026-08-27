"""Unit tests covering 2026-08-24 nightly coverage gap scan.

Targets `app/api/photo.py` endpoints with the largest uncovered branches
that the older `test_nightly_photo_api_gaps.py` round (only 3 cases) did
not exercise:
* batch_download_photos -- empty photo_ids 400, photos missing 404,
  happy zip with case-folded dedup
* batch_create_photos -- happy delegation, exception -> 500
* batch_update_photos_data -- with/without description branch
* batch_update_photos_tags -- add vs remove branches
* batch_transfer_photos -- target outside allowed 403, move, copy
* update_photo -- not-found 404 + happy
* delete_photo_global -- delegation + include_deleted fetch
* recycle-bin endpoints: empty 400 + happy delegation
* get_photo_tags / add_photo_tag / delete_photo_tag (404, 403)
* get_photo_description (None + 403 ownership + happy)
* get_random_photos / get_on_this_day_photos (default + custom)
* replace_photo_file (404 / 403 / happy)

MagicMock-based: avoids SQLite pollution (memory 2026-08-19). Side-effect
helpers (TaskManager, config_manager, storage) are patched at their
source module because api/photo imports them lazily inside functions.
"""
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api import photo as photo_api
from app.dependencies import BaseResponse
from app.schemas.photo import (
    BatchDownloadRequest,
    BatchPhotoCreate,
    BatchPhotoDataUpdate,
    BatchPhotoDelete,
    BatchPhotoTagsUpdate,
    BatchPhotoTransfer,
    BatchPhotoUpdate,
    PhotoCreate,
    PhotoCreateItem,
    PhotoUpdate,
)
from app.db.models.photo import FileType


pytestmark = [pytest.mark.smoke]


def _user():
    return SimpleNamespace(id=uuid4())
# batch_download_photos
def test_batch_download_rejects_empty_photo_ids():
    db = MagicMock()
    req = BatchDownloadRequest(photo_ids=[])
    with pytest.raises(HTTPException) as exc:
        photo_api.batch_download_photos(req=req, db=db, current_user=_user())
    assert exc.value.status_code == 400


def test_batch_download_returns_404_when_no_photos_found():
    db = MagicMock()
    req = BatchDownloadRequest(photo_ids=[uuid4(), uuid4()])
    with patch.object(
        photo_api.app.crud.photo, "get_photos_by_ids", return_value=[]
    ) as get_photos:
        with pytest.raises(HTTPException) as exc:
            photo_api.batch_download_photos(req=req, db=db, current_user=_user())
    assert exc.value.status_code == 404
    get_photos.assert_called_once()


def test_batch_download_writes_zip_with_casefolded_dedup(tmp_path):
    db = MagicMock()
    a_path = tmp_path / "photo_a.jpg"
    a_path.write_bytes(b"a")
    b_path = tmp_path / "photo_b.JPG"  # case-folded dedup candidate
    b_path.write_bytes(b"b")

    photos = [
        SimpleNamespace(id=uuid4(), file_path=str(a_path), filename="photo_a.jpg"),
        SimpleNamespace(id=uuid4(), file_path=str(b_path), filename="photo_b.JPG"),
    ]
    req = BatchDownloadRequest(photo_ids=[p.id for p in photos])

    with patch.object(
        photo_api.app.crud.photo, "get_photos_by_ids", return_value=photos
    ):
        resp = photo_api.batch_download_photos(req=req, db=db, current_user=_user())

    assert hasattr(resp, "path")
    assert resp.background is not None
    assert resp.media_type == "application/zip"
    assert resp.filename == "trailsnap_export.zip"

    import zipfile

    with zipfile.ZipFile(resp.path) as zf:
        names = sorted(zf.namelist())
    assert names[0] == "photo_a.jpg"
    assert names[1].startswith("photo_b")
# batch_create_photos
def _photo_create_item(filename):
    return PhotoCreateItem(
        photo=PhotoCreate(
            filename=filename,
            file_type=FileType.image,
            size=10,
            width=10,
            height=10,
            duration=0.0,
        ),
        file_path="/data/" + filename,
        photo_id=uuid4(),
    )


def __photo_for_item(filename):
    from app.schemas.photo import PhotoBase

    return PhotoBase(
        filename=filename,
        file_type="image",
        size=10,
        width=10,
        height=10,
        duration=0.0,
    )


def test_batch_create_photos_delegates_to_crud():
    db = MagicMock()
    items = [_photo_create_item("a.jpg")]
    payload = BatchPhotoCreate(items=items)

    with patch.object(
        photo_api.app.crud.photo,
        "batch_create_photos",
        return_value=[items[0].photo_id],
    ) as crud_call:
        result = photo_api.batch_create_photos(
            batch_data=payload, db=db, current_user=_user()
        )

    crud_call.assert_called_once()
    passed = crud_call.call_args.args[1]
    assert len(passed) == 1
    assert passed[0]["file_path"] == "/data/a.jpg"
    assert result.code == 0
    assert "Successfully created 1" in result.data["message"]


def test_batch_create_photos_returns_500_on_exception():
    db = MagicMock()
    items = [_photo_create_item("a.jpg")]
    payload = BatchPhotoCreate(items=items)

    with patch.object(
        photo_api.app.crud.photo,
        "batch_create_photos",
        side_effect=RuntimeError("boom"),
    ):
        with pytest.raises(HTTPException) as exc:
            photo_api.batch_create_photos(
                batch_data=payload, db=db, current_user=_user()
            )
    assert exc.value.status_code == 500
    assert "boom" in exc.value.detail
# batch_update_photos_data
def test_batch_update_data_updates_photo_time_only():
    db = MagicMock()
    pid = uuid4()
    payload = BatchPhotoDataUpdate(photo_ids=[pid], photo_time=datetime(2026, 8, 24))

    with patch.object(
        photo_api.app.crud.photo, "update_photo", return_value=SimpleNamespace(id=pid)
    ):
        result = photo_api.batch_update_photos_data(
            data=payload, db=db, current_user=_user()
        )

    assert result.code == 0
    assert "Successfully updated 1" in result.data["message"]


def test_batch_update_data_creates_image_description_when_missing():
    db = MagicMock()
    pid = uuid4()
    payload = BatchPhotoDataUpdate(
        photo_ids=[pid], description="new description text"
    )

    chain = db.query.return_value
    chain.filter.return_value.first.return_value = None  # no existing row

    with patch.object(
        photo_api.app.crud.photo, "update_photo", return_value=SimpleNamespace(id=pid)
    ):
        result = photo_api.batch_update_photos_data(
            data=payload, db=db, current_user=_user()
        )

    assert result.code == 0
    db.add.assert_called_once()
    added = db.add.call_args.args[0]
    assert added.photo_id == pid
    assert added.description == "new description text"
    db.commit.assert_called()


def test_batch_update_data_updates_existing_image_description():
    db = MagicMock()
    pid = uuid4()
    existing_desc = SimpleNamespace(photo_id=pid, description="old")
    payload = BatchPhotoDataUpdate(
        photo_ids=[pid], description="updated text"
    )

    chain = db.query.return_value
    chain.filter.return_value.first.return_value = existing_desc

    with patch.object(
        photo_api.app.crud.photo, "update_photo", return_value=SimpleNamespace(id=pid)
    ):
        photo_api.batch_update_photos_data(data=payload, db=db, current_user=_user())

    assert existing_desc.description == "updated text"
    db.add.assert_not_called()
# batch_update_photos_tags
def test_batch_update_tags_add_calls_crud_tag_add():
    db = MagicMock()
    pid = uuid4()
    payload = BatchPhotoTagsUpdate(
        photo_ids=[pid], action="add", tags=["trip", "beach"]
    )
    photo = SimpleNamespace(id=pid, owner_id=uuid4())
    user = SimpleNamespace(id=photo.owner_id)

    with patch.object(
        photo_api.app.crud.photo, "get_photo", return_value=photo
    ), patch.object(
        photo_api.crud_tag, "add_tag_to_photo"
    ) as add_call:
        result = photo_api.batch_update_photos_tags(
            data=payload, db=db, current_user=user
        )

    assert result.code == 0
    assert add_call.call_count == 2  # one per tag


def test_batch_update_tags_remove_uses_tag_id_lookup():
    db = MagicMock()
    pid = uuid4()
    tag_id = uuid4()
    payload = BatchPhotoTagsUpdate(
        photo_ids=[pid], action="remove", tags=["trip"]
    )
    photo = SimpleNamespace(id=pid, owner_id=uuid4())
    user = SimpleNamespace(id=photo.owner_id)

    with patch.object(
        photo_api.app.crud.photo, "get_photo", return_value=photo
    ), patch.object(
        photo_api.crud_tag, "get_tag_by_name", return_value=SimpleNamespace(id=tag_id)
    ) as lookup, patch.object(
        photo_api.crud_tag, "remove_tag_from_photo"
    ) as remove_call:
        photo_api.batch_update_photos_tags(data=payload, db=db, current_user=user)

    lookup.assert_called_once_with(db, "trip")
    remove_call.assert_called_once_with(db, pid, tag_id)


def test_batch_update_tags_skips_photos_not_owned_by_user():
    db = MagicMock()
    pid = uuid4()
    payload = BatchPhotoTagsUpdate(photo_ids=[pid], action="add", tags=["trip"])
    photo = SimpleNamespace(id=pid, owner_id=uuid4())  # different owner
    user = SimpleNamespace(id=uuid4())

    with patch.object(
        photo_api.app.crud.photo, "get_photo", return_value=photo
    ), patch.object(
        photo_api.crud_tag, "add_tag_to_photo"
    ) as add_call:
        photo_api.batch_update_photos_tags(data=payload, db=db, current_user=user)

    add_call.assert_not_called()
# batch_transfer_photos
def _user_config(primary, external=None):
    return SimpleNamespace(
        storage=SimpleNamespace(
            photo_storage_path=primary, external_directories=external or []
        )
    )


def test_batch_transfer_rejects_target_outside_allowed_roots(tmp_path):
    db = MagicMock()
    user = _user()
    primary = tmp_path / "primary"
    primary.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()

    cfg = _user_config(str(primary))
    payload = BatchPhotoTransfer(
        photo_ids=[uuid4()], target_path=str(outside), action="move"
    )

    with patch.object(photo_api.config_manager, "get_user_config", return_value=cfg):
        with pytest.raises(HTTPException) as exc:
            photo_api.batch_transfer_photos(data=payload, db=db, current_user=user)
    assert exc.value.status_code == 403


def test_batch_transfer_move_relocates_file_and_updates_path(tmp_path):
    db = MagicMock()
    user = _user()
    user_root = tmp_path / "primary" / "users" / str(user.id)
    primary = user_root / "uploads"
    primary.mkdir(parents=True)
    target = primary / "sub"
    target.mkdir()
    old = primary / "old.jpg"
    old.write_bytes(b"x")

    cfg = _user_config(str(primary))
    pid = uuid4()
    photo = SimpleNamespace(
        id=pid, file_path=str(old), filename="old.jpg",
        __table__=SimpleNamespace(columns=[]),
    )
    payload = BatchPhotoTransfer(
        photo_ids=[pid], target_path=str(target), action="move"
    )

    with patch.object(photo_api.config_manager, "get_user_config", return_value=cfg), \
         patch.object(photo_api.storage, "_get_storage_root", return_value=str(user_root)), \
         patch.object(
             photo_api.app.crud.photo, "get_photos_by_ids", return_value=[photo]
         ):
        result = photo_api.batch_transfer_photos(
            data=payload, db=db, current_user=user
        )

    assert result.code == 0
    assert not old.exists()
    assert (target / "old.jpg").exists()
    assert photo.file_path == str(target / "old.jpg")
    assert photo.filename == "old.jpg"
    db.commit.assert_called()


def test_batch_transfer_copy_creates_new_record_and_task(tmp_path):
    db = MagicMock()
    user = _user()
    user_root = tmp_path / "primary" / "users" / str(user.id)
    primary = user_root / "uploads"
    primary.mkdir(parents=True)
    target = primary / "sub"
    target.mkdir()
    old = primary / "old.jpg"
    old.write_bytes(b"x")

    cfg = _user_config(str(primary))
    pid = uuid4()
    photo = SimpleNamespace(
        id=pid, file_path=str(old), filename="old.jpg", owner_id=user.id,
        size=1, width=1, height=1,
        __table__=SimpleNamespace(columns=[]),
    )
    payload = BatchPhotoTransfer(
        photo_ids=[pid], target_path=str(target), action="copy"
    )

    fake_mgr = MagicMock()
    fake_mgr.get_instance.return_value = fake_mgr

    with patch.object(photo_api.config_manager, "get_user_config", return_value=cfg), \
         patch.object(photo_api.storage, "_get_storage_root", return_value=str(user_root)), \
         patch.object(
             photo_api.app.crud.photo, "get_photos_by_ids", return_value=[photo]
         ), patch.object(photo_api, "TaskManager", fake_mgr):
        result = photo_api.batch_transfer_photos(
            data=payload, db=db, current_user=user
        )

    assert result.code == 0
    assert (target / "old.jpg").exists()
    db.add.assert_called_once()
    added = db.add.call_args.args[0]
    assert added.id != pid
    assert added.file_path == str(target / "old.jpg")
    fake_mgr.add_task.assert_called_once()
# update_photo / delete_photo_global
def test_update_photo_raises_404_when_crud_returns_none():
    db = MagicMock()
    pid = uuid4()
    with patch.object(
        photo_api.app.crud.photo, "update_photo", return_value=None
    ):
        with pytest.raises(HTTPException) as exc:
            photo_api.update_photo(
                photo_id=pid, photo=PhotoUpdate(), db=db, current_user=_user()
            )
    assert exc.value.status_code == 404


def test_update_photo_returns_wrapped_response_on_success():
    db = MagicMock()
    pid = uuid4()
    db_photo = SimpleNamespace(id=pid, filename="x.jpg")
    with patch.object(
        photo_api.app.crud.photo, "update_photo", return_value=db_photo
    ):
        result = photo_api.update_photo(
            photo_id=pid, photo=PhotoUpdate(filename="y.jpg"),
            db=db, current_user=_user(),
        )
    assert result.code == 0
    assert result.data is db_photo


def test_delete_photo_global_soft_deletes_then_returns_row():
    db = MagicMock()
    pid = uuid4()
    user = _user()
    db_photo = SimpleNamespace(id=pid, filename="x.jpg")
    with patch.object(
        photo_api.app.crud.photo, "batch_soft_delete_photos"
    ) as soft, patch.object(
        photo_api.app.crud.photo, "get_photo", return_value=db_photo
    ) as get:
        result = photo_api.delete_photo_global(
            photo_id=pid, db=db, current_user=user
        )
    soft.assert_called_once_with(db, [pid], user_id=user.id)
    get.assert_called_once_with(db, pid, include_deleted=True)
    assert result.data is db_photo
# recycle-bin + batch_delete_photos
def test_get_recycle_bin_delegates_with_paging():
    db = MagicMock()
    user = _user()
    expected = [SimpleNamespace(id=uuid4())]
    with patch.object(
        photo_api.app.crud.photo, "get_recycle_bin_photos", return_value=expected
    ) as crud_call:
        result = photo_api.get_recycle_bin(
            skip=5, limit=20, db=db, current_user=user
        )
    crud_call.assert_called_once_with(db, user_id=user.id, skip=5, limit=20)
    assert result.code == 0
    assert result.data is expected


def test_restore_recycle_bin_rejects_empty_ids():
    db = MagicMock()
    payload = BatchPhotoDelete(photo_ids=[])
    with pytest.raises(HTTPException) as exc:
        photo_api.restore_recycle_bin_photos(
            batch_data=payload, db=db, current_user=_user()
        )
    assert exc.value.status_code == 400


def test_restore_recycle_bin_delegates_on_success():
    db = MagicMock()
    payload = BatchPhotoDelete(photo_ids=[uuid4(), uuid4()])
    with patch.object(
        photo_api.app.crud.photo, "restore_photos", return_value=2
    ):
        result = photo_api.restore_recycle_bin_photos(
            batch_data=payload, db=db, current_user=_user()
        )
    assert "Successfully restored 2" in result.data["message"]


def test_permanently_delete_recycle_bin_rejects_empty_ids():
    db = MagicMock()
    payload = BatchPhotoDelete(photo_ids=[])
    with pytest.raises(HTTPException) as exc:
        photo_api.permanently_delete_recycle_bin_photos(
            batch_data=payload, db=db, current_user=_user()
        )
    assert exc.value.status_code == 400


def test_permanently_delete_recycle_bin_delegates_on_success():
    db = MagicMock()
    user = _user()
    payload = BatchPhotoDelete(photo_ids=[uuid4()])
    with patch.object(
        photo_api.app.crud.photo,
        "batch_delete_photos_db",
        return_value=1,
    ) as crud_call:
        result = photo_api.permanently_delete_recycle_bin_photos(
            batch_data=payload, db=db, current_user=user
        )
    crud_call.assert_called_once()
    assert crud_call.call_args.kwargs["user_id"] == user.id
    assert "Successfully permanently deleted 1" in result.data["message"]


def test_batch_delete_photos_soft_delegates():
    db = MagicMock()
    user = _user()
    payload = BatchPhotoDelete(photo_ids=[uuid4()])
    with patch.object(
        photo_api.app.crud.photo, "batch_soft_delete_photos", return_value=1
    ) as crud_call:
        result = photo_api.batch_delete_photos(
            batch_data=payload, db=db, current_user=user
        )
    crud_call.assert_called_once()
    assert "Successfully moved 1" in result.data["message"]
# tag endpoints
def test_get_photo_tags_delegates_with_owner_filter():
    db = MagicMock()
    user = _user()
    pid = uuid4()
    expected = [SimpleNamespace(id=uuid4(), tag_name="trip")]
    with patch.object(
        photo_api.crud_tag, "get_photo_tags", return_value=expected
    ) as crud_call:
        result = photo_api.get_photo_tags(
            photo_id=pid, db=db, current_user=user
        )
    crud_call.assert_called_once_with(db, pid, owner_id=user.id)
    assert result is expected


def test_add_photo_tag_raises_404_when_photo_missing():
    db = MagicMock()
    pid = uuid4()
    payload = SimpleNamespace(tag_name="trip", confidence=1.0)
    with patch.object(photo_api.app.crud.photo, "get_photo", return_value=None):
        with pytest.raises(HTTPException) as exc:
            photo_api.add_photo_tag(
                photo_id=pid, tag_data=payload, db=db, current_user=_user()
            )
    assert exc.value.status_code == 404


def test_add_photo_tag_raises_403_when_not_owner():
    db = MagicMock()
    pid = uuid4()
    owner = uuid4()
    user = SimpleNamespace(id=uuid4())  # different from owner
    photo = SimpleNamespace(id=pid, owner_id=owner)
    payload = SimpleNamespace(tag_name="trip", confidence=1.0)
    with patch.object(photo_api.app.crud.photo, "get_photo", return_value=photo):
        with pytest.raises(HTTPException) as exc:
            photo_api.add_photo_tag(
                photo_id=pid, tag_data=payload, db=db, current_user=user
            )
    assert exc.value.status_code == 403


def test_add_photo_tag_success_delegates_to_crud_tag():
    db = MagicMock()
    pid = uuid4()
    user = _user()
    photo = SimpleNamespace(id=pid, owner_id=user.id)
    payload = SimpleNamespace(tag_name="trip", confidence=0.8)
    expected = SimpleNamespace(id=uuid4(), tag_name="trip")
    with patch.object(photo_api.app.crud.photo, "get_photo", return_value=photo), \
         patch.object(
             photo_api.crud_tag, "add_tag_to_photo", return_value=expected
         ) as add_call:
        result = photo_api.add_photo_tag(
            photo_id=pid, tag_data=payload, db=db, current_user=user
        )
    add_call.assert_called_once_with(db, pid, "trip", 0.8, owner_id=user.id)
    assert result is expected


def test_delete_photo_tag_raises_404_when_photo_missing():
    db = MagicMock()
    pid = uuid4()
    tid = uuid4()
    with patch.object(photo_api.app.crud.photo, "get_photo", return_value=None):
        with pytest.raises(HTTPException) as exc:
            photo_api.delete_photo_tag(
                photo_id=pid, tag_id=tid, db=db, current_user=_user()
            )
    assert exc.value.status_code == 404


def test_delete_photo_tag_success_calls_remove():
    db = MagicMock()
    pid = uuid4()
    tid = uuid4()
    user = _user()
    photo = SimpleNamespace(id=pid, owner_id=user.id)
    with patch.object(photo_api.app.crud.photo, "get_photo", return_value=photo), \
         patch.object(photo_api.crud_tag, "remove_tag_from_photo") as remove_call:
        result = photo_api.delete_photo_tag(
            photo_id=pid, tag_id=tid, db=db, current_user=user
        )
    remove_call.assert_called_once_with(db, pid, tid)
    assert result.code == 0
# description / random / on-this-day
def test_get_photo_description_returns_none_when_no_row():
    db = MagicMock()
    chain = db.query.return_value
    chain.filter.return_value.first.return_value = None
    assert photo_api.get_photo_description(
        photo_id=uuid4(), db=db, current_user=_user()
    ) is None


def test_get_photo_description_raises_403_when_not_owner():
    db = MagicMock()
    pid = uuid4()
    user = _user()
    desc = SimpleNamespace(photo_id=pid, description="x")
    photo = SimpleNamespace(id=pid, owner_id=uuid4())  # not owned

    q1 = MagicMock()
    q1.filter.return_value.first.return_value = desc
    q2 = MagicMock()
    q2.filter.return_value.first.return_value = photo
    db.query.side_effect = [q1, q2]

    with pytest.raises(HTTPException) as exc:
        photo_api.get_photo_description(photo_id=pid, db=db, current_user=user)
    assert exc.value.status_code == 403


def test_get_photo_description_returns_desc_when_owned():
    db = MagicMock()
    pid = uuid4()
    user = _user()
    desc = SimpleNamespace(photo_id=pid, description="hello")
    photo = SimpleNamespace(id=pid, owner_id=user.id)

    q1 = MagicMock()
    q1.filter.return_value.first.return_value = desc
    q2 = MagicMock()
    q2.filter.return_value.first.return_value = photo
    db.query.side_effect = [q1, q2]

    out = photo_api.get_photo_description(photo_id=pid, db=db, current_user=user)
    assert out is desc


def test_get_random_photos_forwards_user_and_limit():
    db = MagicMock()
    user = _user()
    expected = [SimpleNamespace(id=uuid4())]
    with patch.object(
        photo_api.app.crud.photo, "get_random_photos", return_value=expected
    ) as crud_call:
        result = photo_api.get_random_photos(limit=7, db=db, current_user=user)
    crud_call.assert_called_once_with(db, user_id=user.id, limit=7)
    assert result.data is expected
    assert result.code == 0


def test_get_on_this_day_photos_uses_default_year_when_missing():
    db = MagicMock()
    user = _user()
    expected = [SimpleNamespace(id=uuid4())]
    with patch.object(
        photo_api.app.crud.photo, "get_on_this_day_photos", return_value=expected
    ) as crud_call, patch(
        "app.middleware.demo_mode.DEMO_MODE", False
    ):
        result = photo_api.get_on_this_day_photos(
            month=None, day=None, year=None, limit=5, db=db, current_user=user
        )
    passed = crud_call.call_args
    assert passed.kwargs["user_id"] == user.id
    assert passed.kwargs["limit"] == 5
    today = datetime.now()
    assert passed.kwargs["month"] == today.month
    assert passed.kwargs["day"] == today.day
    assert passed.kwargs["year"] == today.year
    assert result is expected


def test_get_on_this_day_photos_honors_explicit_values():
    db = MagicMock()
    user = _user()
    with patch.object(
        photo_api.app.crud.photo, "get_on_this_day_photos", return_value=[]
    ) as crud_call, patch(
        "app.middleware.demo_mode.DEMO_MODE", False
    ):
        photo_api.get_on_this_day_photos(
            month=3, day=14, year=2024, limit=8, db=db, current_user=user
        )
    passed = crud_call.call_args
    assert passed.kwargs["month"] == 3
    assert passed.kwargs["day"] == 14
    assert passed.kwargs["year"] == 2024
    assert passed.kwargs["limit"] == 8
# replace_photo_file (async)
def _upload_file_mock():
    f = MagicMock()
    f.filename = "new.jpg"
    return f


@pytest.mark.asyncio
async def test_replace_photo_file_raises_404_when_photo_missing():
    db = MagicMock()
    pid = uuid4()
    with patch.object(photo_api.app.crud.photo, "get_photo", return_value=None):
        with pytest.raises(HTTPException) as exc:
            await photo_api.replace_photo_file(
                photo_id=pid, file=_upload_file_mock(), db=db, current_user=_user()
            )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_replace_photo_file_raises_403_when_not_owner():
    db = MagicMock()
    pid = uuid4()
    owner = uuid4()
    user = SimpleNamespace(id=uuid4())
    photo = SimpleNamespace(
        id=pid, owner_id=owner, file_type="image", file_path="/x.jpg"
    )
    with patch.object(photo_api.app.crud.photo, "get_photo", return_value=photo):
        with pytest.raises(HTTPException) as exc:
            await photo_api.replace_photo_file(
                photo_id=pid, file=_upload_file_mock(), db=db, current_user=user
            )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_replace_photo_file_raises_400_for_video():
    db = MagicMock()
    pid = uuid4()
    user = _user()
    photo = SimpleNamespace(
        id=pid, owner_id=user.id, file_type=FileType.video, file_path="/x.mp4"
    )
    with patch.object(photo_api.app.crud.photo, "get_photo", return_value=photo):
        with pytest.raises(HTTPException) as exc:
            await photo_api.replace_photo_file(
                photo_id=pid, file=_upload_file_mock(), db=db, current_user=user
            )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_replace_photo_file_happy_path_calls_storage_and_crud(tmp_path):
    db = MagicMock()
    pid = uuid4()
    user = _user()
    photo = SimpleNamespace(
        id=pid, owner_id=user.id, file_type="image", file_path="/old.jpg"
    )
    new_path = str(tmp_path / "new.jpg")
    updated = SimpleNamespace(id=pid, file_path=new_path)

    with patch.object(photo_api.app.crud.photo, "get_photo", return_value=photo), \
         patch.object(
             photo_api.storage, "save_upload_file", return_value=new_path
         ) as save_call, patch.object(
             photo_api.app.crud.photo, "replace_photo_file", return_value=updated
         ) as replace_call:
        result = await photo_api.replace_photo_file(
            photo_id=pid, file=_upload_file_mock(), db=db, current_user=user
        )

    save_call.assert_called_once()
    replace_call.assert_called_once_with(db, photo, new_path, user.id)
    assert result.data is updated
# batch_update_photos (top-level dispatcher)
def test_batch_update_photos_invalid_action_returns_400():
    db = MagicMock()
    payload = BatchPhotoUpdate(photo_ids=[uuid4()], action="weird")
    with pytest.raises(HTTPException) as exc:
        photo_api.batch_update_photos(
            batch_data=payload, db=db, current_user=_user()
        )
    assert exc.value.status_code == 400
    assert exc.value.detail == "Invalid action"


def test_batch_update_photos_add_to_album_requires_album_id():
    db = MagicMock()
    payload = BatchPhotoUpdate(photo_ids=[uuid4()], action="add_to_album")
    with pytest.raises(HTTPException) as exc:
        photo_api.batch_update_photos(
            batch_data=payload, db=db, current_user=_user()
        )
    assert exc.value.status_code == 400
    assert "Album ID required" in exc.value.detail


def test_batch_update_photos_add_to_album_404_when_album_missing():
    db = MagicMock()
    album_id = uuid4()
    payload = BatchPhotoUpdate(
        photo_ids=[uuid4()], action="add_to_album", album_id=album_id
    )
    with patch.object(
        photo_api.crud_album, "get_album", return_value=None
    ):
        with pytest.raises(HTTPException) as exc:
            photo_api.batch_update_photos(
                batch_data=payload, db=db, current_user=_user()
            )
    assert exc.value.status_code == 404


def test_batch_update_photos_add_to_album_success():
    db = MagicMock()
    album_id = uuid4()
    payload = BatchPhotoUpdate(
        photo_ids=[uuid4(), uuid4()], action="add_to_album", album_id=album_id
    )
    album = SimpleNamespace(id=album_id)
    with patch.object(photo_api.crud_album, "get_album", return_value=album), \
         patch.object(
             photo_api.crud_album, "batch_update_album_association", return_value=2
         ) as assoc_call:
        result = photo_api.batch_update_photos(
            batch_data=payload, db=db, current_user=_user()
        )
    assoc_call.assert_called_once()
    assert "Successfully updated 2" in result.data["message"]


def test_batch_update_photos_delete_branch_calls_soft_delete():
    db = MagicMock()
    payload = BatchPhotoUpdate(photo_ids=[uuid4()], action="delete")
    with patch.object(
        photo_api.app.crud.photo, "batch_soft_delete_photos"
    ) as soft:
        result = photo_api.batch_update_photos(
            batch_data=payload, db=db, current_user=_user()
        )
    soft.assert_called_once()
    assert "recycle bin" in result.data["message"]
