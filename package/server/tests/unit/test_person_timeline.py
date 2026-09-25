"""Person timeline uses owned photo evidence and applies story exclusions."""

from datetime import datetime
from uuid import uuid4

import pytest

from app.db.models.face import Face, FaceIdentity
from app.db.models.person_timeline import PersonTimelineHide
from app.db.models.photo import FileType, Photo
from app.db.models.user import User
from app.service import person_timeline
from app.crud.face import merge_identities
from app.service.agent.album_p0 import build_person_timeline, create_artifact

pytestmark = [pytest.mark.smoke, pytest.mark.module_face]


def test_pair_timeline_counts_distinct_years_and_hides_only_pair_scope(face_sqlite_session):
    db = face_sqlite_session
    owner = User(id=uuid4(), username="timeline-owner", hashed_password="x")
    other = User(id=uuid4(), username="timeline-other", hashed_password="x")
    db.add_all([owner, other])
    db.flush()
    alice = FaceIdentity(id=uuid4(), identity_name="Alice", tags=["朋友"], owner_id=owner.id, is_deleted=False, is_hidden=False)
    bob = FaceIdentity(id=uuid4(), identity_name="Bob", tags=["同事"], owner_id=owner.id, is_deleted=False, is_hidden=False)
    db.add_all([alice, bob])
    db.flush()

    def photo(name, time, people, photo_owner=owner):
        row = Photo(id=uuid4(), filename=name, file_path=f"/{name}", file_type=FileType.image,
                    owner_id=photo_owner.id, photo_time=time, is_deleted=False)
        db.add(row)
        db.flush()
        for person in people:
            db.add(Face(photo_id=row.id, face_identity_id=person.id, is_deleted=False))
        db.flush()
        return row

    first = photo("first", datetime(2020, 5, 1), [alice, bob])
    second = photo("second", datetime(2023, 6, 1), [alice, bob])
    photo("solo", datetime(2022, 1, 1), [alice])
    photo("undated", None, [alice, bob])
    photo("foreign", datetime(2024, 1, 1), [alice, bob], other)
    db.commit()

    a, b, people = person_timeline.scope(db, owner.id, alice.id, bob.id)
    result = person_timeline.timeline(db, owner.id, a, b, people)
    assert result["photo_count"] == 2
    assert result["year_count"] == 2
    assert {person["name"]: person["tags"] for person in result["people"]} == {"Alice": ["朋友"], "Bob": ["同事"]}
    assert {item["year"] for item in result["years"]} == {2020, 2023}

    db.add(PersonTimelineHide(id=uuid4(), owner_id=owner.id, person_a_id=a, person_b_id=b,
                              start_at=datetime(2020, 5, 1), end_at=datetime(2020, 5, 2)))
    db.commit()
    result = person_timeline.timeline(db, owner.id, a, b, people)
    assert result["photo_count"] == 1
    assert result["year_count"] == 1
    assert person_timeline.year_detail(db, owner.id, a, b, 2020, 0, 10)["total"] == 0
    solo_a, solo_b, solo_people = person_timeline.scope(db, owner.id, alice.id, None)
    solo = person_timeline.timeline(db, owner.id, solo_a, solo_b, solo_people)
    assert solo["photo_count"] == 3
    assert {first.id, second.id}.issubset({row.id for row in person_timeline.photo_query(db, owner.id, solo_a, solo_b).all()})

    db.add(PersonTimelineHide(id=uuid4(), owner_id=owner.id, person_a_id=solo_a, person_b_id=solo_b,
                              start_at=datetime(2020, 5, 1), end_at=datetime(2020, 5, 2)))
    db.commit()
    assert build_person_timeline(db, str(owner.id), str(alice.id))["total_photo_count"] == 3  # undated remains counted
    assert build_person_timeline(db, str(owner.id), str(alice.id))["dated_photo_count"] == 2
    with pytest.raises(ValueError, match="已隐藏"):
        create_artifact(db, str(owner.id), None, "person_story", "Test", {}, [str(first.id)], [])


def test_merge_keeps_story_exclusions(face_sqlite_session):
    db = face_sqlite_session
    owner = User(id=uuid4(), username="timeline-merge-owner", hashed_password="x")
    target = FaceIdentity(id=uuid4(), identity_name="Target", owner_id=owner.id, is_deleted=False, is_hidden=False)
    source = FaceIdentity(id=uuid4(), identity_name="Source", owner_id=owner.id, is_deleted=False, is_hidden=False)
    db.add_all([owner, target, source])
    db.flush()
    db.add(PersonTimelineHide(id=uuid4(), owner_id=owner.id, person_a_id=source.id,
        person_b_id=person_timeline.SOLO, start_at=datetime(2020, 1, 1), end_at=datetime(2020, 1, 2)))
    db.commit()

    assert merge_identities(db, target.id, [source.id], owner.id)
    assert db.query(PersonTimelineHide).filter_by(person_a_id=target.id).count() == 1
