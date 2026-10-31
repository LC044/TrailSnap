"""2026-10-30 nightly coverage for the *candidate enumeration* half of
``app/service/agent/actions.py``.

The 2026-10-30 morning nightly already covered the write/execute half of this
module (see ``test_nightly_agent_actions_execute_20261030.py``).  What is still
untested is the **read** half that decides *what* the Agent is allowed to
propose to the user:

* ``find_album_repair_candidates`` — count / cover drift detection;
* ``find_album_metadata_repair_candidates`` — missing AI description / md5;
* ``find_photo_context_repair_candidates`` — filename time recovery and
  same-burst GPS bridging;
* ``find_album_cleanup_candidates`` — exact duplicates and empty albums.

These functions only *read* the library, so they are the cheapest place where a
silent regression would quietly offer the user a wrong (or destructive) plan.
The tests below drive the real functions against a real in-memory SQLite
library and assert on the exact candidate ids, kinds and guard messages.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models.album import Album, AlbumPhoto
from app.db.models.image_description import ImageDescription
from app.db.models.photo import FileType, ImageType, Photo
from app.db.models.photo_metadata import PhotoMetadata
from app.db.models.user import User
from app.service.agent import actions


pytestmark = [pytest.mark.smoke, pytest.mark.module_agent]


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False)()
    owner, stranger = uuid.uuid4(), uuid.uuid4()
    session.add_all([
        User(id=owner, username="cand-owner", hashed_password="x"),
        User(id=stranger, username="cand-stranger", hashed_password="x"),
    ])
    session.commit()
    try:
        yield session, owner, stranger
    finally:
        session.close()
        engine.dispose()


def _photo(db, owner, name, when=None, md5=None, file_type=FileType.image,
           image_type=None, width=100, height=100, deleted=False, upload_time=None):
    photo = Photo(
        id=uuid.uuid4(), owner_id=owner, filename=name, file_path=name,
        file_type=file_type, size=1, is_deleted=deleted,
        photo_time=when, md5=md5, image_type=image_type,
        width=width, height=height, upload_time=upload_time,
    )
    db.add(photo)
    db.flush()
    return photo


def _album(db, owner, name, photos=(), num_photos=None, cover=None, album_type="user"):
    album = Album(
        id=uuid.uuid4(), name=name, type=album_type, owner_id=owner,
        num_photos=len(photos) if num_photos is None else num_photos,
        cover_id=cover.id if cover is not None else None,
    )
    db.add(album)
    db.flush()
    for photo in photos:
        db.add(AlbumPhoto(album_id=album.id, photo_id=photo.id))
    db.flush()
    return album


def _metadata(db, photo, **kwargs):
    defaults = {"longitude": 120.1, "latitude": 30.2, "address": "浙江省杭州市西湖区"}
    defaults.update(kwargs)
    row = PhotoMetadata(photo_id=photo.id, **defaults)
    db.add(row)
    db.flush()
    return row


def _description(db, photo, quality=None, memory=None, text="描述"):
    row = ImageDescription(
        photo_id=photo.id, description=text, quality_score=quality, memory_score=memory,
    )
    db.add(row)
    db.flush()
    return row


# ---------------------------------------------------------------------------
# find_album_repair_candidates
# ---------------------------------------------------------------------------


def test_album_repair_candidates_report_count_drift(db):
    session, owner, _ = db
    photo = _photo(session, owner, "a.jpg")
    album = _album(session, owner, "trip", photos=(photo,), num_photos=7)

    candidates = actions.find_album_repair_candidates(session, owner)

    count_item = next(item for item in candidates if item["kind"] == "album_count")
    assert count_item["id"] == f"album_count:{album.id}"
    assert count_item["before"] == 7
    assert count_item["after"] == 1
    assert count_item["album_name"] == "trip"


def test_album_repair_candidates_propose_a_cover_when_missing(db):
    session, owner, _ = db
    photo = _photo(session, owner, "a.jpg")
    _album(session, owner, "trip", photos=(photo,))

    candidates = actions.find_album_repair_candidates(session, owner)

    cover_item = next(item for item in candidates if item["kind"] == "album_cover")
    assert cover_item["before"] is None
    assert cover_item["after"] == str(photo.id)
    assert cover_item["reason"] == "当前没有封面"
    assert cover_item["thumbnail_url"].endswith(f"/thumbnail?size=small")


def test_album_repair_candidates_flag_a_cover_outside_the_album(db):
    session, owner, _ = db
    inside = _photo(session, owner, "inside.jpg")
    outside = _photo(session, owner, "outside.jpg")
    album = _album(session, owner, "trip", photos=(inside,), cover=outside)

    candidates = actions.find_album_repair_candidates(session, owner)

    cover_item = next(item for item in candidates if item["kind"] == "album_cover")
    assert cover_item["before"] == str(outside.id)
    assert cover_item["after"] == str(inside.id)
    assert cover_item["reason"] == "当前封面不属于相册"


def test_album_repair_candidates_prefer_the_best_scored_cover(db):
    session, owner, _ = db
    plain = _photo(session, owner, "plain.jpg")
    scored = _photo(session, owner, "scored.jpg")
    _description(session, scored, quality=90, memory=80)
    _album(session, owner, "trip", photos=(plain, scored))

    candidates = actions.find_album_repair_candidates(session, owner)

    cover_item = next(item for item in candidates if item["kind"] == "album_cover")
    assert cover_item["after"] == str(scored.id)


def test_album_repair_candidates_skip_healthy_albums(db):
    session, owner, _ = db
    photo = _photo(session, owner, "a.jpg")
    _album(session, owner, "trip", photos=(photo,), cover=photo)

    assert actions.find_album_repair_candidates(session, owner) == []


def test_album_repair_candidates_ignore_deleted_photos(db):
    session, owner, _ = db
    alive = _photo(session, owner, "alive.jpg")
    gone = _photo(session, owner, "gone.jpg", deleted=True)
    _album(session, owner, "trip", photos=(alive, gone), num_photos=2, cover=alive)

    candidates = actions.find_album_repair_candidates(session, owner)

    assert [item["kind"] for item in candidates] == ["album_count"]
    assert candidates[0]["after"] == 1


def test_album_repair_candidates_reject_an_unknown_album(db):
    session, owner, _ = db
    with pytest.raises(ValueError, match="相册不存在或无权访问"):
        actions.find_album_repair_candidates(session, owner, album_id=uuid.uuid4())


def test_album_repair_candidates_reject_another_users_album(db):
    session, owner, stranger = db
    photo = _photo(session, stranger, "s.jpg")
    album = _album(session, stranger, "theirs", photos=(photo,))
    with pytest.raises(ValueError, match="相册不存在或无权访问"):
        actions.find_album_repair_candidates(session, owner, album_id=album.id)


def test_album_repair_candidates_are_truncated(db, monkeypatch):
    session, owner, _ = db
    photo = _photo(session, owner, "a.jpg")
    _album(session, owner, "one", photos=(photo,), num_photos=3)
    _album(session, owner, "two", photos=(photo,), num_photos=4)
    monkeypatch.setattr(actions, "MAX_REPAIR_ITEMS", 1)

    candidates = actions.find_album_repair_candidates(session, owner)

    assert len(candidates) == 1


# ---------------------------------------------------------------------------
# find_album_metadata_repair_candidates
# ---------------------------------------------------------------------------


def test_metadata_repair_candidates_report_missing_description_and_hash(db):
    session, owner, _ = db
    _photo(session, owner, "a.jpg")

    candidates = actions.find_album_metadata_repair_candidates(session, owner)

    ids = [item["id"] for item in candidates]
    assert ids == ["metadata_description", "metadata_hash"]
    assert candidates[0]["kind"] == "visual_description"
    assert candidates[0]["count"] == 1
    assert candidates[0]["queued_count"] == 1
    assert candidates[0]["truncated"] is False
    assert candidates[1]["kind"] == "file_hash"


def test_metadata_repair_candidates_skip_photos_that_already_have_data(db):
    session, owner, _ = db
    photo = _photo(session, owner, "a.jpg", md5="hash-1")
    _description(session, photo)

    candidates = actions.find_album_metadata_repair_candidates(session, owner)

    assert [item["id"] for item in candidates] == []


def test_metadata_repair_candidates_exclude_videos_and_screenshots(db):
    session, owner, _ = db
    _photo(session, owner, "clip.mp4", file_type=FileType.video)
    _photo(session, owner, "shot.png", image_type=ImageType.SCREENSHOT)

    candidates = actions.find_album_metadata_repair_candidates(session, owner)

    assert all(item["id"] != "metadata_description" for item in candidates)


def test_metadata_repair_candidates_can_be_scoped_to_one_album(db):
    session, owner, _ = db
    inside = _photo(session, owner, "inside.jpg")
    outside = _photo(session, owner, "outside.jpg")
    album = _album(session, owner, "trip", photos=(inside,))

    candidates = actions.find_album_metadata_repair_candidates(session, owner, album_id=album.id)

    assert candidates[0]["count"] == 1
    assert candidates[0]["photo_ids"] == [str(inside.id)]
    assert str(outside.id) not in candidates[0]["photo_ids"]


def test_metadata_repair_candidates_mark_a_truncated_batch(db, monkeypatch):
    session, owner, _ = db
    _photo(session, owner, "a.jpg")
    _photo(session, owner, "b.jpg")
    monkeypatch.setattr(actions, "MAX_METADATA_REPAIR_PHOTOS", 1)

    candidates = actions.find_album_metadata_repair_candidates(session, owner)

    description = next(item for item in candidates if item["id"] == "metadata_description")
    assert description["count"] == 2
    assert description["queued_count"] == 1
    assert description["truncated"] is True


def test_metadata_repair_candidates_reject_an_unknown_album(db):
    session, owner, _ = db
    with pytest.raises(ValueError, match="相册不存在或无权访问"):
        actions.find_album_metadata_repair_candidates(session, owner, album_id=uuid.uuid4())


# ---------------------------------------------------------------------------
# find_photo_context_repair_candidates
# ---------------------------------------------------------------------------


def test_context_repair_candidates_recover_time_from_the_filename(db):
    session, owner, _ = db
    photo = _photo(session, owner, "IMG_20230505_161512_122.jpg", when=None)

    candidates = actions.find_photo_context_repair_candidates(session, owner)

    assert len(candidates) == 1
    item = candidates[0]
    assert item["kind"] == "photo_time"
    assert item["id"] == f"photo_time:{photo.id}"
    assert item["before"] is None
    assert item["confidence"] == "high"
    assert "2023-05-05" in item["after"]


def test_context_repair_candidates_ignore_unparsable_filenames(db):
    session, owner, _ = db
    _photo(session, owner, "holiday.jpg", when=None)

    assert actions.find_photo_context_repair_candidates(session, owner) == []


def test_context_repair_candidates_bridge_a_missing_location(db):
    session, owner, _ = db
    base = datetime(2024, 5, 1, 9, 0, 0)
    first = _photo(session, owner, "1.jpg", when=base)
    middle = _photo(session, owner, "2.jpg", when=base + timedelta(minutes=30))
    last = _photo(session, owner, "3.jpg", when=base + timedelta(minutes=60))
    _metadata(session, first)
    _metadata(session, last)

    candidates = actions.find_photo_context_repair_candidates(session, owner)

    assert len(candidates) == 1
    item = candidates[0]
    assert item["kind"] == "photo_location"
    assert item["photo_id"] == str(middle.id)
    assert item["after"]["latitude"] == pytest.approx(30.2)
    assert "60 分钟" in item["evidence"]  # 跨度取前后两张已知照片


def test_context_repair_candidates_skip_a_bridge_that_is_too_long(db):
    session, owner, _ = db
    base = datetime(2024, 5, 1, 9, 0, 0)
    first = _photo(session, owner, "1.jpg", when=base)
    middle = _photo(session, owner, "2.jpg", when=base + timedelta(hours=8))
    last = _photo(session, owner, "3.jpg", when=base + timedelta(hours=9))
    _metadata(session, first)
    _metadata(session, last)

    assert actions.find_photo_context_repair_candidates(session, owner) == []


def test_context_repair_candidates_skip_a_bridge_with_a_different_place(db):
    session, owner, _ = db
    base = datetime(2024, 5, 1, 9, 0, 0)
    first = _photo(session, owner, "1.jpg", when=base)
    middle = _photo(session, owner, "2.jpg", when=base + timedelta(minutes=30))
    last = _photo(session, owner, "3.jpg", when=base + timedelta(minutes=60))
    _metadata(session, first)
    _metadata(session, last, latitude=40.0, longitude=130.0)

    assert actions.find_photo_context_repair_candidates(session, owner) == []


def test_context_repair_candidates_reject_an_unknown_album(db):
    session, owner, _ = db
    with pytest.raises(ValueError, match="相册不存在或无权访问"):
        actions.find_photo_context_repair_candidates(session, owner, album_id=uuid.uuid4())


# ---------------------------------------------------------------------------
# find_album_cleanup_candidates
# ---------------------------------------------------------------------------


def test_cleanup_candidates_report_an_empty_album(db):
    session, owner, _ = db
    album = _album(session, owner, "empty", photos=())

    candidates = actions.find_album_cleanup_candidates(session, owner)

    empty = next(item for item in candidates if item["kind"] == "empty_album")
    assert empty["id"] == f"empty_album:{album.id}"
    assert empty["before"] == 0
    assert empty["after"] is None


def test_cleanup_candidates_report_exact_duplicates(db):
    session, owner, _ = db
    keeper = _photo(session, owner, "keeper.jpg", md5="same")
    duplicate = _photo(session, owner, "duplicate.jpg", md5="same")
    _description(session, keeper, quality=90)
    _album(session, owner, "trip", photos=(keeper,))

    candidates = actions.find_album_cleanup_candidates(session, owner)

    dup = next(item for item in candidates if item["kind"] == "duplicate_photo")
    assert dup["id"] == f"duplicate_photo:{duplicate.id}"
    assert dup["keeper_photo_id"] == str(keeper.id)
    assert dup["md5"] == "same"
    assert dup["after"] == {"is_deleted": True}


def test_cleanup_candidates_ignore_a_single_occurrence(db):
    session, owner, _ = db
    _photo(session, owner, "only.jpg", md5="unique")

    assert actions.find_album_cleanup_candidates(session, owner) == []


def test_cleanup_candidates_ignore_deleted_duplicates(db):
    session, owner, _ = db
    _photo(session, owner, "a.jpg", md5="same")
    _photo(session, owner, "b.jpg", md5="same", deleted=True)

    assert actions.find_album_cleanup_candidates(session, owner) == []


def test_cleanup_candidates_reject_a_non_user_album(db):
    session, owner, _ = db
    album = _album(session, owner, "smart", photos=(), album_type="smart")
    with pytest.raises(ValueError, match="普通相册不存在或无权清理"):
        actions.find_album_cleanup_candidates(session, owner, album_id=album.id)


# ---------------------------------------------------------------------------
# preview helpers
# ---------------------------------------------------------------------------


def test_repair_preview_counts_only_the_selected_items(db):
    session, owner, _ = db
    photo = _photo(session, owner, "a.jpg")
    album = _album(session, owner, "trip", photos=(photo,), num_photos=3)
    candidates = actions.find_album_repair_candidates(session, owner)

    preview = actions._repair_preview(candidates, [f"album_count:{album.id}"])

    assert preview["mode"] == "repair"
    assert preview["repair_count"] == 1
    assert preview["candidate_count"] == len(candidates)
    assert preview["affected_album_count"] == 1


def test_metadata_repair_preview_sums_the_queued_photos(db):
    session, owner, _ = db
    _photo(session, owner, "a.jpg")
    _photo(session, owner, "b.jpg")
    candidates = actions.find_album_metadata_repair_candidates(session, owner)

    preview = actions._metadata_repair_preview(candidates, ["metadata_description"])

    assert preview["mode"] == "metadata_repair"
    assert preview["photo_count"] == 2
    assert preview["reversible"] is False
    assert len(preview["sample_photos"]) == 2


def test_cleanup_preview_counts_duplicates_and_empty_albums(db):
    session, owner, _ = db
    keeper = _photo(session, owner, "keeper.jpg", md5="same")
    duplicate = _photo(session, owner, "duplicate.jpg", md5="same")
    _album(session, owner, "trip", photos=(keeper, duplicate))
    _album(session, owner, "empty", photos=())
    candidates = actions.find_album_cleanup_candidates(session, owner)

    preview = actions._cleanup_preview(candidates, [item["id"] for item in candidates])

    assert preview["mode"] == "cleanup"
    assert preview["duplicate_photo_count"] == 1
    assert preview["empty_album_count"] == 1
    assert preview["destructive"] is True
    assert preview["reversible"] is True
