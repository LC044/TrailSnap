"""SQLite smoke tests for desktop persistence and in-memory vector search."""

from datetime import datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import StatementError
from sqlalchemy.orm import sessionmaker

import app.db.models  # noqa: F401
from app.crud.crud_vector import search_similar_vectors
from app.crud.dashboard import get_emotion_calendar_stats, get_heatmap_stats
from app.crud.location import get_timeline_nodes
from app.crud.location_stats import get_heatmap_range, get_places
from app.crud.moment import get_day_locations
from app.db.base import Base
from app.db.bootstrap import (
    DESKTOP_ADMIN_EMAIL,
    DESKTOP_ADMIN_USERNAME,
    LEGACY_DESKTOP_ADMIN_EMAIL,
    ensure_desktop_admin,
)
from app.db.models.face import Face, FaceIdentity
from app.db.models.image_description import ImageDescription
from app.db.models.image_vector import ImageVector
from app.db.models.photo import FileType, ImageType, Photo
from app.db.models.photo_metadata import PhotoMetadata
from app.db.models.user import User
from app.schemas.user import UserResponse

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


def test_sqlite_uuid_and_vector_search_returns_scalar_distances(sqlite_session):
    """SQLite's in-memory fallback also returns ``(ImageVector, float)`` rows."""
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
    assert all(isinstance(distance, float) for _, distance in results)
    assert results[0][1] == pytest.approx(0.0)
    assert results[1][1] == pytest.approx(1.0)


def test_desktop_admin_is_created_once(sqlite_session, monkeypatch):
    monkeypatch.setenv("TS_DESKTOP", "1")

    first = ensure_desktop_admin(sqlite_session)
    second = ensure_desktop_admin(sqlite_session)

    assert first.id == second.id
    assert first.email == DESKTOP_ADMIN_EMAIL
    assert first.is_superuser is True
    assert UserResponse.model_validate(first).email == DESKTOP_ADMIN_EMAIL
    assert sqlite_session.query(User).count() == 1


def test_desktop_admin_repairs_legacy_reserved_email(sqlite_session, monkeypatch):
    monkeypatch.setenv("TS_DESKTOP", "1")
    legacy_user = User(
        username=DESKTOP_ADMIN_USERNAME,
        email=LEGACY_DESKTOP_ADMIN_EMAIL,
        hashed_password="unused",
        is_active=True,
        is_superuser=True,
    )
    sqlite_session.add(legacy_user)
    sqlite_session.commit()

    user = ensure_desktop_admin(sqlite_session)

    assert user.id == legacy_user.id
    assert user.email == DESKTOP_ADMIN_EMAIL
    assert UserResponse.model_validate(user).email == DESKTOP_ADMIN_EMAIL
    assert sqlite_session.query(User).count() == 1


def test_database_vector_rejects_wrong_dimensions(sqlite_session):
    photo_id = uuid4()
    sqlite_session.add(ImageVector(photo_id=photo_id, embedding=[1.0, 2.0]))

    with pytest.raises(StatementError, match="512-dimensional"):
        sqlite_session.commit()


def test_face_assignment_uses_in_memory_cosine_distance_on_sqlite(sqlite_session, monkeypatch):
    from app.service.face_cluster import FaceClusterService

    user = User(username="face-user", email="face@example.com", hashed_password="unused")
    sqlite_session.add(user); sqlite_session.flush()
    identity = FaceIdentity(identity_name="Known", owner_id=user.id)
    sqlite_session.add(identity); sqlite_session.flush()
    reference_photo = Photo(filename="ref.jpg", file_path="/ref.jpg", file_type=FileType.image, owner_id=user.id)
    target_photo = Photo(filename="target.jpg", file_path="/target.jpg", file_type=FileType.image, owner_id=user.id)
    sqlite_session.add_all([reference_photo, target_photo]); sqlite_session.flush()
    reference = Face(photo_id=reference_photo.id, face_identity_id=identity.id, face_feature=[1.0] + [0.0] * 511)
    target = Face(photo_id=target_photo.id, face_feature=[0.99, 0.01] + [0.0] * 510)
    sqlite_session.add_all([reference, target]); sqlite_session.commit()
    cfg = type("Cfg", (), {"ai": type("AI", (), {"face_cluster_threshold": 0.4})()})()
    monkeypatch.setattr("app.service.face_cluster.config_manager.get_user_config", lambda *_: cfg)

    matched = FaceClusterService(sqlite_session).assign_face_to_identity(
        target.id, target.face_feature, user.id
    )

    assert matched == identity.id


def test_on_this_day_vector_sort_works_on_sqlite(sqlite_session, monkeypatch):
    from app.crud import photo as photo_crud

    user = User(username="memory-user", email="memory@example.com", hashed_password="unused")
    sqlite_session.add(user); sqlite_session.flush()
    photo = Photo(
        filename="memory.jpg", file_path="/memory.jpg", file_type=FileType.image,
        owner_id=user.id, photo_time=datetime(2020, 8, 12), image_type=ImageType.CAMERA,
    )
    sqlite_session.add(photo); sqlite_session.flush()
    sqlite_session.add(ImageDescription(photo_id=photo.id, memory_score=80, quality_score=70))
    sqlite_session.add(ImageVector(photo_id=photo.id, embedding=[1.0] + [0.0] * 511))
    sqlite_session.commit()
    monkeypatch.setattr(photo_crud.POSITIVE_SENTIMENT_VECTOR, "embedding", [1.0] + [0.0] * 511)

    result = photo_crud.get_on_this_day_photos(sqlite_session, user.id, 8, 12, 2026)

    assert [item.id for item in result] == [photo.id]


def test_date_statistics_work_on_sqlite(sqlite_session):
    user = User(username="date-user", email="date@example.com", hashed_password="unused")
    sqlite_session.add(user)
    sqlite_session.flush()

    photos = [
        Photo(
            filename=f"date-{index}.jpg",
            file_path=f"/date-{index}.jpg",
            file_type=FileType.image,
            owner_id=user.id,
            photo_time=photo_time,
        )
        for index, photo_time in enumerate(
            (datetime(2025, 8, 5, 10), datetime(2025, 8, 5, 18), datetime(2025, 8, 6, 9))
        )
    ]
    sqlite_session.add_all(photos)
    sqlite_session.flush()
    sqlite_session.add_all([
        PhotoMetadata(photo_id=photos[0].id, city="上海", province="上海", latitude=31.23, longitude=121.47),
        PhotoMetadata(photo_id=photos[1].id, city="上海", province="上海", latitude=31.24, longitude=121.48),
        PhotoMetadata(photo_id=photos[2].id, city="杭州", province="浙江", latitude=30.27, longitude=120.15),
    ])
    sqlite_session.commit()

    timeline = get_timeline_nodes(sqlite_session, user.id)
    heatmap = get_heatmap_stats(sqlite_session, user.id, year=2025)
    emotion = get_emotion_calendar_stats(sqlite_session, user.id, year=2025)
    moments = get_day_locations(
        sqlite_session,
        user.id,
        datetime(2025, 8, 5),
        datetime(2025, 8, 7),
    )
    places = get_places(sqlite_session, user.id)
    location_heatmap = get_heatmap_range(sqlite_session, user.id)

    assert timeline.total == 2
    assert {node.startDate for node in timeline.nodes} == {"2025-08-05", "2025-08-06"}
    assert [(item.date, item.count) for item in heatmap.data] == [
        ("2025-08-05", 2),
        ("2025-08-06", 1),
    ]
    assert [(item.date, item.photo_count) for item in emotion.data] == [
        ("2025-08-05", 2),
        ("2025-08-06", 1),
    ]
    assert [item["day"].isoformat() for item in moments] == ["2025-08-06", "2025-08-05"]
    assert {item.name: item.visit_dates for item in places.top_places} == {
        "上海": ["2025-08-05"],
        "杭州": ["2025-08-06"],
    }
    assert [(item.date, item.count) for item in location_heatmap.data] == [
        ("2025-08-05", 2),
        ("2025-08-06", 1),
    ]
