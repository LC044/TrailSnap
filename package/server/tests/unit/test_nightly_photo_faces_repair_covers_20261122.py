"""Nightly watch 2026-11-22 · app/service/photo_faces.py::repair_face_covers 盲区。

repair_face_covers 在人物封面失效时（封面脸被软删除 / 归属被改走 / 照片被删）
重选一张可信度最高的脸作为新封面。它是 assign_photo_face 的收口逻辑，
出错会让人物列表出现「空封面」或指向别人照片。

本文件覆盖：
- 封面仍然有效 -> 保持不变（happy）
- 封面脸被软删除 -> 重选置信度最高的存活脸（edge）
- 封面脸指向别人的照片 -> 重选本 owner 的存活脸（edge）
- 该人物已无任何可用脸 -> 封面置空（edge）
- 传入不存在的 identity / 别的 owner 的 identity -> 跳过，不误改（error）
"""

from uuid import uuid4

import pytest

from app.db.models.face import Face, FaceIdentity
from app.db.models.photo import FileType, Photo
from app.db.models.user import User
from app.service.photo_faces import repair_face_covers

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


def _identity(db, user, name="未命名"):
    identity = FaceIdentity(identity_name=name, owner_id=user.id)
    db.add(identity)
    db.flush()
    return identity


def _face(db, photo, identity, *, confidence=None, deleted=False):
    face = Face(photo_id=photo.id, face_identity_id=identity.id,
                is_deleted=deleted, face_rect=[0.1, 0.1, 0.2, 0.2],
                recognize_confidence=confidence)
    db.add(face)
    db.flush()
    return face


def test_repair_face_covers_keeps_a_still_valid_cover(face_sqlite_session):
    db = face_sqlite_session
    user = _user(db, "keeper")
    identity = _identity(db, user)
    photo = _photo(db, user, "a")
    face = _face(db, photo, identity, confidence=0.9)
    identity.default_face_id = face.id
    db.flush()

    repair_face_covers(db, {identity.id}, user.id)

    assert identity.default_face_id == face.id


def test_repair_face_covers_picks_the_highest_confidence_live_face(face_sqlite_session):
    db = face_sqlite_session
    user = _user(db, "reselect")
    identity = _identity(db, user)
    good_photo = _photo(db, user, "good")
    weak_photo = _photo(db, user, "weak")
    deleted_photo = _photo(db, user, "deleted")
    weak = _face(db, weak_photo, identity, confidence=0.30)
    good = _face(db, good_photo, identity, confidence=0.95)
    dead = _face(db, deleted_photo, identity, confidence=0.99, deleted=True)
    identity.default_face_id = dead.id
    db.flush()

    repair_face_covers(db, {identity.id}, user.id)

    assert identity.default_face_id == good.id
    assert identity.default_face_id != weak.id


def test_repair_face_covers_ignores_faces_of_other_owners(face_sqlite_session):
    db = face_sqlite_session
    owner = _user(db, "owner")
    intruder = _user(db, "intruder")
    identity = _identity(db, owner)
    own_photo = _photo(db, owner, "own")
    foreign_photo = _photo(db, intruder, "foreign")
    own_face = _face(db, own_photo, identity, confidence=0.10)
    foreign_face = _face(db, foreign_photo, identity, confidence=0.99)
    identity.default_face_id = foreign_face.id
    db.flush()

    repair_face_covers(db, {identity.id}, owner.id)

    assert identity.default_face_id == own_face.id


def test_repair_face_covers_clears_the_cover_when_no_face_is_left(face_sqlite_session):
    db = face_sqlite_session
    user = _user(db, "empty")
    identity = _identity(db, user)
    photo = _photo(db, user, "only")
    face = _face(db, photo, identity, confidence=0.9)
    identity.default_face_id = face.id
    db.flush()
    face.is_deleted = True
    db.flush()

    repair_face_covers(db, {identity.id}, user.id)

    assert identity.default_face_id is None


def test_repair_face_covers_skips_identities_of_another_owner(face_sqlite_session):
    db = face_sqlite_session
    owner = _user(db, "real-owner")
    other = _user(db, "other-owner")
    identity = _identity(db, other)
    photo = _photo(db, other, "theirs")
    face = _face(db, photo, identity, confidence=0.9)
    identity.default_face_id = None
    db.flush()

    repair_face_covers(db, {identity.id}, owner.id)

    assert identity.default_face_id is None
    assert face.face_identity_id == identity.id


def test_repair_face_covers_ignores_an_unknown_identity_id(face_sqlite_session):
    db = face_sqlite_session
    user = _user(db, "unknown")

    # 不应抛出异常，也不应产生任何副作用
    repair_face_covers(db, {uuid4()}, user.id)

    assert db.query(FaceIdentity).count() == 0
