"""Nightly 2026-11-18: app/service/toolbox_scope.py 归属范围解析盲区。"""
import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.db.models
from app.db.base import Base
from app.db.models import Album, AlbumPhoto, Photo, StorageRoot, User
from app.schemas.toolbox import MediaScope
from app.service.toolbox_scope import allowed_directory, owned_roots, scope_query

pytestmark = [pytest.mark.smoke, pytest.mark.module_toolbox]


@pytest.fixture()
def scope_env(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'scope.sqlite').as_posix()}")
    Base.metadata.create_all(engine)
    external = tmp_path / "external"
    external.mkdir()
    with Session(engine, expire_on_commit=False) as db:
        user = User(id=uuid4(), username="scope", hashed_password="unused",
                    settings={"storage": {"external_directories": [str(external)]}})
        other = User(id=uuid4(), username="scope-other", hashed_password="unused")
        db.add_all([user, other])
        db.commit()

        def photo(owner=None, name="a.jpg", file_type="image", album=None):
            item = Photo(id=uuid4(), owner_id=owner or user.id, filename=name,
                         file_path=str(tmp_path / name), file_type=file_type)
            db.add(item)
            db.flush()
            if album is not None:
                db.add(AlbumPhoto(album_id=album, photo_id=item.id))
            db.commit()
            return item

        yield {"db": db, "user": user, "other": other, "photo": photo, "tmp": tmp_path,
               "external": external}
    engine.dispose()


def test_owned_roots_include_external_and_storage_root(scope_env):
    db, user = scope_env["db"], scope_env["user"]
    external = scope_env["external"]
    db.add(StorageRoot(id=uuid4(), owner_id=user.id, name="extra", kind="external",
                       location=str(external)))
    db.commit()
    roots = owned_roots(db, user)
    assert any(os.path.normcase(str(external)) in os.path.normcase(root) for root in roots)
    # 去重：重复的 external_directories 只保留一份
    assert len(roots) == len(set(roots))


def test_owned_roots_ignore_other_users_storage_roots(scope_env):
    db, user, other = scope_env["db"], scope_env["user"], scope_env["other"]
    other_dir = scope_env["tmp"] / "other"
    other_dir.mkdir()
    db.add(StorageRoot(id=uuid4(), owner_id=other.id, name="other", kind="external",
                       location=str(other_dir)))
    db.commit()
    roots = owned_roots(db, user)
    assert not any(os.path.normcase(str(other_dir)) in os.path.normcase(root) for root in roots)


def test_allowed_directory_rejects_relative_and_foreign_paths(scope_env):
    db, user = scope_env["db"], scope_env["user"]
    with pytest.raises(ValueError):
        allowed_directory(db, user, "")
    with pytest.raises(ValueError):
        allowed_directory(db, user, "relative/path")
    with pytest.raises(ValueError):
        allowed_directory(db, user, str(scope_env["tmp"].parent))


def test_allowed_directory_accepts_owned_external_path(scope_env):
    db, user = scope_env["db"], scope_env["user"]
    allowed = allowed_directory(db, user, str(scope_env["external"]))
    assert os.path.normcase(allowed).endswith("external")


def test_scope_query_filters_by_owner_and_deleted(scope_env):
    db, user = scope_env["db"], scope_env["user"]
    scope_env["photo"]()
    deleted = scope_env["photo"](name="deleted.jpg")
    deleted.is_deleted = True
    db.commit()
    scope = MediaScope(source="all", media_type="all")
    ids = {p.id for p in scope_query(db, user, scope).all()}
    assert deleted.id not in ids
    assert len(ids) == 1


def test_scope_query_selected_requires_ownership(scope_env):
    db, user, other = scope_env["db"], scope_env["user"], scope_env["other"]
    foreign = scope_env["photo"](owner=other.id, name="foreign.jpg")
    scope = MediaScope(source="selected", photo_ids=[foreign.id])
    with pytest.raises(ValueError):
        scope_query(db, user, scope)


def test_scope_query_album_scope_requires_owned_album(scope_env):
    db, user, other = scope_env["db"], scope_env["user"], scope_env["other"]
    album = Album(id=uuid4(), owner_id=other.id, name="别人的相册", type="user")
    db.add(album)
    db.commit()
    scope = MediaScope(source="albums", album_ids=[album.id])
    with pytest.raises(ValueError):
        scope_query(db, user, scope)
