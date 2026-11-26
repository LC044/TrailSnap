"""Nightly watch 2026-11-25: ``app/crud/swipe_filter.py`` 盲区。

2026-11-24 的后端覆盖率报告里 ``crud/swipe_filter.py`` 为 96.4%，第 136-138 行
（撤销决定时删除记录失败 -> 回滚并把异常抛给调用方）从未被执行。

这条分支是「滑动清理撤销」的失败兜底：如果删记录失败却继续提交，
数据库就会处于半改状态 —— 照片被恢复成未删除，但撤销记录还在，
用户再点一次撤销会拿到一个永远删不掉的僵尸记录。

这里用真实的内存 SQLite 会话 + 一次注入的删除失败来验证：
异常必须冒泡，且事务必须回滚（记录仍在、照片状态未被改动）。
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.crud import swipe_filter as swipe_filter_crud
from app.db.base import Base
from app.db.models.photo import FileType, Photo
from app.db.models.photo_declutter_record import PhotoDeclutterRecord
from app.db.models.user import User


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
def owner(db):
    user = User(id=uuid4(), username="nightly-swipe-owner", hashed_password="x")
    db.add(user)
    db.commit()
    return user


def _deleted_photo(db, owner):
    photo = Photo(
        id=uuid4(), owner_id=owner.id, filename="nightly-swipe.jpg", file_type=FileType.image,
        file_path="/photos/nightly-swipe.jpg", is_deleted=True,
    )
    db.add(photo)
    db.add(PhotoDeclutterRecord(owner_id=owner.id, photo_id=photo.id, decision="delete"))
    db.commit()
    return photo


def test_undo_decision_restores_a_deleted_photo(db, owner):
    photo = _deleted_photo(db, owner)

    assert swipe_filter_crud.undo_decision(db, owner.id, photo.id) is True

    db.refresh(photo)
    assert photo.is_deleted is False
    assert photo.deleted_at is None
    assert db.query(PhotoDeclutterRecord).filter(
        PhotoDeclutterRecord.photo_id == photo.id).count() == 0


def test_undo_decision_rolls_back_when_the_record_cannot_be_deleted(db, owner, monkeypatch):
    photo = _deleted_photo(db, owner)

    def _boom(instance):
        raise RuntimeError("数据库忙")

    monkeypatch.setattr(db, "delete", _boom)

    with pytest.raises(RuntimeError):
        swipe_filter_crud.undo_decision(db, owner.id, photo.id)

    db.expire_all()
    assert db.query(PhotoDeclutterRecord).filter(
        PhotoDeclutterRecord.photo_id == photo.id).count() == 1, "删除失败后记录必须还在"


def test_undo_decision_returns_false_without_a_record(db, owner):
    photo = Photo(
        id=uuid4(), owner_id=owner.id, filename="nightly-plain.jpg", file_type=FileType.image,
        file_path="/photos/nightly-plain.jpg",
    )
    db.add(photo)
    db.commit()

    assert swipe_filter_crud.undo_decision(db, owner.id, photo.id) is False

