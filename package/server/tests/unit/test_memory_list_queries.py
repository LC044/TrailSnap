"""List contracts and bounded loading on SQLite and PostgreSQL."""

import os
from datetime import date, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import Session

import app.db.models  # noqa: F401
from app.db.base import Base
from app.db.models.chapter import LifeChapter
from app.db.models.face import FaceIdentity
from app.db.models.memory import Memory, MemoryEvidence, MemoryOrigin, MemoryPerson, MemoryPhoto, MemoryPlace, MemoryStatus
from app.db.models.photo import FileType, Photo
from app.db.models.user import User
from app.service import chapter, memory


pytestmark = [pytest.mark.smoke, pytest.mark.module_album]


@pytest.fixture(params=["sqlite", pytest.param("postgresql", marks=pytest.mark.postgres)])
def query_db(request, face_sqlite_session):
    if request.param == "sqlite":
        yield face_sqlite_session
        return
    if "postgres" not in request.config.getoption("markexpr"):
        pytest.skip("Run with -m postgres against the PostgreSQL test database")
    url = os.environ.get("TS_DB_URL") or os.environ.get("DB_URL", "")
    if not url.startswith("postgresql"):
        pytest.skip("TS_DB_URL must point to the PostgreSQL test database")
    engine = create_engine(url, connect_args={"connect_timeout": 5})
    # DDL and test writes live in an isolated schema and are rolled back even
    # when a service commits its session. Existing test data stays untouched.
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            schema = "memory_query_test_" + uuid4().hex
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            connection.execute(text(f'SET LOCAL search_path TO "{schema}", public'))
            Base.metadata.create_all(connection)
            with Session(connection, join_transaction_mode="create_savepoint") as db:
                yield db
        finally:
            transaction.rollback()
    engine.dispose()


def seed(db):
    owner = User(id=uuid4(), username="query-owner", hashed_password="x")
    stranger = User(id=uuid4(), username="query-stranger", hashed_password="x")
    db.add_all([owner, stranger])
    db.flush()
    row = Memory(id=uuid4(), owner_id=owner.id, status=MemoryStatus.CANDIDATE,
                 origin=MemoryOrigin.MANUAL, title="many photos", start_time=datetime(2026, 1, 1))
    row.places = [MemoryPlace(name="杭州"), MemoryPlace(name="西湖")]
    row.evidence = [MemoryEvidence(evidence_type="time", summary="连续拍摄"),
                    MemoryEvidence(evidence_type="place", summary="同一地点")]
    row.people = [MemoryPerson(identity=FaceIdentity(owner_id=owner.id, identity_name="甲")),
                  MemoryPerson(identity=FaceIdentity(owner_id=owner.id, identity_name="乙"))]
    db.add(row)
    db.flush()
    # Null dates must stay ahead of dated photos, as in detail serialization.
    for index in range(12):
        photo = Photo(id=uuid4(), owner_id=owner.id, filename=f"{index}.jpg",
                      file_path=f"/test/{index}.jpg", file_type=FileType.image,
                      photo_time=None if index < 2 else datetime(2026, 1, 1) + timedelta(hours=index))
        db.add(photo)
        db.flush()
        row.photo_links.append(MemoryPhoto(photo=photo, sort_order=index))
    db.add_all([
        Memory(owner_id=owner.id, title="empty", status=MemoryStatus.CANDIDATE, origin=MemoryOrigin.MANUAL),
        Memory(owner_id=stranger.id, title="private", status=MemoryStatus.CANDIDATE, origin=MemoryOrigin.MANUAL),
        Memory(owner_id=owner.id, title="ignored", status=MemoryStatus.IGNORED, origin=MemoryOrigin.MANUAL),
        Memory(owner_id=owner.id, title="deleted", status=MemoryStatus.DELETED, origin=MemoryOrigin.MANUAL),
    ])
    db.flush()
    return owner.id, row.id


def test_list_preserves_response_without_loading_photos(query_db):
    db = query_db
    owner_id, memory_id = seed(db)
    expected = memory.serialize(db, memory.get_detail(db, memory_id, owner_id))
    db.expunge_all()
    statements = []
    def capture(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement)
    event.listen(db.get_bind(), "before_cursor_execute", capture)
    try:
        items, total = memory.list_items(db, owner_id, MemoryStatus.CANDIDATE)
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", capture)
    assert total == 2
    assert items[0] == expected
    assert items[1]["photo_count"] == 0
    assert items[1]["preview_photo_ids"] == []
    assert len(items[0]["preview_photo_ids"]) == 4
    assert len(statements) <= 6
    assert not any(isinstance(item, (Photo, MemoryPhoto)) for item in db.identity_map.values())
    assert all("photo_metadata" not in sql for sql in statements)
    assert all("photo_links" in inspect(item).unloaded for item in db.identity_map.values() if isinstance(item, Memory))
    page, total = memory.list_items(db, owner_id, MemoryStatus.CANDIDATE, skip=1, limit=1)
    assert total == 2 and [item["title"] for item in page] == ["empty"]
    assert memory.list_items(db, owner_id, MemoryStatus.CANDIDATE, skip=2) == ([], 2)


def test_status_counts_do_not_load_relationships(query_db):
    owner_id, _ = seed(query_db)
    query_db.expunge_all()
    assert memory.count_owned(query_db, owner_id) == {"candidate": 2, "confirmed": 0, "ignored": 1}
    assert not query_db.identity_map
    assert memory.count_owned(query_db, uuid4()) == {"candidate": 0, "confirmed": 0, "ignored": 0}


def test_chapter_counts_skip_serialization_and_keep_visibility(query_db, monkeypatch):
    db = query_db
    owner_id, _ = seed(db)
    db.add_all([
        LifeChapter(owner_id=owner_id, title="visible", status="candidate", start_date=date(2026, 1, 1)),
        LifeChapter(owner_id=owner_id, title="hidden", status="candidate", is_hidden=True, start_date=date(2026, 1, 1)),
        LifeChapter(owner_id=owner_id, title="confirmed", status="confirmed", start_date=date(2026, 1, 1)),
    ])
    db.flush()
    visible = chapter.list_owned(db, owner_id, status="confirmed")
    assert visible["items"][0]["photo_count"] == 10
    assert visible["items"][0]["event_count"] == 0
    monkeypatch.setattr(chapter, "serialize", lambda *args, **kwargs: pytest.fail("count serialized a chapter"))
    assert chapter.list_owned(db, owner_id, status="candidate", counts_only=True) == {
        "items": [], "total": 1, "skip": 0, "limit": 20,
    }
