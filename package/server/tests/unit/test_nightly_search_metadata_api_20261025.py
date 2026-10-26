"""Nightly coverage for the metadata search branch of ``app/api/search.py`` (2026-10-25).

The 2026-10-25 backend coverage scan listed ``api/search.py`` at 79.0% with 34
missed lines.  Every missed line sat in one place: the *metadata* branch of
``POST /search/text`` -- the ``request.type`` switch that turns a plain text
query into a structured filter over

* ``filename`` / ``folder``  -- the photo columns
* ``location``              -- ``PhotoMetadata`` (city / province / country / district / address)
* ``album`` / ``tag`` / ``scene`` / ``person`` / ``ocr`` -- the joined relations

The branch had no test at all: the existing suite only exercised the vector
search path (``request.type is None``).

These tests drive the real endpoint function against a real SQLite session
(``face_sqlite_session`` from the shared conftest) so the assertions describe
query *behaviour* -- which photos come back -- instead of the shape of a mock
call chain.
"""

import asyncio
import uuid
from datetime import datetime
from types import SimpleNamespace

import pytest

pytestmark = [pytest.mark.smoke]


def _run(coro):
    """Run the async endpoint function to completion."""
    return asyncio.run(coro)


def _search(db, user_id, text, search_type=None, **kwargs):
    from app.api.search import TextSearchRequest, search_by_text

    request = TextSearchRequest(text=text, type=search_type, **kwargs)
    user = SimpleNamespace(id=user_id)
    response = _run(search_by_text(request, db, user))
    assert response.code == 200
    return [item.photo.id for item in (response.data or [])]


@pytest.fixture()
def seeded(face_sqlite_session):
    """Two photos for one owner, wired to every searchable relation."""
    from app.db.models.album import Album
    from app.db.models.face import Face, FaceIdentity
    from app.db.models.ocr import OCR
    from app.db.models.photo import FileType, Photo
    from app.db.models.photo_metadata import PhotoMetadata
    from app.db.models.scene import Scene
    from app.db.models.tag import PhotoTag

    db = face_sqlite_session
    owner_id = uuid.uuid4()
    other_owner_id = uuid.uuid4()

    beach = Photo(
        id=uuid.uuid4(),
        owner_id=owner_id,
        filename="sunset_beach.jpg",
        file_path="/photos/2024/sunset_beach.jpg",
        photo_time=datetime(2024, 5, 1, 9, 30),
        file_type=FileType.image,
        size=1024,
        width=800,
        height=600,
        duration=0.0,
    )
    dinner = Photo(
        id=uuid.uuid4(),
        owner_id=owner_id,
        filename="family_dinner.jpg",
        file_path="/photos/2023/family_dinner.jpg",
        photo_time=datetime(2023, 11, 20, 18, 0),
        file_type=FileType.image,
        size=2048,
        width=1024,
        height=768,
        duration=0.0,
    )
    stranger = Photo(
        id=uuid.uuid4(),
        owner_id=other_owner_id,
        filename="sunset_beach.jpg",
        file_path="/photos/2024/somebody_else.jpg",
        photo_time=datetime(2024, 5, 1, 9, 30),
        file_type=FileType.image,
        size=1024,
        width=800,
        height=600,
        duration=0.0,
    )
    db.add_all([beach, dinner, stranger])
    db.flush()

    seaside = Scene(name="Seaside", owner_id=owner_id)
    db.add(seaside)
    db.flush()

    db.add(
        PhotoMetadata(
            photo_id=beach.id,
            city="Hangzhou",
            province="Zhejiang",
            country="China",
            district="Xihu",
            address="No.1 West Lake Road",
            scene_id=seaside.id,
        )
    )
    db.add(
        PhotoMetadata(
            photo_id=dinner.id,
            city="Beijing",
            province="Beijing",
            country="China",
        )
    )

    album = Album(name="Travel 2024", owner_id=owner_id)
    db.add(album)
    db.flush()
    beach.albums.append(album)

    tag = PhotoTag(tag_name="beach", owner_id=owner_id)
    db.add(tag)
    db.flush()
    beach.tags.append(tag)

    identity = FaceIdentity(identity_name="Alice", owner_id=owner_id)
    db.add(identity)
    db.flush()
    db.add(Face(photo_id=beach.id, face_identity_id=identity.id, face_confidence=0.99))

    db.add(OCR(photo_id=beach.id, text="SUNSET BEACH 2024"))
    db.commit()

    return SimpleNamespace(
        db=db,
        owner_id=owner_id,
        other_owner_id=other_owner_id,
        beach=beach,
        dinner=dinner,
        stranger=stranger,
    )


# ---------------------------------------------------------------------------
# filename
# ---------------------------------------------------------------------------


def test_filename_search_matches_only_the_owner(seeded):
    """The metadata branch is always scoped to ``Photo.owner_id``."""
    found = _search(seeded.db, seeded.owner_id, "sunset", "filename")
    assert found == [seeded.beach.id]


def test_filename_search_is_case_insensitive(seeded):
    found = _search(seeded.db, seeded.owner_id, "SUNSET", "filename")
    assert found == [seeded.beach.id]


def test_filename_search_without_matches(seeded):
    assert _search(seeded.db, seeded.owner_id, "nothing-here", "filename") == []


# ---------------------------------------------------------------------------
# location
# ---------------------------------------------------------------------------


def test_location_search_by_city(seeded):
    found = _search(seeded.db, seeded.owner_id, "hangzhou", "location")
    assert found == [seeded.beach.id]


def test_location_search_by_address(seeded):
    """The location branch also matches the free-text address column."""
    found = _search(seeded.db, seeded.owner_id, "West Lake", "location")
    assert found == [seeded.beach.id]


def test_location_search_by_country_matches_both(seeded):
    found = _search(seeded.db, seeded.owner_id, "China", "location")
    assert set(found) == {seeded.beach.id, seeded.dinner.id}


# ---------------------------------------------------------------------------
# album / tag / scene
# ---------------------------------------------------------------------------


def test_album_search(seeded):
    found = _search(seeded.db, seeded.owner_id, "Travel", "album")
    assert found == [seeded.beach.id]


def test_tag_search(seeded):
    found = _search(seeded.db, seeded.owner_id, "beach", "tag")
    assert found == [seeded.beach.id]


def test_scene_search(seeded):
    found = _search(seeded.db, seeded.owner_id, "Seaside", "scene")
    assert found == [seeded.beach.id]


# ---------------------------------------------------------------------------
# person / ocr
# ---------------------------------------------------------------------------


def test_person_search_by_identity_name(seeded):
    found = _search(seeded.db, seeded.owner_id, "Alice", "person")
    assert found == [seeded.beach.id]


def test_ocr_search(seeded):
    found = _search(seeded.db, seeded.owner_id, "SUNSET", "ocr")
    assert found == [seeded.beach.id]


# ---------------------------------------------------------------------------
# time range / paging / unknown type
# ---------------------------------------------------------------------------


def test_start_time_filter_excludes_older_photos(seeded):
    found = _search(
        seeded.db,
        seeded.owner_id,
        "sunset",
        "filename",
        start_time=datetime(2024, 1, 1),
    )
    assert found == [seeded.beach.id]


def test_end_time_filter_excludes_newer_photos(seeded):
    """Only the photo taken before the window survives ``end_time``."""
    found = _search(
        seeded.db,
        seeded.owner_id,
        "jpg",
        "filename",
        end_time=datetime(2024, 1, 1),
    )
    assert found == [seeded.dinner.id]


def test_limit_and_skip_are_applied(seeded):
    """``limit``/``skip`` page through the result set without losing rows."""
    first = _search(seeded.db, seeded.owner_id, "jpg", "filename", limit=1)
    second = _search(seeded.db, seeded.owner_id, "jpg", "filename", limit=1, skip=1)

    assert len(first) == 1
    assert len(second) == 1
    assert first != second
    assert set(first) | set(second) == {seeded.beach.id, seeded.dinner.id}


def test_unknown_type_returns_the_owner_photos(seeded):
    """An unknown type adds no extra filter but keeps the owner scope."""
    found = _search(seeded.db, seeded.owner_id, "jpg", "not-a-type")
    assert len(found) == 2
    assert seeded.stranger.id not in found


def test_other_owner_never_sees_the_photo(seeded):
    """The same query for a different owner only returns that owner's photos."""
    found = _search(seeded.db, seeded.other_owner_id, "sunset", "filename")
    assert found == [seeded.stranger.id]
    assert seeded.beach.id not in found
