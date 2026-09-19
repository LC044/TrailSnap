"""SQLite-backed tests for the smart album overview aggregate queries."""

import uuid
from datetime import datetime

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.crud.album import get_smart_album_overview
from app.db.base import Base
from app.db.models.face import Face, FaceIdentity
from app.db.models.photo import FileType, Photo
from app.db.models.photo_metadata import PhotoMetadata
from app.db.models.scene import Scene
from app.db.models.tag import PhotoTag, PhotoTagRelation
from app.db.models.user import User


pytestmark = [pytest.mark.smoke, pytest.mark.module_album]


def _photo(photo_id, owner_id, filename, taken_at):
    return Photo(
        id=photo_id,
        owner_id=owner_id,
        filename=filename,
        file_path=f"/photos/{filename}.jpg",
        file_type=FileType.image,
        photo_time=taken_at,
        upload_time=taken_at,
        is_deleted=False,
    )


def test_smart_album_overview_uses_three_queries_and_returns_covers():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            User.__table__,
            Scene.__table__,
            Photo.__table__,
            PhotoMetadata.__table__,
            FaceIdentity.__table__,
            Face.__table__,
            PhotoTag.__table__,
            PhotoTagRelation.__table__,
        ],
    )
    query_count = 0

    @event.listens_for(engine, "before_cursor_execute")
    def count_queries(_conn, _cursor, _statement, _parameters, _context, _executemany):
        nonlocal query_count
        query_count += 1

    Session = sessionmaker(bind=engine)
    with Session() as db:
        owner_id = uuid.uuid4()
        db.add(User(id=owner_id, username="u", email="u@example.com", hashed_password="x"))

        photo_ids = [uuid.uuid4() for _ in range(4)]
        taken_times = [
            datetime(2026, 1, 4),
            datetime(2026, 1, 3),
            datetime(2026, 1, 2),
            datetime(2026, 1, 1),
        ]
        for photo_id, taken_at in zip(photo_ids, taken_times):
            db.add(_photo(photo_id, owner_id, f"p-{photo_id.hex[:6]}", taken_at))

        db.add(PhotoMetadata(photo_id=photo_ids[0], city="Shanghai"))
        db.add(PhotoMetadata(photo_id=photo_ids[1], city="Shanghai"))
        db.add(PhotoMetadata(photo_id=photo_ids[2], city="Beijing"))
        db.add(PhotoMetadata(photo_id=photo_ids[3], city=""))

        identity = FaceIdentity(
            id=uuid.uuid4(),
            identity_name="Alice",
            owner_id=owner_id,
            is_deleted=False,
            is_hidden=False,
        )
        db.add(identity)
        db.flush()
        first_face = Face(
            photo_id=photo_ids[0],
            face_identity_id=identity.id,
            face_rect=[0.2, 0.2, 0.5, 0.5],
            is_deleted=False,
        )
        default_face = Face(
            photo_id=photo_ids[1],
            face_identity_id=identity.id,
            face_rect=[0.3, 0.3, 0.6, 0.6],
            is_deleted=False,
        )
        db.add_all([first_face, default_face])
        db.flush()
        identity.default_face_id = default_face.id

        tag = PhotoTag(
            id=uuid.uuid4(),
            tag_name="travel",
            owner_id=owner_id,
            cover_id=photo_ids[3],
            is_deleted=False,
        )
        db.add(tag)
        db.flush()
        db.add_all(
            [
                PhotoTagRelation(
                    photo_id=photo_ids[0],
                    tag_id=tag.id,
                    created_at=datetime(2026, 1, 1),
                    is_deleted=False,
                ),
                PhotoTagRelation(
                    photo_id=photo_ids[1],
                    tag_id=tag.id,
                    created_at=datetime(2026, 1, 2),
                    is_deleted=False,
                ),
            ]
        )
        db.commit()

        query_count = 0
        overview = get_smart_album_overview(db, owner_id)

    assert query_count == 3

    assert overview.people.item_count == 1
    assert overview.people.photo_count == 2
    assert len(overview.people.representatives) == 1
    assert overview.people.representatives[0].name == "Alice"
    assert overview.people.representatives[0].photo_id == photo_ids[1]
    assert overview.people.representatives[0].face_rect == [0.3, 0.3, 0.6, 0.6]
    assert overview.people.representatives[0].photo_count == 2

    assert overview.location.item_count == 2
    assert overview.location.photo_count == 3
    assert [item.name for item in overview.location.representatives] == ["Shanghai", "Beijing"]
    assert overview.location.representatives[0].photo_id == photo_ids[0]
    assert overview.location.representatives[0].photo_count == 2
    assert overview.location.representatives[1].photo_id == photo_ids[2]
    assert overview.location.representatives[1].photo_count == 1

    assert overview.classification.item_count == 1
    assert overview.classification.photo_count == 2
    assert len(overview.classification.representatives) == 1
    assert overview.classification.representatives[0].name == "travel"
    assert overview.classification.representatives[0].photo_id == photo_ids[3]
    assert overview.classification.representatives[0].photo_count == 2
