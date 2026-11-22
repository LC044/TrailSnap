"""Nightly watch 2026-11-22 · app/service/similar_faces.py::_lock_faces 盲区。

_lock_faces 在「把多张人脸合并到同一身份」之前加行锁并做一次归属校验：
数量对不上说明选中的脸已经变化，必须让用户重新查找。

本文件覆盖：
- 全部命中 -> 返回 {face_id: face}（happy）
- 数量不足 -> HTTPException 409（error）
- 别的 owner 的照片 -> 同样 409（error）
- 已软删除的脸 -> 不计入（edge）
"""

from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.db.models.face import Face
from app.db.models.photo import Photo
from app.service.similar_faces import _lock_faces

pytestmark = [pytest.mark.smoke]


def _photo(db, owner_id, name="p.jpg"):
    photo = Photo(id=uuid4(), filename=name, file_path=name, owner_id=owner_id, file_type="image")
    db.add(photo)
    db.flush()
    return photo


def _face(db, photo):
    face = Face(photo_id=photo.id, is_deleted=False)
    db.add(face)
    db.flush()
    return face


def test_lock_faces_returns_every_requested_face(face_sqlite_session):
    db = face_sqlite_session
    owner = uuid4()
    photo = _photo(db, owner)
    face = _face(db, photo)

    locked = _lock_faces(db, {face.id}, owner)

    assert list(locked) == [face.id]
    assert locked[face.id].id == face.id


def test_lock_faces_rejects_a_partial_selection(face_sqlite_session):
    db = face_sqlite_session
    owner = uuid4()
    photo = _photo(db, owner)
    face = _face(db, photo)

    with pytest.raises(HTTPException) as failure:
        _lock_faces(db, {face.id, face.id + 1000}, owner)
    assert failure.value.status_code == 409


def test_lock_faces_rejects_faces_of_another_owner(face_sqlite_session):
    db = face_sqlite_session
    other = uuid4()
    photo = _photo(db, other)
    face = _face(db, photo)

    with pytest.raises(HTTPException) as failure:
        _lock_faces(db, {face.id}, uuid4())
    assert failure.value.status_code == 409


def test_lock_faces_ignores_soft_deleted_faces(face_sqlite_session):
    db = face_sqlite_session
    owner = uuid4()
    photo = _photo(db, owner)
    face = _face(db, photo)
    face.is_deleted = True
    db.flush()

    with pytest.raises(HTTPException) as failure:
        _lock_faces(db, {face.id}, owner)
    assert failure.value.status_code == 409

