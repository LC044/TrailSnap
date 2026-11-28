"""Nightly 2026-11-28: app/service/toolbox_scope.py 范围过滤/分页/文件夹归属盲区。

覆盖 #525 新增的 PhotoScopeFilters 与 scope_preview 增量分页路径：
- scope_query 的 media_type / excluded_ids / 日期区间 / upload_time_fallback
- scope_preview 对非 folders 来源的 SQL 分页（total 与 items 独立计算）
- iter_scope 对 folders 来源的 include_children 精确目录 vs 递归子目录
"""
import os
from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models import Photo, User
from app.schemas.toolbox import MediaScope
from app.service.toolbox_scope import iter_scope, scope_preview, scope_query

pytestmark = [pytest.mark.smoke, pytest.mark.module_toolbox]


@pytest.fixture()
def scope_env(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'scope.sqlite').as_posix()}")
    Base.metadata.create_all(engine)
    external = tmp_path / "external"
    (external / "sub" / "deep").mkdir(parents=True)
    with Session(engine, expire_on_commit=False) as db:
        user = User(id=uuid4(), username="scope-paging", hashed_password="unused",
                    settings={"storage": {"external_directories": [str(external)]}})
        db.add(user)
        db.commit()

        def photo(name, *, file_type="image", photo_time=None, upload_time=None,
                  folder=None):
            target = folder or external
            item = Photo(id=uuid4(), owner_id=user.id, filename=name,
                         file_path=str(target / name), file_type=file_type,
                         photo_time=photo_time, upload_time=upload_time)
            db.add(item)
            db.commit()
            return item

        yield {"db": db, "user": user, "photo": photo, "external": external}
    engine.dispose()


def test_scope_query_filters_by_media_type_and_excluded_ids(scope_env):
    db, user = scope_env["db"], scope_env["user"]
    image = scope_env["photo"]("a.jpg", file_type="image")
    video = scope_env["photo"]("b.mp4", file_type="video")

    scope = MediaScope(source="all", media_type="video")
    assert [p.id for p in scope_query(db, user, scope).all()] == [video.id]

    scope = MediaScope(source="all", media_type="video", excluded_ids=[video.id])
    assert scope_query(db, user, scope).all() == []

    scope = MediaScope(source="all", media_type="all")
    assert {p.id for p in scope_query(db, user, scope).all()} == {image.id, video.id}


def test_scope_query_date_range_uses_upload_time_fallback(scope_env):
    db, user = scope_env["db"], scope_env["user"]
    uploaded = scope_env["photo"]("c.jpg", photo_time=None,
                                  upload_time=datetime(2024, 5, 10, 9, 0, 0))
    scope = MediaScope(source="filter", media_type="all", start_date=datetime(2024, 5, 1).date(),
                       end_date=datetime(2024, 5, 31).date())
    # photo_time 为空时按 upload_time 兜底才能命中
    assert scope_query(db, user, scope).all() == []
    scope = scope.model_copy(update={"upload_time_fallback": True})
    assert [p.id for p in scope_query(db, user, scope).all()] == [uploaded.id]


def test_scope_preview_pages_non_folder_sources(scope_env):
    db, user = scope_env["db"], scope_env["user"]
    photos = [scope_env["photo"](f"p{i}.jpg") for i in range(3)]
    scope = MediaScope(source="selected", photo_ids=[p.id for p in photos], media_type="all")

    first = scope_preview(db, user, scope, offset=0, limit=2)
    assert first["total"] == 3
    assert len(first["items"]) == 2

    second = scope_preview(db, user, scope, offset=2, limit=2)
    assert second["total"] == 3
    assert len(second["items"]) == 1

    rows = first["items"] + second["items"]
    assert {row["id"] for row in rows} == {str(p.id) for p in photos}
    assert all(row["filename"].endswith(".jpg") for row in rows)


def test_iter_scope_folders_respects_include_children(scope_env):
    db, user = scope_env["db"], scope_env["user"]
    external = scope_env["external"]
    direct = scope_env["photo"]("direct.jpg", folder=external)
    nested = scope_env["photo"]("nested.jpg", folder=external / "sub")
    deep = scope_env["photo"]("deep.jpg", folder=external / "sub" / "deep")

    scope = MediaScope(source="folders", folders=[str(external / "sub")], media_type="all")
    assert {p.id for p in iter_scope(db, user, scope)} == {nested.id, deep.id}

    scope = scope.model_copy(update={"include_children": False})
    assert {p.id for p in iter_scope(db, user, scope)} == {nested.id}
    assert direct.id not in {p.id for p in iter_scope(db, user, scope)}


def test_scope_preview_for_folders_counts_every_match(scope_env):
    db, user = scope_env["db"], scope_env["user"]
    external = scope_env["external"]
    scope_env["photo"]("one.jpg", folder=external / "sub")
    scope_env["photo"]("two.jpg", folder=external / "sub" / "deep")
    scope = MediaScope(source="folders", folders=[str(external / "sub")], media_type="all")

    preview = scope_preview(db, user, scope, offset=0, limit=1)
    assert preview["total"] == 2
    assert len(preview["items"]) == 1


def test_iter_scope_skips_photos_outside_the_selected_folder(scope_env):
    db, user = scope_env["db"], scope_env["user"]
    external = scope_env["external"]
    outside = scope_env["photo"]("outside.jpg", folder=external.parent)
    inside = scope_env["photo"]("inside.jpg", folder=external)
    scope = MediaScope(source="folders", folders=[str(external)], media_type="all")
    ids = {p.id for p in iter_scope(db, user, scope)}
    assert ids == {inside.id}
    assert outside.id not in ids
    assert os.path.normcase(str(external)).endswith("external")
