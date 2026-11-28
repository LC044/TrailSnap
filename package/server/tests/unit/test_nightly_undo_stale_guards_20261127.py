"""Nightly watch 2026-11-27 (round 2) - stale-undo guards and dead-branch backfill.

Targeted coverage measured on 2026-11-27 (see tests/artifacts/nightly/2026-11-27)
showed these confirmed gaps:

- ``app/service/agent/actions.py`` ``undo_plan``: the *stale-state* guards were
  never asserted.  A plan can only be undone when the world still looks the way
  the plan left it; every one of those guards raised ``ValueError`` with a
  distinct Chinese message and none of them appeared in any test file.
- ``app/service/agent/actions.py`` ``undo_plan`` for ``album_organize``: the
  ``tag_changes`` / ``created_tag_ids`` / ``added_photo_ids`` undo payload was
  never exercised at all.
- ``app/utils/portable_library.py``: the "linked configuration" and "invalid
  database" snapshot guards, plus the portable-database integrity check.
- ``app/service/tasks/scan.py``: the ``.HEIC``/``.MOV`` live-photo pairing.
- ``app/service/cleanup_scan.py``: the "file changed while scanning" guard and
  the ``model_cursor`` resume skip.

Everything here is offline: SQLite in-memory, tmp_path, no service process.
"""
from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models.agent_action import AgentActionPlan
from app.db.models.album import Album, AlbumPhoto
from app.db.models.photo import FileType, Photo
from app.db.models.photo_metadata import PhotoMetadata
from app.db.models.tag import PhotoTag, PhotoTagRelation
from app.db.models.user import User
from app.service.agent import actions
from app.utils import portable_library

pytestmark = [pytest.mark.smoke, pytest.mark.module_agent]


# ---------------------------------------------------------------------------
# fixtures / helpers
# ---------------------------------------------------------------------------
@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False)()
    owner = uuid.uuid4()
    session.add(User(id=owner, username="undo-owner", hashed_password="x"))
    session.commit()
    try:
        yield session, owner
    finally:
        session.close()
        engine.dispose()


def _photo(session, owner, name="a.jpg", when=None):
    photo = Photo(id=uuid.uuid4(), owner_id=owner, filename=name, file_path=name,
                  file_type=FileType.image, size=1, is_deleted=False, photo_time=when)
    session.add(photo)
    session.flush()
    return photo


def _executed_plan(session, owner, plan_type, undo_data):
    plan = AgentActionPlan(
        id=uuid.uuid4(), user_id=owner, plan_type=plan_type, title="plan",
        status="executed", operations={}, preview={}, undo_data=undo_data,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    session.add(plan)
    session.commit()
    session.refresh(plan)
    return plan


# ---------------------------------------------------------------------------
# app/service/agent/actions.py - undo_plan stale-state guards
# ---------------------------------------------------------------------------
def test_undo_photo_context_repair_rejects_a_missing_photo(db):
    session, owner = db
    ghost = uuid.uuid4()
    plan = _executed_plan(session, owner, "photo_context_repair", {
        "repairs": [{"kind": "photo_time", "photo_id": str(ghost),
                     "before": None, "applied_after": "2024-01-01T00:00:00"}],
    })

    with pytest.raises(ValueError, match="部分已修复照片不存在"):
        actions.undo_plan(session, owner, plan.id)


def test_undo_photo_context_repair_rejects_a_photo_time_changed_afterwards(db):
    session, owner = db
    photo = _photo(session, owner, "time.jpg", when=datetime(2024, 5, 6, 7, 8, 9))
    plan = _executed_plan(session, owner, "photo_context_repair", {
        "repairs": [{"kind": "photo_time", "photo_id": str(photo.id),
                     "before": None, "applied_after": "2023-01-01T00:00:00"}],
    })

    with pytest.raises(ValueError, match="拍摄时间之后又被修改"):
        actions.undo_plan(session, owner, plan.id)


def test_undo_photo_context_repair_rejects_a_location_changed_afterwards(db):
    session, owner = db
    photo = _photo(session, owner, "loc.jpg")
    session.add(PhotoMetadata(photo_id=photo.id, city="上海"))
    session.commit()
    plan = _executed_plan(session, owner, "photo_context_repair", {
        "repairs": [{"kind": "photo_location", "photo_id": str(photo.id),
                     "before": {"city": "北京"}, "applied_after": {"city": "杭州"}}],
    })

    with pytest.raises(ValueError, match="地点之后又被修改"):
        actions.undo_plan(session, owner, plan.id)


def test_undo_photo_context_repair_rejects_an_unsupported_kind(db):
    session, owner = db
    photo = _photo(session, owner, "kind.jpg")
    plan = _executed_plan(session, owner, "photo_context_repair", {
        "repairs": [{"kind": "photo_palette", "photo_id": str(photo.id),
                     "before": None, "applied_after": None}],
    })

    with pytest.raises(ValueError, match="撤销数据包含不支持的操作"):
        actions.undo_plan(session, owner, plan.id)


def test_undo_photo_context_repair_restores_the_photo_time(db):
    session, owner = db
    photo = _photo(session, owner, "restore.jpg", when=datetime(2024, 5, 6, 7, 8, 9))
    plan = _executed_plan(session, owner, "photo_context_repair", {
        "repairs": [{"kind": "photo_time", "photo_id": str(photo.id),
                     "before": None,
                     "applied_after": photo.photo_time.isoformat()}],
    })

    undone = actions.undo_plan(session, owner, plan.id)

    assert undone.status == "undone"
    session.refresh(photo)
    assert photo.photo_time is None


def test_undo_photo_context_repair_creates_the_missing_metadata_row(db):
    session, owner = db
    photo = _photo(session, owner, "newmeta.jpg")
    # The photo has no metadata row yet, so the undo has to create one.
    assert session.query(PhotoMetadata).filter(PhotoMetadata.photo_id == photo.id).first() is None
    plan = _executed_plan(session, owner, "photo_context_repair", {
        "repairs": [{"kind": "photo_location", "photo_id": str(photo.id),
                     "before": {"city": "北京", "address": "天安门"},
                     "applied_after": actions._location_snapshot(None)}],
    })

    undone = actions.undo_plan(session, owner, plan.id)

    assert undone.status == "undone"
    metadata = session.query(PhotoMetadata).filter(PhotoMetadata.photo_id == photo.id).one()
    assert metadata.city == "北京"
    assert metadata.address == "天安门"


def test_undo_album_repair_rejects_a_missing_album(db):
    session, owner = db
    plan = _executed_plan(session, owner, "album_repair", {
        "repairs": [{"kind": "album_count", "album_id": str(uuid.uuid4()),
                     "before": 3, "applied_after": 1}],
    })

    with pytest.raises(ValueError, match="已修复的相册不存在"):
        actions.undo_plan(session, owner, plan.id)


def test_undo_album_repair_rejects_a_count_changed_afterwards(db):
    session, owner = db
    album = Album(id=uuid.uuid4(), name="trip", type="user", owner_id=owner, num_photos=7)
    session.add(album)
    session.commit()
    plan = _executed_plan(session, owner, "album_repair", {
        "repairs": [{"kind": "album_count", "album_id": str(album.id),
                     "before": 3, "applied_after": 1}],
    })

    with pytest.raises(ValueError, match="照片计数之后又被修改"):
        actions.undo_plan(session, owner, plan.id)


def test_undo_album_repair_rejects_a_cover_changed_afterwards(db):
    session, owner = db
    photo = _photo(session, owner, "cover.jpg")
    album = Album(id=uuid.uuid4(), name="trip", type="user", owner_id=owner,
                  num_photos=1, cover_id=photo.id)
    session.add(album)
    session.commit()
    plan = _executed_plan(session, owner, "album_repair", {
        "repairs": [{"kind": "album_cover", "album_id": str(album.id),
                     "before": None, "applied_after": str(uuid.uuid4())}],
    })

    with pytest.raises(ValueError, match="封面之后又被修改"):
        actions.undo_plan(session, owner, plan.id)


def test_undo_album_repair_rejects_an_unsupported_kind(db):
    session, owner = db
    album = Album(id=uuid.uuid4(), name="trip", type="user", owner_id=owner, num_photos=1)
    session.add(album)
    session.commit()
    plan = _executed_plan(session, owner, "album_repair", {
        "repairs": [{"kind": "album_title", "album_id": str(album.id),
                     "before": "x", "applied_after": "y"}],
    })

    with pytest.raises(ValueError, match="撤销数据包含不支持的操作"):
        actions.undo_plan(session, owner, plan.id)


def test_undo_album_repair_restores_the_count_and_the_cover(db):
    session, owner = db
    photo = _photo(session, owner, "cover.jpg")
    album = Album(id=uuid.uuid4(), name="trip", type="user", owner_id=owner,
                  num_photos=1, cover_id=photo.id)
    session.add(album)
    session.commit()
    plan = _executed_plan(session, owner, "album_repair", {
        "repairs": [
            {"kind": "album_count", "album_id": str(album.id), "before": 9, "applied_after": 1},
            {"kind": "album_cover", "album_id": str(album.id),
             "before": str(photo.id), "applied_after": str(photo.id)},
        ],
    })

    undone = actions.undo_plan(session, owner, plan.id)

    assert undone.status == "undone"
    session.refresh(album)
    assert album.num_photos == 9
    assert album.cover_id == photo.id


def test_undo_album_organize_removes_the_created_tag_relations_and_tags(db):
    session, owner = db
    photo = _photo(session, owner, "tag.jpg")
    tag = PhotoTag(id=uuid.uuid4(), tag_name="旅行", owner_id=owner)
    session.add(tag)
    session.flush()
    relation = PhotoTagRelation(photo_id=photo.id, tag_id=tag.id, confidence=1.0)
    session.add(relation)
    session.commit()
    relation_id, tag_id = relation.id, tag.id
    plan = _executed_plan(session, owner, "album_organize", {
        "created_album": True,
        "album_id": str(uuid.uuid4()),
        "album_before": None,
        "added_photo_ids": [],
        "tag_changes": [{"relation_id": relation_id, "created": True}],
        "created_tag_ids": [str(tag_id)],
    })

    undone = actions.undo_plan(session, owner, plan.id)

    assert undone.status == "undone"
    assert session.query(PhotoTagRelation).filter(PhotoTagRelation.id == relation_id).first() is None
    # The tag has no remaining relation, so it is removed as well.
    assert session.query(PhotoTag).filter(PhotoTag.id == tag_id).first() is None


def test_undo_album_organize_restores_a_previously_deleted_tag_relation(db):
    session, owner = db
    photo = _photo(session, owner, "tag.jpg")
    tag = PhotoTag(id=uuid.uuid4(), tag_name="旅行", owner_id=owner)
    session.add(tag)
    session.flush()
    relation = PhotoTagRelation(photo_id=photo.id, tag_id=tag.id, confidence=0.4, is_deleted=True)
    session.add(relation)
    session.commit()
    plan = _executed_plan(session, owner, "album_organize", {
        "created_album": True,
        "album_id": str(uuid.uuid4()),
        "album_before": None,
        "added_photo_ids": [],
        "tag_changes": [{"relation_id": relation.id, "created": False,
                         "was_deleted": True, "previous_confidence": 0.4}],
        "created_tag_ids": [],
    })

    undone = actions.undo_plan(session, owner, plan.id)

    assert undone.status == "undone"
    session.refresh(relation)
    assert relation.is_deleted is True
    assert relation.confidence == pytest.approx(0.4)


def test_undo_album_organize_skips_a_tag_relation_that_no_longer_exists(db):
    session, owner = db
    plan = _executed_plan(session, owner, "album_organize", {
        "created_album": True,
        "album_id": str(uuid.uuid4()),
        "album_before": None,
        "added_photo_ids": [],
        "tag_changes": [{"relation_id": 999999, "created": True}],
        "created_tag_ids": [],
    })

    undone = actions.undo_plan(session, owner, plan.id)

    assert undone.status == "undone"


def test_undo_album_organize_restores_the_album_and_removes_the_added_photos(db):
    session, owner = db
    kept = _photo(session, owner, "kept.jpg")
    added = _photo(session, owner, "added.jpg")
    album = Album(id=uuid.uuid4(), name="新相册", type="user", owner_id=owner, num_photos=2)
    session.add(album)
    session.flush()
    session.add_all([AlbumPhoto(album_id=album.id, photo_id=kept.id),
                      AlbumPhoto(album_id=album.id, photo_id=added.id)])
    session.commit()
    plan = _executed_plan(session, owner, "album_organize", {
        "created_album": False,
        "album_id": str(album.id),
        "album_before": {"name": "旧相册", "description": "旧简介", "cover_photo_id": str(kept.id)},
        "added_photo_ids": [str(added.id)],
        "tag_changes": [],
        "created_tag_ids": [],
    })

    undone = actions.undo_plan(session, owner, plan.id)

    assert undone.status == "undone"
    session.refresh(album)
    assert album.name == "旧相册"
    assert album.description == "旧简介"
    assert album.cover_id == kept.id
    remaining = {row.photo_id for row in
                 session.query(AlbumPhoto).filter(AlbumPhoto.album_id == album.id).all()}
    assert remaining == {kept.id}
    assert album.num_photos == 1


def test_undo_rejects_a_plan_type_that_cannot_be_undone(db):
    session, owner = db
    plan = _executed_plan(session, owner, "album_metadata_repair", {})

    with pytest.raises(ValueError, match="不可撤销"):
        actions.undo_plan(session, owner, plan.id)


def test_undo_rejects_a_plan_that_is_not_executed(db):
    session, owner = db
    plan = AgentActionPlan(
        id=uuid.uuid4(), user_id=owner, plan_type="album_organize", title="plan",
        status="proposed", operations={}, preview={},
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    session.add(plan)
    session.commit()

    with pytest.raises(ValueError, match="只有已执行的计划可以撤销"):
        actions.undo_plan(session, owner, plan.id)


# ---------------------------------------------------------------------------
# app/utils/portable_library.py - snapshot / integrity guards
# ---------------------------------------------------------------------------
def _library(root, *, library_id="11111111-2222-3333-4444-555555555555"):
    (root / "data").mkdir(parents=True, exist_ok=True)
    (root / "library.json").write_text(
        '{"libraryId": "%s", "schemaVersion": 1, "pathFormat": 1}' % library_id,
        encoding="utf-8",
    )
    connection = sqlite3.connect(root / "data" / "trailsnap.sqlite")
    connection.execute("CREATE TABLE IF NOT EXISTS users (id TEXT, settings TEXT)")
    connection.commit()
    connection.close()


def test_snapshot_refuses_a_linked_configuration_file(tmp_path):
    root = tmp_path / "library"
    _library(root)
    real = tmp_path / "real-config.json"
    real.write_text("{}", encoding="utf-8")
    link = root / "data" / "config.json"
    try:
        os.symlink(real, link)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not available on this platform")

    with pytest.raises(ValueError, match="Linked configuration"):
        portable_library.snapshot_library(root, tmp_path / "snapshot")


def test_snapshot_refuses_a_corrupted_database(tmp_path, monkeypatch):
    root = tmp_path / "library"
    _library(root)
    destination = tmp_path / "snapshot"
    real_connect = sqlite3.connect

    class _Rows:
        def __init__(self, rows):
            self._rows = rows

        def fetchall(self):
            return self._rows

    class _BrokenCheckConnection(sqlite3.Connection):
        """A healthy connection whose PRAGMA quick_check reports corruption."""

        def execute(self, sql, *args, **kwargs):
            if "quick_check" in sql:
                return _Rows([("corrupt",)])
            return super().execute(sql, *args, **kwargs)

    def fake_connect(*args, **kwargs):
        kwargs.setdefault("factory", _BrokenCheckConnection)
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", fake_connect)

    with pytest.raises(ValueError, match="Invalid database"):
        portable_library.snapshot_library(root, destination)


def test_prepare_rejects_a_portable_database_that_fails_the_integrity_check(tmp_path, monkeypatch):
    root = tmp_path / "library"
    _library(root)
    # prepare_portable_library needs a full manifest and a users/photos/tasks schema.
    (root / "library.json").write_text(json.dumps({
        "libraryId": "11111111-2222-3333-4444-555555555555",
        "schemaVersion": 1, "pathFormat": 1,
        "lastRoot": str(root),
    }), encoding="utf-8")
    connection = sqlite3.connect(root / "data" / "trailsnap.sqlite")
    connection.executescript(
        "CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, settings TEXT);"
        "CREATE TABLE IF NOT EXISTS photos (id TEXT PRIMARY KEY, owner_id TEXT, file_path TEXT,"
        " storage_root_id TEXT, storage_relative_path TEXT);"
        "CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, payload TEXT);"
    )
    connection.commit()
    connection.close()

    real_connect = sqlite3.connect

    class _Rows:
        def __init__(self, rows):
            self._rows = rows

        def fetchall(self):
            return self._rows

    class _BrokenCheckConnection(sqlite3.Connection):
        """A healthy connection whose PRAGMA quick_check reports corruption."""

        def execute(self, sql, *args, **kwargs):
            if "quick_check" in sql:
                return _Rows([("corrupt",)])
            return super().execute(sql, *args, **kwargs)

    def fake_connect(*args, **kwargs):
        kwargs.setdefault("factory", _BrokenCheckConnection)
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", fake_connect)
    monkeypatch.setenv("TS_DESKTOP_ROOT", str(root))

    with pytest.raises(ValueError, match="Portable database check failed"):
        portable_library.prepare_portable_library(root)



