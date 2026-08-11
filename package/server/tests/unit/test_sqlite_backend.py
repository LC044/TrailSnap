"""SQLite smoke tests for desktop persistence and in-memory vector search."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import StatementError
from sqlalchemy.orm import sessionmaker

import app.db.models  # noqa: F401
from app.crud.crud_vector import search_similar_vectors
from app.db.base import Base
from app.db.bootstrap import ensure_desktop_admin
from app.db.models.image_vector import ImageVector
from app.db.models.photo import FileType, Photo
from app.db.models.user import User

pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


@pytest.fixture()
def sqlite_session(tmp_path):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'trailsnap.sqlite').as_posix()}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def test_sqlite_uuid_and_vector_round_trip(sqlite_session):
    user = User(
        username="sqlite-user",
        email="sqlite@example.com",
        hashed_password="unused",
        is_active=True,
    )
    sqlite_session.add(user)
    sqlite_session.flush()

    vectors = ([1.0, 0.0] + [0.0] * 510, [0.0, 1.0] + [0.0] * 510)
    photos = []
    for index, embedding in enumerate(vectors):
        photo = Photo(
            filename=f"photo-{index}.jpg",
            file_path=f"/photos/photo-{index}.jpg",
            file_type=FileType.image,
            owner_id=user.id,
        )
        sqlite_session.add(photo)
        sqlite_session.flush()
        sqlite_session.add(ImageVector(photo_id=photo.id, embedding=embedding))
        photos.append(photo)
    sqlite_session.commit()

    results = search_similar_vectors(
        sqlite_session,
        [1.0, 0.0] + [0.0] * 510,
        user_id=user.id,
    )

    assert isinstance(photos[0].id, UUID)
    assert results[0][0].photo_id == photos[0].id
    assert results[0][1] == pytest.approx(0.0)
    assert results[1][1] == pytest.approx(1.0)


def test_desktop_admin_is_created_once(sqlite_session, monkeypatch):
    monkeypatch.setenv("TS_DESKTOP", "1")

    first = ensure_desktop_admin(sqlite_session)
    second = ensure_desktop_admin(sqlite_session)

    assert first.id == second.id
    assert first.is_superuser is True
    assert sqlite_session.query(User).count() == 1


def test_database_vector_rejects_wrong_dimensions(sqlite_session):
    photo_id = uuid4()
    sqlite_session.add(ImageVector(photo_id=photo_id, embedding=[1.0, 2.0]))

    with pytest.raises(StatementError, match="512-dimensional"):
        sqlite_session.commit()
