"""Nightly 2026-11-18: app/service/chapter_days.py 与 app/crud/tag.py 盲区。"""
from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.db.models
from app.db.base import Base
from app.db.models import Photo, PhotoTag, User
from app.db.models.photo import FileType
from app.crud.tag import resolve_tag
from app.service.chapter_days import photo_item

pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


@pytest.fixture()
def tag_db(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'tag.sqlite').as_posix()}")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        user = User(id=uuid4(), username="tagger", hashed_password="unused")
        db.add(user)
        db.commit()
        yield db, user
    engine.dispose()


def test_photo_item_serializes_core_fields():
    photo = Photo(id=uuid4(), filename="a.jpg", file_type=FileType.image,
                  photo_time=datetime(2021, 6, 1, 12, 0, 0), width=100, height=80)
    item = photo_item(photo)
    assert item["filename"] == "a.jpg"
    assert item["photo_time"] == "2021-06-01T12:00:00"
    assert item["width"] == 100
    assert item["height"] == 80
    assert item["id"] == str(photo.id)
    assert item["file_type"] == "image"


def test_resolve_tag_by_name_returns_owner_tag(tag_db):
    db, user = tag_db
    tag = PhotoTag(id=uuid4(), owner_id=user.id, tag_name="海边", is_deleted=False)
    db.add(tag)
    db.commit()
    assert resolve_tag(db, user.id, "海边") is not None


def test_resolve_tag_by_name_returns_none_when_missing(tag_db):
    db, user = tag_db
    assert resolve_tag(db, user.id, "不存在") is None


def test_resolve_tag_by_id_requires_ownership(tag_db):
    db, user = tag_db
    other = User(id=uuid4(), username="tagger-other", hashed_password="unused")
    db.add(other)
    db.commit()
    tag = PhotoTag(id=uuid4(), owner_id=other.id, tag_name="别人的", is_deleted=False)
    db.add(tag)
    db.commit()
    assert resolve_tag(db, user.id, "别人的", tag_id=tag.id) is None
    assert resolve_tag(db, other.id, "别人的", tag_id=tag.id) is not None


def test_resolve_tag_excludes_deleted_tags(tag_db):
    db, user = tag_db
    tag = PhotoTag(id=uuid4(), owner_id=user.id, tag_name="已删除", is_deleted=True)
    db.add(tag)
    db.commit()
    assert resolve_tag(db, user.id, "已删除") is None
