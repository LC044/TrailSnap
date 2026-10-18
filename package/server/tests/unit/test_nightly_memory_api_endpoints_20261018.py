# Nightly watch 2026-10-18 round 3: HTTP-layer coverage for the memory domain.
#
# The service module ``app.service.memory`` keeps a high missed-line count
# (162 lines uncovered, 60% rate) and ``app.api.memory`` (223 lines) was the
# highest untested FastAPI router for this domain. This file targets the
# FastAPI handlers and exercises the underlying service paths so both files
# climb meaningfully off the bottom of the gap list.

from datetime import datetime
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.api.memory import router
from app.db.models.face import FaceIdentity
from app.db.models.memory import (
    Memory,
    MemoryPhoto,
    MemoryOrigin,
    MemoryStatus,
)
from app.db.models.photo import FileType, Photo
from app.db.models.trip import FlightTicket, TrainTicket
from app.db.models.user import User
from app.dependencies import get_db
from app.service import memory as memory_service

pytestmark = [pytest.mark.smoke, pytest.mark.module_album]


def _build_client(db, owner):
    app = FastAPI()
    app.include_router(router, prefix="/api/memory")
    app.dependency_overrides[get_current_user] = lambda: owner
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def _seed_owner(db, *, username="memory-api"):
    owner = User(id=uuid4(), username=username, hashed_password="x", is_active=True)
    stranger = User(id=uuid4(), username=username + "-stranger", hashed_password="x", is_active=True)
    db.add_all([owner, stranger])
    db.flush()
    return owner, stranger


def _seed_photos(db, owner, *, count=3):
    rows = []
    for index in range(count):
        photo = Photo(
            id=uuid4(),
            owner_id=owner.id,
            filename=f"memory-api-{index}.jpg",
            file_path=f"/tmp/memory-api-{index}.jpg",
            file_type=FileType.image,
            photo_time=datetime(2026, 6, 1, 9, index, 0),
            upload_time=datetime(2026, 6, 1, 9, index, 0),
            size=10,
            is_deleted=False,
        )
        db.add(photo)
        rows.append(photo)
    db.flush()
    return rows


def _seed_memory(db, owner, *, status=MemoryStatus.CONFIRMED, with_photos=True):
    photos = _seed_photos(db, owner, count=3) if with_photos else []
    row = Memory(
        id=uuid4(),
        owner_id=owner.id,
        status=status,
        origin=MemoryOrigin.MANUAL,
        title=f"seed-{status.value}-{uuid4().hex[:6]}",
        title_source="user",
        start_time=datetime(2026, 6, 1, 9, 0, 0),
        end_time=datetime(2026, 6, 1, 11, 0, 0),
        confidence=1.0,
    )
    db.add(row)
    db.flush()
    for index, photo in enumerate(photos):
        row.photo_links.append(
            MemoryPhoto(photo=photo, source="user_added", is_confirmed=True, sort_order=index)
        )
    db.commit()
    return row, photos


def test_list_counts_and_detail_hide_stranger_memories(face_sqlite_session):
    db = face_sqlite_session
    owner, stranger = _seed_owner(db)
    confirmed, _ = _seed_memory(db, owner, status=MemoryStatus.CONFIRMED)
    _seed_memory(db, owner, status=MemoryStatus.CANDIDATE)
    _seed_memory(db, stranger, status=MemoryStatus.CONFIRMED)
    client = _build_client(db, owner)

    counts = client.get("/api/memory/counts")
    assert counts.status_code == 200
    body = counts.json()["data"]
    # counts only consider CANDIDATE/CONFIRMED/IGNORED; deleted/superseded excluded
    assert body["confirmed"] == 1 and body["candidate"] == 1

    listing = client.get("/api/memory?status=candidate")
    assert listing.status_code == 200
    data = listing.json()["data"]
    assert data["total"] == 1 and len(data["items"]) == 1
    listed = data["items"][0]
    assert listed["status"] == "candidate" and listed["title_source"] == "user"
    assert "preview_photo_ids" in listed and "photo_count" in listed

    detail = client.get(f"/api/memory/{confirmed.id}")
    assert detail.status_code == 200
    body = detail.json()["data"]
    assert body["id"] == str(confirmed.id)
    assert body["status"] == "confirmed"
    assert isinstance(body["photos"], list) and len(body["photos"]) == 3
    assert body["confidence_level"] == "strong"

    foreign = client.get(f"/api/memory/{uuid4()}")
    assert foreign.status_code == 404


def test_create_update_and_delete_with_ownership(face_sqlite_session):
    db = face_sqlite_session
    owner, stranger = _seed_owner(db)
    photos = _seed_photos(db, owner, count=2)
    client = _build_client(db, owner)

    create_payload = {
        "title": "Hangzhou weekend",
        "story": "Two quiet days by the lake.",
        "photo_ids": [str(photo.id) for photo in photos],
        "cover_photo_id": str(photos[0].id),
        "place_names": ["Hangzhou", "West Lake"],
        "origin": "manual",
    }
    create = client.post("/api/memory", json=create_payload)
    assert create.status_code == 200, create.text
    body = create.json()["data"]
    memory_id = body["id"]
    assert body["title"] == "Hangzhou weekend"
    assert body["title_source"] == "user"
    assert body["story_source"] == "user"
    assert {place["name"] for place in body["places"]} == {"Hangzhou", "West Lake"}

    # Update title, story, and place_names via PATCH
    update = client.patch(
        f"/api/memory/{memory_id}",
        json={
            "title": "Hangzhou weekend v2",
            "story": "Revised story.",
            "place_names": ["Hangzhou"],
        },
    )
    assert update.status_code == 200
    updated = update.json()["data"]
    assert updated["title"] == "Hangzhou weekend v2"
    assert len(updated["places"]) == 1 and updated["places"][0]["name"] == "Hangzhou"

    # Inverted time window must be rejected by service update path
    bad_time = client.patch(
        f"/api/memory/{memory_id}",
        json={
            "start_time": "2026-06-02T00:00:00",
            "end_time": "2026-06-01T00:00:00",
        },
    )
    assert bad_time.status_code == 400
    assert "开始时间" in bad_time.json()["detail"]

    # Stranger cannot see or delete the memory
    stranger_client = _build_client(db, stranger)
    forbidden = stranger_client.get(f"/api/memory/{memory_id}")
    assert forbidden.status_code == 404
    forbidden_delete = stranger_client.delete(f"/api/memory/{memory_id}")
    assert forbidden_delete.status_code == 404

    delete = client.delete(f"/api/memory/{memory_id}")
    assert delete.status_code == 200 and delete.json()["data"] == {"deleted": True}
    gone = client.get(f"/api/memory/{memory_id}")
    assert gone.status_code == 404

    # Re-create with a photo from another user must fail at validation
    foreign_photo = Photo(
        id=uuid4(),
        owner_id=stranger.id,
        filename="stranger.jpg",
        file_path="/tmp/stranger.jpg",
        file_type=FileType.image,
        photo_time=datetime(2026, 6, 1, 9, 0, 0),
        upload_time=datetime(2026, 6, 1, 9, 0, 0),
        size=10,
        is_deleted=False,
    )
    db.add(foreign_photo)
    db.commit()
    bad = client.post(
        "/api/memory",
        json={"title": "bad", "photo_ids": [str(foreign_photo.id)]},
    )
    assert bad.status_code == 400


def test_status_transitions_only_accept_eligible_states(face_sqlite_session):
    db = face_sqlite_session
    owner, _ = _seed_owner(db)
    client = _build_client(db, owner)

    candidate, _ = _seed_memory(db, owner, status=MemoryStatus.CANDIDATE)
    confirmed, _ = _seed_memory(db, owner, status=MemoryStatus.CONFIRMED)
    ignored, _ = _seed_memory(db, owner, status=MemoryStatus.IGNORED)
    archived, _ = _seed_memory(db, owner, status=MemoryStatus.ARCHIVED)

    # Candidate -> Confirmed works
    confirm = client.post(f"/api/memory/{candidate.id}/confirm")
    assert confirm.status_code == 200 and confirm.json()["data"]["status"] == "confirmed"
    # Confirmed cannot be confirmed again (must be CANDIDATE or IGNORED)
    repeat = client.post(f"/api/memory/{confirmed.id}/confirm")
    assert repeat.status_code == 400

    # Confirmed -> Archive works
    archive = client.post(f"/api/memory/{confirmed.id}/archive")
    assert archive.status_code == 200 and archive.json()["data"]["status"] == "archived"
    # Archive requires confirmed state, so archiving an already-archived row fails
    repeat_archive = client.post(f"/api/memory/{archived.id}/archive")
    assert repeat_archive.status_code == 400

    # Ignored -> Restore returns to CANDIDATE
    restore_ignored = client.post(f"/api/memory/{ignored.id}/restore")
    assert restore_ignored.status_code == 200
    assert restore_ignored.json()["data"]["status"] == "candidate"
    # Archived -> Restore returns to CONFIRMED
    restore_archived = client.post(f"/api/memory/{archived.id}/restore")
    assert restore_archived.status_code == 200
    assert restore_archived.json()["data"]["status"] == "confirmed"

    # Only CANDIDATE can be ignored
    ignore_confirmed = client.post(f"/api/memory/{confirmed.id}/ignore")
    assert ignore_confirmed.status_code == 400
    # ignore works on a fresh CANDIDATE row; reuse ``candidate`` (now CONFIRMED) by
    # creating another candidate. The transition rules live in api/memory.py.
    ignore_candidate_row, _ = _seed_memory(db, owner, status=MemoryStatus.CANDIDATE)
    ignore_candidate = client.post(f"/api/memory/{ignore_candidate_row.id}/ignore")
    assert ignore_candidate.status_code == 200, ignore_candidate.text
    assert ignore_candidate.json()["data"]["status"] == "ignored"


def test_photo_add_remove_and_cover_alignment(face_sqlite_session):
    db = face_sqlite_session
    owner, _ = _seed_owner(db)
    photos = _seed_photos(db, owner, count=4)
    memory, attached = _seed_memory(db, owner, status=MemoryStatus.CONFIRMED)
    client = _build_client(db, owner)

    new_photos = photos[3:]
    add = client.post(
        f"/api/memory/{memory.id}/photos/add",
        json={"photo_ids": [str(photo.id) for photo in new_photos]},
    )
    assert add.status_code == 200
    body = add.json()["data"]
    assert {photo["id"] for photo in body["photos"]} == {str(photo.id) for photo in attached + new_photos}

    # Adding the same photo twice is idempotent (sort_order stays stable)
    repeat = client.post(
        f"/api/memory/{memory.id}/photos/add",
        json={"photo_ids": [str(new_photos[0].id)]},
    )
    assert repeat.status_code == 200
    repeat_body = repeat.json()["data"]
    assert len(repeat_body["photos"]) == 4

    # Removing all photos must fail
    drain = client.post(
        f"/api/memory/{memory.id}/photos/remove",
        json={"photo_ids": [str(photo.id) for photo in attached + new_photos]},
    )
    assert drain.status_code == 400
    assert "一张" in drain.json()["detail"]

    # Removing only the cover photo rotates cover to the first remaining one
    cover_id = str(memory.cover_photo_id) if memory.cover_photo_id else str(attached[0].id)
    rotate = client.post(
        f"/api/memory/{memory.id}/photos/remove",
        json={"photo_ids": [cover_id]},
    )
    assert rotate.status_code == 200
    rotated = rotate.json()["data"]
    assert rotated["cover_photo_id"] != cover_id
    assert len(rotated["photos"]) == 3


def test_merge_requires_two_eligible_and_combines_photos(face_sqlite_session):
    db = face_sqlite_session
    owner, _ = _seed_owner(db)
    photos = _seed_photos(db, owner, count=4)
    client = _build_client(db, owner)

    first, first_photos = _seed_memory(db, owner, status=MemoryStatus.CONFIRMED)
    second, second_photos = _seed_memory(db, owner, status=MemoryStatus.CONFIRMED)

    # Single memory id is rejected by the Pydantic schema (min_length=2)
    bad = client.post(
        "/api/memory/merge",
        json={"memory_ids": [str(first.id)]},
    )
    assert bad.status_code == 422

    # Merge should combine photos from both sources
    merged = client.post(
        "/api/memory/merge",
        json={
            "memory_ids": [str(first.id), str(second.id)],
            "title": "Combined memory",
            "story": "Two memories, one story.",
            "cover_photo_id": str(first_photos[0].id),
        },
    )
    assert merged.status_code == 200, merged.text
    body = merged.json()["data"]
    assert body["title"] == "Combined memory"
    assert body["title_source"] == "user"
    assert body["story_source"] == "user"
    assert body["status"] == "confirmed"
    assert len(body["photos"]) == len(first_photos) + len(second_photos)

    # Sources should now be SUPERSEDED and not visible in default listing
    db.refresh(first)
    db.refresh(second)
    assert first.status == MemoryStatus.SUPERSEDED
    assert second.status == MemoryStatus.SUPERSEDED


def test_split_requires_full_photo_partition_and_assigns_titles(face_sqlite_session):
    db = face_sqlite_session
    owner, _ = _seed_owner(db)
    photos = _seed_photos(db, owner, count=4)
    memory, attached = _seed_memory(db, owner, status=MemoryStatus.CONFIRMED)
    client = _build_client(db, owner)

    # Partition missing one photo must fail at service validation
    partial = client.post(
        f"/api/memory/{memory.id}/split",
        json={
            "parts": [
                {"title": "Part A", "photo_ids": [str(attached[0].id)]},
                {"title": "Part B", "photo_ids": [str(attached[1].id)]},
            ]
        },
    )
    assert partial.status_code == 400
    assert "全部照片" in partial.json()["detail"]

    # Duplicate photo ids in the parts must be rejected by the schema validator
    dup = client.post(
        f"/api/memory/{memory.id}/split",
        json={
            "parts": [
                {"title": "Part A", "photo_ids": [str(attached[0].id)]},
                {"title": "Part B", "photo_ids": [str(attached[0].id)]},
            ]
        },
    )
    assert dup.status_code == 422

    # Successful split assigns each photo to its own part and supersedes the source
    parts = [
        {"title": "Part A", "photo_ids": [str(photo.id) for photo in attached[:2]]},
        {"title": "Part B", "photo_ids": [str(photo.id) for photo in attached[2:]]},
    ]
    ok = client.post(f"/api/memory/{memory.id}/split", json={"parts": parts})
    assert ok.status_code == 200, ok.text
    body = ok.json()["data"]
    assert len(body) == 2
    titles = sorted(item["title"] for item in body)
    assert titles == ["Part A", "Part B"]


def test_discover_with_empty_window_returns_empty_and_blocks_foreign_photos(face_sqlite_session):
    db = face_sqlite_session
    owner, stranger = _seed_owner(db)
    client = _build_client(db, owner)

    empty = client.post(
        "/api/memory/discover",
        json={"start_time": "2099-01-01T00:00:00", "end_time": "2099-01-02T00:00:00"},
    )
    assert empty.status_code == 200
    body = empty.json()["data"]
    assert body["created"] == 0 and body["items"] == []

    # Validation: min_photos must respect ge=3
    too_low = client.post("/api/memory/discover", json={"min_photos": 1})
    assert too_low.status_code == 422

    # Discover over a private window with only the stranger's photos must yield no rows
    foreign_photo = Photo(
        id=uuid4(),
        owner_id=stranger.id,
        filename="stranger.jpg",
        file_path="/tmp/stranger.jpg",
        file_type=FileType.image,
        photo_time=datetime(2026, 6, 1, 9, 0, 0),
        upload_time=datetime(2026, 6, 1, 9, 0, 0),
        size=10,
        is_deleted=False,
    )
    db.add(foreign_photo)
    db.commit()
    none = client.post(
        "/api/memory/discover",
        json={"start_time": "2026-06-01T00:00:00", "end_time": "2026-06-01T23:59:59"},
    )
    assert none.status_code == 200 and none.json()["data"]["created"] == 0


def test_create_with_ticket_and_face_refs_validates_ownership(face_sqlite_session):
    db = face_sqlite_session
    owner, stranger = _seed_owner(db)
    photos = _seed_photos(db, owner, count=2)
    train = TrainTicket(
        id=str(uuid4()),
        owner_id=owner.id,
        train_code="G7556",
        departure_station="Shanghai-Hongqiao",
        arrival_station="Hangzhou",
        date_time=datetime(2026, 6, 1, 9, 0, 0),
        carriage="04",
        seat_num="12A",
        price=184,
        seat_type="second-class",
        name="nightrain",
    )
    flight = FlightTicket(
        id=str(uuid4()),
        owner_id=owner.id,
        flight_code="MU5402",
        departure_city="Shanghai-Hongqiao",
        arrival_city="Hangzhou-Xiaoshan",
        date_time=datetime(2026, 6, 1, 7, 30, 0),
        price=620,
        name="nightrain",
    )
    own_face = FaceIdentity(id=uuid4(), owner_id=owner.id, identity_name="甲")
    stranger_face = FaceIdentity(id=uuid4(), owner_id=stranger.id, identity_name="乙")
    db.add_all([train, flight, own_face, stranger_face])
    db.commit()

    client = _build_client(db, owner)
    payload = {
        "title": "Trip with face and tickets",
        "photo_ids": [str(photo.id) for photo in photos],
        "person_ids": [str(own_face.id), str(stranger_face.id)],
        "ticket_refs": [{"type": "train", "id": train.id}, {"type": "flight", "id": flight.id}],
        "place_names": ["Hangzhou"],
    }
    bad = client.post("/api/memory", json=payload)
    assert bad.status_code == 400  # stranger_face fails ownership

    payload["person_ids"] = [str(own_face.id)]
    bad_ticket = client.post(
        "/api/memory",
        json={**payload, "ticket_refs": [{"type": "bus", "id": "abc"}]},
    )
    assert bad_ticket.status_code == 400  # invalid ticket type

    ok = client.post("/api/memory", json=payload)
    assert ok.status_code == 200, ok.text
    body = ok.json()["data"]
    assert {ticket["type"] for ticket in body["tickets"]} == {"train", "flight"}
    assert {person["id"] for person in body["people"]} == {str(own_face.id)}
    assert body["places"][0]["name"] == "Hangzhou"

