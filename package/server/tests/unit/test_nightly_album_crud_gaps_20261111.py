"""Nightly watch 2026-11-11: ``app/crud/album.py`` update / conditional-sync gaps.

The 2026-11-11 coverage snapshot showed ``app/crud/album.py`` at 93.8% with 18
missed statements. The uncovered branches are:

* ``update_album``            - clearing the shared-user list, resolving shared
                                users from their ids, and keeping the previous
                                ``description`` / ``threshold`` when the update
                                payload leaves them out (they are ``None``);
* ``trigger_conditional_albums_update``
                              - no conditional/smart album at all, an empty
                                ``photo_ids`` list, adding a photo that now
                                matches the condition, dropping a photo that no
                                longer matches, and the fallback to a full async
                                scan when no photo ids are supplied;
* ``_smart_people_section`` / ``_smart_location_section`` /
  ``_smart_classification_section``
                              - the "no rows" short circuit.

Every test exercises already-implemented behaviour; no production code changes.
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.crud import album as album_crud
from app.db.base import Base
from app.db.models.album import Album, AlbumPhoto
from app.db.models.photo import FileType, Photo
from app.db.models.user import User
from app.schemas import album as album_schemas


pytestmark = [pytest.mark.smoke, pytest.mark.module_album]


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def owner_id(db):
    value = uuid4()
    db.add(User(id=value, username="nightly-album-crud-owner", hashed_password="x"))
    db.commit()
    return value


def _album(db, owner_id, *, name="条件相册", type_="conditional", condition=None, threshold=0.25):
    row = Album(id=uuid4(), owner_id=owner_id, name=name, type=type_, condition=condition, threshold=threshold)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _photo(db, owner_id, filename="p.jpg"):
    now = datetime(2024, 4, 2, 10, 0, 0)
    photo = Photo(id=uuid4(), owner_id=owner_id, filename=filename, file_path=filename,
                  file_type=FileType.image, photo_time=now, upload_time=now)
    db.add(photo)
    db.commit()
    db.refresh(photo)
    return photo


def test_update_album_keeps_previous_values_when_the_payload_omits_them(db, owner_id):
    """description / threshold 为 None 时保留旧值，不被清空。"""
    row = _album(db, owner_id)
    row.description = "旧描述"
    row.threshold = 0.9
    db.commit()

    updated = album_crud.update_album(db, row.id, album_schemas.AlbumUpdate(name="新名字", description=None, threshold=None))

    assert updated.name == "新名字"
    assert updated.description == "旧描述"
    assert updated.threshold == 0.9


def test_update_album_clears_and_resolves_shared_users(db, owner_id):
    """shared_users 传空列表表示清空；传 id 列表表示解析成用户。"""
    row = _album(db, owner_id)
    friend_id = uuid4()
    db.add(User(id=friend_id, username="nightly-album-friend", hashed_password="x"))
    db.commit()

    album_crud.update_album(db, row.id, album_schemas.AlbumUpdate(shared_users=[friend_id]))
    db.refresh(row)
    assert [user.id for user in row.shared_users] == [friend_id]

    album_crud.update_album(db, row.id, album_schemas.AlbumUpdate(shared_users=[]))
    db.refresh(row)
    assert list(row.shared_users) == []


def test_update_album_returns_none_for_an_unknown_album(db):
    """相册不存在时返回 None 而不是抛错。"""
    assert album_crud.update_album(db, uuid4(), album_schemas.AlbumUpdate(name="x")) is None


def test_trigger_conditional_albums_update_does_nothing_without_albums(db, owner_id):
    """用户没有任何条件/智能相册时直接返回。"""
    assert album_crud.trigger_conditional_albums_update(db, owner_id, [uuid4()]) is None


def test_trigger_conditional_albums_update_ignores_an_empty_photo_id_list(db, owner_id):
    """photo_ids 为空列表时直接返回，不做任何匹配。"""
    album = _album(db, owner_id, condition={"file_types": ["image"]})
    assert album_crud.trigger_conditional_albums_update(db, owner_id, []) is None
    db.refresh(album)
    assert album.num_photos == 0


def test_trigger_conditional_albums_update_adds_a_matching_photo(db, owner_id):
    """满足条件的照片被加入相册，并刷新数量与封面。"""
    album = _album(db, owner_id, condition={"time_range": {"start": "2024-01-01T00:00:00", "end": "2024-12-31T23:59:59"}})
    photo = _photo(db, owner_id)

    album_crud.trigger_conditional_albums_update(db, owner_id, [photo.id])

    db.refresh(album)
    assert album.num_photos == 1
    assert album.cover_id == photo.id
    assert db.query(AlbumPhoto).filter(AlbumPhoto.album_id == album.id).count() == 1


def test_trigger_conditional_albums_update_drops_a_photo_that_no_longer_matches(db, owner_id):
    """不再满足条件的照片被移出相册。"""
    album = _album(db, owner_id, condition={"time_range": {"start": "2024-01-01T00:00:00", "end": "2024-12-31T23:59:59"}})
    photo = _photo(db, owner_id)
    db.add(AlbumPhoto(album_id=album.id, photo_id=photo.id))
    db.commit()

    # 条件改成只覆盖 2025 年，这张 2024 年的照片不再匹配
    album_crud.update_album(db, album.id, album_schemas.AlbumUpdate(condition={"time_range": {"start": "2025-01-01T00:00:00", "end": "2025-12-31T23:59:59"}}))
    album_crud.trigger_conditional_albums_update(db, owner_id, [photo.id])

    db.refresh(album)
    assert db.query(AlbumPhoto).filter(AlbumPhoto.album_id == album.id).count() == 0


def test_trigger_conditional_albums_update_falls_back_to_a_full_scan(db, owner_id, monkeypatch):
    """未提供 photo_ids 时退回到异步全量扫描。"""
    album = _album(db, owner_id, condition={"file_types": ["image"]})
    added: list[tuple] = []

    class _Worker:
        @staticmethod
        def get_instance():
            return SimpleNamespace(add_task=lambda db, task_type, payload=None, owner_id=None: added.append(
                (task_type, payload, owner_id)))

    monkeypatch.setattr("app.service.task_worker.TaskWorker", _Worker)

    album_crud.trigger_conditional_albums_update(db, owner_id, None)

    assert len(added) == 1
    _task_type, payload, owner = added[0]
    assert payload == {"album_id": str(album.id)}
    assert owner == owner_id


def test_smart_sections_return_an_empty_section_without_rows(db, owner_id):
    """没有人物/地点/分类数据时，智能相册分区返回空分区。"""
    people = album_crud._smart_people_section(db, owner_id, 4, 0)
    location = album_crud._smart_location_section(db, owner_id, 4, 0)
    classification = album_crud._smart_classification_section(db, owner_id, 4, 0)
    for section in (people, location, classification):
        assert section.item_count == 0
        assert section.photo_count == 0
        assert section.representatives == []

