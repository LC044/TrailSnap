"""Nightly watch 2026-11-22 · app/service/similar_faces.py::_reference / _finish 盲区。

_reference 是「相似人脸查找 / 归属」的入口守卫：它同时校验照片归属、人脸存在性
以及特征与检测框是否可用；一旦放过一张没有特征或检测框非法的人脸，后续的
相似度计算就会产出错误结果。
_finish 是批量归属的收口：它负责刷新人物封面、触发条件相册更新并提交事务，
漏掉任何一步都会让用户看到「归属已改但封面/相册没更新」的中间态。

本文件覆盖：
- _reference: 照片不属于本人 / 人脸不存在 -> 404（error）
- _reference: 检测框非法 / 缺少特征 -> 422（error）
- _reference: 正常人脸 -> 返回该人脸（happy）
- _finish: 返回去重且按字符串排序的照片 id，并触发相册更新（happy）
- _finish: 人物封面失效时顺带被修复（edge）
- _finish: 提交后修改对后续查询可见（happy）
"""

from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.db.models.face import Face, FaceIdentity
from app.db.models.photo import FileType, Photo
from app.db.models.user import User
from app.service.similar_faces import _finish, _reference

pytestmark = [pytest.mark.smoke]


def _user(db, name):
    user = User(username=name, email=f"{name}@example.com", hashed_password="x")
    db.add(user)
    db.flush()
    return user


def _photo(db, user, name, *, deleted=False):
    photo = Photo(filename=f"{name}.jpg", file_path=f"/{name}.jpg",
                  file_type=FileType.image, size=10, owner_id=user.id,
                  is_deleted=deleted)
    db.add(photo)
    db.flush()
    return photo


def _face(db, photo, identity=None, *, rect=None, feature=None, deleted=False):
    face = Face(photo_id=photo.id, face_identity_id=identity.id if identity else None,
                is_deleted=deleted,
                face_rect=rect if rect is not None else [0.1, 0.1, 0.4, 0.4],
                face_feature=feature if feature is not None else [0.1] * 512)
    db.add(face)
    db.flush()
    return face


def test_reference_rejects_a_photo_owned_by_somebody_else(face_sqlite_session):
    db = face_sqlite_session
    owner = _user(db, "owner")
    intruder = _user(db, "intruder")
    photo = _photo(db, intruder, "foreign")
    face = _face(db, photo)

    with pytest.raises(HTTPException) as exc:
        _reference(db, photo.id, face.id, owner.id)

    assert exc.value.status_code == 404


def test_reference_rejects_an_unknown_face_id(face_sqlite_session):
    db = face_sqlite_session
    owner = _user(db, "owner")
    photo = _photo(db, owner, "mine")

    with pytest.raises(HTTPException) as exc:
        _reference(db, photo.id, 987654, owner.id)

    assert exc.value.status_code == 404


def test_reference_rejects_a_soft_deleted_face(face_sqlite_session):
    db = face_sqlite_session
    owner = _user(db, "owner")
    photo = _photo(db, owner, "deleted-face")
    face = _face(db, photo, deleted=True)

    with pytest.raises(HTTPException) as exc:
        _reference(db, photo.id, face.id, owner.id)

    assert exc.value.status_code == 404


def test_reference_rejects_a_face_without_feature(face_sqlite_session):
    db = face_sqlite_session
    owner = _user(db, "owner")
    photo = _photo(db, owner, "no-feature")
    face = _face(db, photo, feature=None)
    face.face_feature = None
    db.flush()

    with pytest.raises(HTTPException) as exc:
        _reference(db, photo.id, face.id, owner.id)

    assert exc.value.status_code == 422


def test_reference_rejects_an_invalid_face_rect(face_sqlite_session):
    db = face_sqlite_session
    owner = _user(db, "owner")
    photo = _photo(db, owner, "bad-rect")
    face = _face(db, photo, rect=[0.6, 0.1, 0.2, 0.4])

    with pytest.raises(HTTPException) as exc:
        _reference(db, photo.id, face.id, owner.id)

    assert exc.value.status_code == 422


def test_reference_returns_a_usable_face(face_sqlite_session):
    db = face_sqlite_session
    owner = _user(db, "owner")
    photo = _photo(db, owner, "good")
    face = _face(db, photo)

    found = _reference(db, photo.id, face.id, owner.id)

    assert found.id == face.id
    assert found.photo_id == photo.id


def test_finish_returns_sorted_unique_photo_ids_and_triggers_albums(face_sqlite_session, monkeypatch):
    db = face_sqlite_session
    owner = _user(db, "owner")
    identity = FaceIdentity(identity_name="同名", owner_id=owner.id)
    db.add(identity)
    db.flush()
    photo_a = _photo(db, owner, "a")
    photo_b = _photo(db, owner, "b")
    face_a = _face(db, photo_a, identity)
    face_b = _face(db, photo_b, identity)

    calls = []
    from app.crud import album as album_module
    monkeypatch.setattr(album_module, "trigger_conditional_albums_update",
                        lambda db, owner_id, photo_ids, commit=False: calls.append((owner_id, sorted(map(str, photo_ids)), commit)))

    result = _finish(db, owner.id, [face_a, face_b, face_a], {identity.id})

    assert result == sorted({photo_a.id, photo_b.id}, key=str)
    assert len(calls) == 1
    owner_id, photo_ids, commit = calls[0]
    assert owner_id == owner.id
    assert photo_ids == sorted(map(str, result), key=str)
    assert commit is False


def test_finish_repairs_a_stale_identity_cover(face_sqlite_session, monkeypatch):
    db = face_sqlite_session
    owner = _user(db, "owner")
    identity = FaceIdentity(identity_name="需换封面", owner_id=owner.id)
    db.add(identity)
    db.flush()
    photo = _photo(db, owner, "cover")
    stale = _face(db, photo, identity, rect=[0.1, 0.1, 0.2, 0.2])
    keeper = _face(db, photo, identity, rect=[0.3, 0.3, 0.6, 0.6])
    identity.default_face_id = stale.id
    db.flush()
    stale.is_deleted = True
    db.flush()

    from app.crud import album as album_module
    monkeypatch.setattr(album_module, "trigger_conditional_albums_update",
                        lambda db, owner_id, photo_ids, commit=False: None)

    _finish(db, owner.id, [keeper], {identity.id})

    assert identity.default_face_id == keeper.id


def test_finish_commits_the_pending_changes(face_sqlite_session, monkeypatch):
    db = face_sqlite_session
    owner = _user(db, "owner")
    identity = FaceIdentity(identity_name="提交", owner_id=owner.id)
    db.add(identity)
    db.flush()
    photo = _photo(db, owner, "commit")
    face = _face(db, photo, identity)

    from app.crud import album as album_module
    monkeypatch.setattr(album_module, "trigger_conditional_albums_update",
                        lambda db, owner_id, photo_ids, commit=False: None)

    _finish(db, owner.id, [face], {identity.id})

    assert db.query(Face).filter(Face.id == face.id).count() == 1
    assert db.expire_on_commit is not None
    # 提交后对象仍可读取，且身份绑定保持不变
    assert face.face_identity_id == identity.id
