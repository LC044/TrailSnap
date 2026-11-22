"""Nightly watch 2026-11-22 · app/service/clip_classification.py::lock_photo 盲区。

lock_photo 在写入标签决策前给照片行加锁：并发跑 CLIP 分类时，两条任务若拿到
同一张照片的决策权，后写者会覆盖先写者的人工取舍（保留/隐藏）。
这个函数本身没有返回值，测试要盯住的是「是否真的加了行锁」与「锁一张
不存在的照片时不应把整个批次打断」。

本文件覆盖：
- 使用 with_for_update 拿锁（happy）
- 锁一张已存在的照片：不抛异常、不改动数据（happy）
- 锁一张不存在的照片：静默跳过，不抛异常（edge）
"""

from uuid import uuid4

import pytest

from app.db.models.photo import FileType, Photo
from app.db.models.user import User
from app.service.clip_classification import lock_photo

pytestmark = [pytest.mark.smoke]


class _SpyQuery:
    def __init__(self, recorder):
        self._recorder = recorder

    def filter(self, *args, **kwargs):
        self._recorder["filtered"] = True
        return self

    def with_for_update(self, *args, **kwargs):
        self._recorder["locked"] = True
        return self

    def first(self):
        self._recorder["selected"] = True
        return None


class _SpySession:
    def __init__(self):
        self.recorder = {}

    def query(self, *args, **kwargs):
        return _SpyQuery(self.recorder)


def _user(db, name):
    user = User(username=name, email=f"{name}@example.com", hashed_password="x")
    db.add(user)
    db.flush()
    return user


def test_lock_photo_asks_the_database_for_a_row_lock():
    spy = _SpySession()

    lock_photo(spy, uuid4())

    assert spy.recorder["filtered"] is True
    assert spy.recorder["locked"] is True
    assert spy.recorder["selected"] is True


def test_lock_photo_accepts_an_existing_photo(face_sqlite_session):
    db = face_sqlite_session
    user = _user(db, "locker")
    photo = Photo(filename="locked.jpg", file_path="/locked.jpg", file_type=FileType.image,
                  size=10, owner_id=user.id)
    db.add(photo)
    db.flush()
    before = db.query(Photo).count()

    lock_photo(db, photo.id)

    assert db.query(Photo).count() == before


def test_lock_photo_ignores_an_unknown_photo_id(face_sqlite_session):
    db = face_sqlite_session
    _user(db, "locker")

    lock_photo(db, uuid4())

    assert db.query(Photo).count() == 0
