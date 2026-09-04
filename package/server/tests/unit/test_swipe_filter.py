from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import swipe_filter as swipe_filter_api
from app.crud import photo as photo_crud
from app.crud import swipe_filter as swipe_filter_crud
from app.db.base import Base
from app.db.models.photo import FileType, Photo
from app.db.models.photo_declutter_record import PhotoDeclutterRecord
from app.db.models.user import User
from app.schemas.swipe_filter import SwipeFilterDecisionItem, SwipeFilterDecisionRequest


pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


def _user(db, username: str) -> User:
    user = User(
        username=username,
        email=f"{username}@example.com",
        hashed_password="test",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _photo(db, owner: User, name: str) -> Photo:
    photo = Photo(
        filename=name,
        file_path=f"/{owner.id}/{name}",
        file_type=FileType.image,
        size=1,
        owner_id=owner.id,
        is_deleted=False,
    )
    db.add(photo)
    db.commit()
    db.refresh(photo)
    return photo


def _item(photo: Photo, decision: str) -> SwipeFilterDecisionItem:
    return SwipeFilterDecisionItem(photo_id=photo.id, decision=decision)


def test_decisions_are_durable_excluded_idempotent_and_user_scoped(db):
    owner = _user(db, "owner")
    other = _user(db, "other")
    first = _photo(db, owner, "first.jpg")
    second = _photo(db, owner, "second.jpg")
    third = _photo(db, owner, "third.jpg")
    other_photo = _photo(db, other, "other.jpg")

    with patch.object(swipe_filter_crud, "_refresh_albums"):
        assert swipe_filter_crud.save_decisions(
            db, owner.id, [_item(first, "keep"), _item(second, "delete")]
        ) == 2
        # Repeating the same decision updates the existing row instead of
        # creating a duplicate or failing because the photo is now deleted.
        assert swipe_filter_crud.save_decisions(db, owner.id, [_item(second, "delete")]) == 1

    records = db.query(PhotoDeclutterRecord).filter_by(owner_id=owner.id).all()
    assert len(records) == 2
    assert db.get(Photo, second.id).is_deleted is True

    batch, stats = swipe_filter_crud.get_batch(db, owner.id, limit=20)
    assert [photo.id for photo in batch] == [third.id]
    assert other_photo.id not in {photo.id for photo in batch}
    assert stats == {
        "processed": 2,
        "remaining": 1,
        "total": 3,
        "kept": 1,
        "deleted": 1,
    }


def test_undo_restores_delete_and_reset_only_clears_records(db):
    owner = _user(db, "undo-owner")
    kept = _photo(db, owner, "kept.jpg")
    deleted = _photo(db, owner, "deleted.jpg")

    with patch.object(swipe_filter_crud, "_refresh_albums"):
        swipe_filter_crud.save_decisions(
            db, owner.id, [_item(kept, "keep"), _item(deleted, "delete")]
        )
        assert swipe_filter_crud.undo_decision(db, owner.id, deleted.id) is True

    assert db.get(Photo, deleted.id).is_deleted is False
    assert db.query(PhotoDeclutterRecord).filter_by(photo_id=deleted.id).first() is None
    assert swipe_filter_crud.reset_decisions(db, owner.id) == 1
    assert db.query(PhotoDeclutterRecord).filter_by(owner_id=owner.id).count() == 0
    assert db.get(Photo, kept.id).is_deleted is False


def test_recycle_bin_restore_reopens_swipe_deleted_photo(db):
    owner = _user(db, "restore-owner")
    photo = _photo(db, owner, "restore.jpg")

    with patch.object(swipe_filter_crud, "_refresh_albums"):
        swipe_filter_crud.save_decisions(db, owner.id, [_item(photo, "delete")])

    # restore_photos now recounts albums in one batched call (update_album_photo_counts)
    # instead of committing once per album, so the isolation patch must target that
    # name — patching the old per-album helper would silently do nothing.
    with patch.object(photo_crud, "update_album_photo_counts"), patch(
        "app.crud.album.trigger_conditional_albums_update"
    ):
        assert photo_crud.restore_photos(db, [photo.id], user_id=owner.id) == 1

    assert db.get(Photo, photo.id).is_deleted is False
    assert db.query(PhotoDeclutterRecord).filter_by(photo_id=photo.id).first() is None
    batch, stats = swipe_filter_crud.get_batch(db, owner.id, limit=20)
    assert [item.id for item in batch] == [photo.id]
    assert stats["remaining"] == 1


def test_api_wraps_batch_and_maps_decisions():
    db = MagicMock()
    user = SimpleNamespace(id=uuid4())
    photo = SimpleNamespace(id=uuid4())
    stats = {"processed": 0, "remaining": 1, "total": 1, "kept": 0, "deleted": 0}

    with patch.object(swipe_filter_api.crud, "get_batch", return_value=([photo], stats)):
        response = swipe_filter_api.get_swipe_filter_batch(limit=20, db=db, current_user=user)
    assert response.code == 0
    assert response.data["photos"] == [photo]
    assert response.data["stats"] == stats

    payload = SwipeFilterDecisionRequest(items=[
        SwipeFilterDecisionItem(photo_id=photo.id, decision="keep")
    ])
    with patch.object(swipe_filter_api.crud, "save_decisions", return_value=1) as save:
        response = swipe_filter_api.save_swipe_filter_decisions(payload, db=db, current_user=user)
    save.assert_called_once_with(db, user.id, payload.items)
    assert response.data == {"updated": 1}
