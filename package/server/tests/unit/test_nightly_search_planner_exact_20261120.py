"""Exact-entity search planning for the agent."""
from uuid import uuid4

import pytest

from app.db.models.face import FaceIdentity
from app.db.models.photo import Photo
from app.db.models.photo_metadata import PhotoMetadata
from app.db.models.photo import FileType
from app.service.agent.search_planner import exact_entity_plan

pytestmark = [pytest.mark.smoke, pytest.mark.module_agent]


def _photo(db, owner_id, filename="photo.jpg"):
    photo = Photo(
        id=uuid4(),
        owner_id=owner_id,
        filename=filename,
        photo_time=None,
        file_path="/tmp/photo.jpg",
        file_type=FileType.image,
    )
    db.add(photo)
    db.flush()
    return photo


def test_blank_text_produces_no_plan(face_sqlite_session):
    assert exact_entity_plan(face_sqlite_session, uuid4(), "   ") is None


def test_visual_environment_is_never_a_place(face_sqlite_session):
    assert exact_entity_plan(face_sqlite_session, uuid4(), "海边") is None


def test_unknown_text_produces_no_plan(face_sqlite_session):
    assert exact_entity_plan(face_sqlite_session, uuid4(), "Atlantis") is None


def test_matching_city_produces_a_location_plan(face_sqlite_session):
    owner_id = uuid4()
    photo = _photo(face_sqlite_session, owner_id)
    face_sqlite_session.add(PhotoMetadata(photo_id=photo.id, city="Hangzhou"))
    face_sqlite_session.flush()

    plan = exact_entity_plan(face_sqlite_session, owner_id, "Hangzhou")
    assert plan is not None
    assert plan.location == "Hangzhou"


def test_a_unique_identity_produces_a_people_plan(face_sqlite_session):
    owner_id = uuid4()
    identity = FaceIdentity(id=uuid4(), owner_id=owner_id, identity_name="Alice")
    face_sqlite_session.add(identity)
    face_sqlite_session.flush()

    plan = exact_entity_plan(face_sqlite_session, owner_id, "Alice")
    assert plan is not None
    assert plan.people == ["Alice"]


def test_ambiguous_identities_produce_no_plan(face_sqlite_session):
    owner_id = uuid4()
    for _ in range(2):
        face_sqlite_session.add(FaceIdentity(id=uuid4(), owner_id=owner_id, identity_name="Bob"))
    face_sqlite_session.flush()

    assert exact_entity_plan(face_sqlite_session, owner_id, "Bob") is None


def test_a_deleted_photo_is_not_a_location_match(face_sqlite_session):
    owner_id = uuid4()
    photo = _photo(face_sqlite_session, owner_id)
    photo.is_deleted = True
    face_sqlite_session.add(PhotoMetadata(photo_id=photo.id, city="Hangzhou"))
    face_sqlite_session.flush()

    assert exact_entity_plan(face_sqlite_session, owner_id, "Hangzhou") is None
