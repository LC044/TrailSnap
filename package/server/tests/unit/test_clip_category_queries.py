"""Category reads stay bounded as the catalog grows."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import event

from app.api.clip_classification import categories
from app.db.models import User, Photo
from app.db.models.photo import FileType
from app.db.models.tag import PhotoTagRelation
from app.db.models.clip_classification import ClipCategory, ClipRuleRevision
from app.service import clip_classification as svc

pytestmark = [pytest.mark.smoke, pytest.mark.module_classification]


def test_initialized_catalog_reads_use_two_queries(face_sqlite_session):
    db = face_sqlite_session
    owner = User(username=str(uuid4()))
    other = User(username=str(uuid4()))
    db.add_all([owner, other])
    db.flush()
    owner_id = owner.id
    svc.ensure_presets(db, owner_id)
    svc.ensure_presets(db, other.id)
    cat = db.query(ClipCategory).filter_by(owner_id=owner_id).first()
    cat_id, tag_id = cat.id, cat.tag_id
    cat.revision = 2
    db.add(ClipRuleRevision(category_id=cat_id, revision=2,
                           descriptions=["edited"], strictness="strict", thresholds={"test": .8}))
    for photo_owner, deleted, relation_deleted in [
        (owner_id, False, False), (owner_id, True, False),
        (owner_id, False, True), (other.id, False, False),
    ]:
        photo = Photo(owner_id=photo_owner, filename="test.jpg", file_path=str(uuid4()),
                      file_type=FileType.image, is_deleted=deleted)
        db.add(photo)
        db.flush()
        db.add(PhotoTagRelation(photo_id=photo.id, tag_id=tag_id, is_deleted=relation_deleted))
    db.commit()
    db.expunge_all()
    queries = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        queries.append(statement)

    event.listen(db.bind, "before_cursor_execute", capture)
    try:
        result = categories(db, SimpleNamespace(id=owner_id))
    finally:
        event.remove(db.bind, "before_cursor_execute", capture)
    assert result.code == 0
    assert len(result.data["categories"]) == len(svc.load_catalog()["categories"])
    row = next(c for c in result.data["categories"] if c["id"] == str(cat_id))
    assert row["count"] == 1
    assert row["descriptions"] == ["edited"] and row["revision"] == 2
    assert row["calibration"] == {"status": "custom"}
    assert len(queries) == 2, queries
    assert all(q.lstrip().upper().startswith("SELECT") for q in queries)


def test_complete_presets_skip_lock_and_preserve_deleted(face_sqlite_session, monkeypatch):
    db = face_sqlite_session
    owner = User(username=str(uuid4()))
    db.add(owner)
    db.flush()
    owner_id = owner.id
    assert svc.ensure_presets(db, owner_id) is True
    db.commit()
    cat = db.query(ClipCategory).filter_by(owner_id=owner_id).first()
    cat.is_deleted = True
    db.commit()
    from sqlalchemy.orm import Query

    def unexpected_lock(*args, **kwargs):
        pytest.fail("complete presets must not lock the owner")

    monkeypatch.setattr(Query, "with_for_update", unexpected_lock)
    assert svc.ensure_presets(db, owner_id) is False
    assert db.query(ClipCategory).filter_by(owner_id=owner_id, is_deleted=True).count() == 1


def test_committed_presets_skip_all_sql_across_sessions(face_sqlite_session):
    from sqlalchemy.orm import Session

    db = face_sqlite_session
    owner = User(username=str(uuid4()))
    db.add(owner)
    db.flush()
    owner_id = owner.id
    svc.ensure_presets(db, owner_id)
    db.commit()
    queries = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        queries.append(statement)

    event.listen(db.bind, "before_cursor_execute", capture)
    try:
        with Session(db.bind) as other:
            for _ in range(100):
                assert svc.ensure_presets(other, owner_id) is False
    finally:
        event.remove(db.bind, "before_cursor_execute", capture)
    assert queries == []


@pytest.mark.parametrize("finish", ["rollback", "close"])
def test_uncommitted_presets_are_not_cached(face_sqlite_session, finish):
    db = face_sqlite_session
    owner = User(username=str(uuid4()))
    db.add(owner)
    db.commit()
    owner_id = owner.id
    assert svc.ensure_presets(db, owner_id)
    assert not svc.ensure_presets(db, owner_id)
    getattr(db, finish)()
    assert db.query(ClipCategory).count() == 0
    assert svc.ensure_presets(db, owner_id)
    db.commit()
    assert not svc.ensure_presets(db, owner_id)


def test_savepoint_commit_is_not_published_before_outer_commit(face_sqlite_session):
    db = face_sqlite_session
    owner = User(username=str(uuid4()))
    db.add(owner)
    db.commit()
    owner_id = owner.id
    db.commit()
    # SQLite legacy transaction mode otherwise releases an outermost savepoint
    # as a real commit, defeating the intended outer rollback in this test.
    db.connection().exec_driver_sql("BEGIN")
    with db.begin_nested():
        assert svc.ensure_presets(db, owner_id)
    assert (str(owner_id), svc.load_catalog()["version"]) not in svc._initialized_presets.get(db.bind, {})
    db.rollback()
    assert db.query(ClipCategory).count() == 0
    assert svc.ensure_presets(db, owner_id)


def test_preset_cache_isolates_users_and_catalog_versions(face_sqlite_session, monkeypatch):
    db = face_sqlite_session
    owners = [User(username=str(uuid4())) for _ in range(2)]
    db.add_all(owners)
    db.flush()
    first_id, second_id = [owner.id for owner in owners]
    assert svc.ensure_presets(db, first_id)
    db.commit()
    assert svc.ensure_presets(db, second_id)
    db.commit()
    data = svc.load_catalog()
    extra = dict(data["categories"][0], key="new-version-key", name="new-version-name")
    updated = dict(data, version=data["version"] + 1, categories=[*data["categories"], extra])
    monkeypatch.setattr(svc, "load_catalog", lambda: updated)
    assert svc.ensure_presets(db, first_id)
    db.commit()
    assert db.query(ClipCategory).filter_by(owner_id=first_id, preset_key=extra["key"]).count() == 1
    assert db.query(ClipCategory).filter_by(owner_id=second_id, preset_key=extra["key"]).count() == 0


def test_preset_cache_isolates_database_engines(face_sqlite_session, tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.db.base import Base

    db = face_sqlite_session
    owner = User(username=str(uuid4()))
    db.add(owner)
    db.flush()
    owner_id = owner.id
    svc.ensure_presets(db, owner_id)
    db.commit()
    engine = create_engine(f"sqlite:///{(tmp_path / 'other.sqlite').as_posix()}")
    try:
        Base.metadata.create_all(engine)
        with Session(engine) as other:
            other.add(User(id=owner_id, username=str(uuid4())))
            other.commit()
            assert svc.ensure_presets(other, owner_id)
            other.commit()
    finally:
        engine.dispose()
