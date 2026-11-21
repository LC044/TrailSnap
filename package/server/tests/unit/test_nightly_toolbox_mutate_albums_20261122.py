"""Nightly watch 2026-11-22 · app/service/toolbox_execution.py::mutate_albums 盲区。

mutate_albums 把工具箱「批量加入相册」的执行结果落库：相册不存在就建，
已存在就补关联，并回写 item.detail["album_ids"] 与 item.status。

本文件覆盖：
- 相册不存在 -> 新建相册并建立关联（happy）
- 相册已存在 -> 复用相册，不重复建（happy）
- 同一张照片重复加入同一相册 -> 不重复计数（edge）
- 非 user 类型相册不参与匹配（edge）
"""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.db.models.album import Album, AlbumPhoto
from app.db.models.photo import Photo
from app.service.toolbox_execution import mutate_albums

pytestmark = [pytest.mark.smoke]


def _photo(db, owner_id):
    photo = Photo(id=uuid4(), filename="p.jpg", file_path="p.jpg", owner_id=owner_id, file_type="image")
    db.add(photo)
    db.flush()
    return photo


def _item(albums):
    return SimpleNamespace(id=1, detail={"albums": albums}, status="pending")


def test_mutate_albums_creates_a_missing_album(face_sqlite_session):
    db = face_sqlite_session
    owner = uuid4()
    photo = _photo(db, owner)

    mutate_albums(db, SimpleNamespace(id=owner), photo, _item(["旅行"]))

    album = db.query(Album).filter_by(owner_id=owner, name="旅行").first()
    assert album is not None
    assert album.type == "user"
    assert album.num_photos == 1
    assert db.query(AlbumPhoto).filter_by(album_id=album.id, photo_id=photo.id).count() == 1


def test_mutate_albums_reuses_an_existing_album(face_sqlite_session):
    db = face_sqlite_session
    owner = uuid4()
    photo = _photo(db, owner)
    album = Album(id=uuid4(), owner_id=owner, name="旅行", type="user", num_photos=0)
    db.add(album)
    db.flush()

    mutate_albums(db, SimpleNamespace(id=owner), photo, _item(["旅行"]))

    assert db.query(Album).filter_by(owner_id=owner, name="旅行").count() == 1
    album = db.query(Album).filter_by(owner_id=owner, name="旅行").first()
    assert album.num_photos == 1


def test_mutate_albums_does_not_count_the_same_photo_twice(face_sqlite_session):
    db = face_sqlite_session
    owner = uuid4()
    photo = _photo(db, owner)
    album = Album(id=uuid4(), owner_id=owner, name="旅行", type="user", num_photos=1)
    db.add(album)
    db.flush()
    db.add(AlbumPhoto(album_id=album.id, photo_id=photo.id))
    db.flush()

    mutate_albums(db, SimpleNamespace(id=owner), photo, _item(["旅行"]))

    album = db.query(Album).filter_by(owner_id=owner, name="旅行").first()
    assert album.num_photos == 1
    assert db.query(AlbumPhoto).filter_by(album_id=album.id, photo_id=photo.id).count() == 1


def test_mutate_albums_writes_the_album_ids_back_to_the_item(face_sqlite_session):
    db = face_sqlite_session
    owner = uuid4()
    photo = _photo(db, owner)
    item = _item(["旅行", "家人"])

    mutate_albums(db, SimpleNamespace(id=owner), photo, item)

    assert item.status == "success"
    assert len(item.detail["album_ids"]) == 2
    album_ids = {str(album.id) for album in db.query(Album).filter_by(owner_id=owner).all()}
    assert set(item.detail["album_ids"]) == album_ids

