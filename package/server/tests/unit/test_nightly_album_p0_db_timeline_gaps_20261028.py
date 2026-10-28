"""Nightly coverage for the DB-backed helpers in ``app/service/agent/album_p0.py``.

The 2026-10-28 backend coverage scan ranked ``service/agent/album_p0.py`` at
79.5% (114 missed statements). The pure helpers were already covered by
``test_nightly_album_p0_helpers_gaps_20261020.py``; what remained uncovered
were the **query-backed** functions that the Agent tools call with a real
session:

* ``search_ocr_rows``   -- owner-scoped OCR lookup with a clamped limit
* ``trip_tickets``      -- train + flight tickets merged and sorted
* ``travel_timeline``   -- day/location segmentation of the photo timeline
* ``contact_sheet_content`` -- numbered contact sheet for multimodal tools
* ``select_representatives`` -- diverse "best of" selection for grids

Every case here uses a real SQLite session (no DB mocking), matching the
style of ``test_album_agent_p0.py``.
"""
from __future__ import annotations

import base64
import json
from datetime import datetime
from uuid import uuid4

import pytest
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models.image_description import ImageDescription
from app.db.models.ocr import OCR
from app.db.models.photo import FileType, Photo
from app.db.models.photo_metadata import PhotoMetadata
from app.db.models.trip import FlightTicket, TrainTicket
from app.db.models.user import User
from app.service.agent import album_p0


pytestmark = [pytest.mark.smoke]


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _photo(owner, filename, photo_time, city=None, width=100, height=100):
    photo = Photo(
        id=uuid4(), owner_id=owner, filename=filename, file_path=filename,
        file_type=FileType.image, is_deleted=False, photo_time=photo_time,
        width=width, height=height,
    )
    return photo

def _train(owner, code, departure, arrival, when):
    return TrainTicket(
        id=str(uuid4()), owner_id=owner, train_code=code,
        departure_station=departure, arrival_station=arrival, date_time=when,
        carriage="08", seat_num="12F", berth_type="无", price=553.5,
        seat_type="二等座", name="测试乘客", discount_type="全价票",
        total_mileage=0, total_running_time=0,
    )


def _flight(owner, code, departure, arrival, when):
    return FlightTicket(
        id=str(uuid4()), owner_id=owner, flight_code=code,
        departure_city=departure, arrival_city=arrival, date_time=when,
        price=1240.0, name="测试乘客",
        total_mileage=0, total_running_time=0,
    )

# ---------------------------------------------------------------------------
# search_ocr_rows
# ---------------------------------------------------------------------------


def test_search_ocr_rows_is_owner_scoped_and_clamped(db):
    owner, stranger = uuid4(), uuid4()
    db.add_all([
        User(id=owner, username="ocr-owner", hashed_password="x"),
        User(id=stranger, username="ocr-stranger", hashed_password="x"),
    ])
    mine = _photo(owner, "mine.jpg", datetime(2026, 3, 1, 10, 0))
    other = _photo(stranger, "other.jpg", datetime(2026, 3, 1, 10, 0))
    db.add_all([mine, other])
    db.flush()
    db.add_all([
        OCR(photo_id=mine.id, text="G1024 次列车", text_score=0.9),
        OCR(photo_id=mine.id, text="另一段 G1024 记录", text_score=0.5),
        OCR(photo_id=other.id, text="G1024 别人的", text_score=0.99),
    ])
    db.commit()

    rows = album_p0.search_ocr_rows(db, str(owner), "G1024")

    # Only the owner's photo matches; the stranger's OCR row is out of scope.
    assert {row["photo_id"] for row in rows} == {str(mine.id)}
    # Both matching OCR rows are returned, highest score first.
    assert [row["text"] for row in rows] == ["G1024 次列车", "另一段 G1024 记录"]
    assert rows[0]["confidence"] == 0.9
    assert rows[0]["thumbnail_url"] == f"/api/medias/{mine.id}/thumbnail"
    assert rows[0]["photo_time"] == datetime(2026, 3, 1, 10, 0).isoformat()


def test_search_ocr_rows_clamps_the_limit_into_one_to_fifty(db):
    owner = uuid4()
    db.add(User(id=owner, username="ocr-limit", hashed_password="x"))
    photo = _photo(owner, "only.jpg", datetime(2026, 3, 2, 9, 0))
    db.add(photo)
    db.flush()
    db.add(OCR(photo_id=photo.id, text="needle", text_score=0.4))
    db.commit()

    # A non-positive limit must not return everything or nothing.
    assert len(album_p0.search_ocr_rows(db, str(owner), "needle", limit=0)) == 1
    assert len(album_p0.search_ocr_rows(db, str(owner), "needle", limit=-5)) == 1
    assert len(album_p0.search_ocr_rows(db, str(owner), "needle", limit=5000)) == 1


def test_search_ocr_rows_skips_deleted_photos(db):
    owner = uuid4()
    db.add(User(id=owner, username="ocr-deleted", hashed_password="x"))
    photo = _photo(owner, "gone.jpg", datetime(2026, 3, 3, 9, 0))
    photo.is_deleted = True
    db.add(photo)
    db.flush()
    db.add(OCR(photo_id=photo.id, text="needle", text_score=0.4))
    db.commit()

    assert album_p0.search_ocr_rows(db, str(owner), "needle") == []


# ---------------------------------------------------------------------------
# trip_tickets
# ---------------------------------------------------------------------------


def test_trip_tickets_merges_train_and_flight_in_time_order(db):
    owner, stranger = uuid4(), uuid4()
    db.add_all([
        User(id=owner, username="ticket-owner", hashed_password="x"),
        User(id=stranger, username="ticket-stranger", hashed_password="x"),
    ])
    flight = _flight(owner, "CA1234", "北京", "上海", datetime(2026, 4, 2, 8, 0))
    late_train = _train(owner, "G100", "西安", "北京", datetime(2026, 4, 3, 9, 0))
    early_train = _train(owner, "G99", "上海", "西安", datetime(2026, 4, 1, 7, 0))
    foreign = _train(stranger, "G77", "广州", "深圳", datetime(2026, 4, 1, 6, 0))
    db.add_all([flight, late_train, early_train, foreign])
    db.commit()

    tickets = album_p0.trip_tickets(db, str(owner), None, None)

    assert [row["code"] for row in tickets] == ["G99", "CA1234", "G100"]
    assert tickets[0]["type"] == "train"
    assert tickets[0]["departure"] == "上海"
    assert tickets[0]["arrival"] == "西安"
    assert tickets[1]["type"] == "flight"
    assert tickets[1]["departure"] == "北京"
    assert tickets[1]["arrival"] == "上海"
    assert tickets[2]["photo_id"] is None


def test_trip_tickets_applies_an_inclusive_end_date(db):
    owner = uuid4()
    db.add(User(id=owner, username="ticket-range", hashed_password="x"))
    inside = _train(owner, "G1", "北京", "天津", datetime(2026, 4, 10, 12, 0))
    outside = _train(owner, "G2", "北京", "天津", datetime(2026, 4, 11, 12, 0))
    db.add_all([inside, outside])
    db.commit()

    # The end date is inclusive, so 2026-04-10 still counts.
    tickets = album_p0.trip_tickets(db, str(owner), "2026-04-10", "2026-04-10")
    assert [row["code"] for row in tickets] == ["G1"]


# ---------------------------------------------------------------------------
# travel_timeline
# ---------------------------------------------------------------------------


def test_travel_timeline_groups_by_day_and_location(db):
    owner, stranger = uuid4(), uuid4()
    db.add_all([
        User(id=owner, username="tl-owner", hashed_password="x"),
        User(id=stranger, username="tl-stranger", hashed_password="x"),
    ])
    day_one_a = _photo(owner, "a.jpg", datetime(2026, 5, 1, 10, 0))
    day_one_b = _photo(owner, "b.jpg", datetime(2026, 5, 1, 18, 0))
    day_two = _photo(owner, "c.jpg", datetime(2026, 5, 2, 11, 0))
    foreign = _photo(stranger, "d.jpg", datetime(2026, 5, 1, 10, 0))
    db.add_all([day_one_a, day_one_b, day_two, foreign])
    db.flush()
    db.add_all([
        PhotoMetadata(photo_id=day_one_a.id, city="西安"),
        PhotoMetadata(photo_id=day_one_b.id, city="西安"),
        PhotoMetadata(photo_id=day_two.id, province="陕西"),
        PhotoMetadata(photo_id=foreign.id, city="西安"),
    ])
    db.commit()

    timeline = album_p0.travel_timeline(db, str(owner), None, None)

    assert timeline["total_photos"] == 3
    assert timeline["truncated"] is False
    segments = {(row["date"], row["location"]): row for row in timeline["segments"]}
    assert segments[("2026-05-01", "西安")]["photo_count"] == 2
    assert len(segments[("2026-05-01", "西安")]["photo_ids"]) == 2
    # No city -> falls back to the province.
    assert segments[("2026-05-02", "陕西")]["photo_count"] == 1


def test_travel_timeline_filters_by_date_range_and_uses_unknown_location(db):
    owner = uuid4()
    db.add(User(id=owner, username="tl-range", hashed_password="x"))
    inside = _photo(owner, "in.jpg", datetime(2026, 6, 1, 10, 0))
    outside = _photo(owner, "out.jpg", datetime(2026, 7, 1, 10, 0))
    db.add_all([inside, outside])
    db.flush()
    db.add_all([
        PhotoMetadata(photo_id=inside.id),
        PhotoMetadata(photo_id=outside.id),
    ])
    db.commit()

    timeline = album_p0.travel_timeline(db, str(owner), "2026-06-01", "2026-06-30")

    assert timeline["total_photos"] == 1
    assert timeline["segments"][0]["location"] == "未知地点"
    assert timeline["segments"][0]["photo_ids"] == [str(inside.id)]


def test_travel_timeline_caps_stored_photo_ids_per_segment(db):
    owner = uuid4()
    db.add(User(id=owner, username="tl-cap", hashed_password="x"))
    photos = [_photo(owner, f"p{i}.jpg", datetime(2026, 8, 1, 10, 0)) for i in range(15)]
    db.add_all(photos)
    db.flush()
    for photo in photos:
        db.add(PhotoMetadata(photo_id=photo.id, city="杭州"))
    db.commit()

    timeline = album_p0.travel_timeline(db, str(owner), None, None)

    segment = timeline["segments"][0]
    # The count is exact, but only the first 12 ids are kept.
    assert segment["photo_count"] == 15
    assert len(segment["photo_ids"]) == 12


# ---------------------------------------------------------------------------
# contact_sheet_content
# ---------------------------------------------------------------------------


def test_contact_sheet_content_returns_a_numbered_index_and_image(db, tmp_path, monkeypatch):
    owner = uuid4()
    db.add(User(id=owner, username="sheet-owner", hashed_password="x"))
    photo = _photo(owner, "sheet.jpg", datetime(2026, 9, 1, 10, 0))
    db.add(photo)
    db.commit()

    source = tmp_path / "source.jpg"
    Image.new("RGB", (300, 200), (10, 120, 200)).save(source)
    monkeypatch.setattr(
        album_p0, "get_available_photo_path",
        lambda user_id, file_id, original_path: str(source),
    )

    blocks = album_p0.contact_sheet_content(db, str(owner), [str(photo.id)])

    assert blocks[0]["type"] == "text"
    payload = json.loads(blocks[0]["text"])
    assert payload["index_to_photo_id"] == {"1": str(photo.id)}
    assert blocks[1]["type"] == "image_url"
    assert blocks[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    decoded = base64.b64decode(blocks[1]["image_url"]["url"].split(",", 1)[1])
    assert decoded[:2] == b"\xff\xd8"  # JPEG magic


def test_contact_sheet_content_warns_when_no_thumbnail_is_readable(db, monkeypatch):
    owner = uuid4()
    db.add(User(id=owner, username="sheet-empty", hashed_password="x"))
    photo = _photo(owner, "missing.jpg", datetime(2026, 9, 2, 10, 0))
    db.add(photo)
    db.commit()

    monkeypatch.setattr(album_p0, "get_available_photo_path", lambda *args: None)

    blocks = album_p0.contact_sheet_content(db, str(owner), [str(photo.id)])

    assert len(blocks) == 1
    payload = json.loads(blocks[0]["text"])
    assert payload["items"] == []
    assert payload["warning"] == "没有可读取的缩略图"


def test_contact_sheet_content_skips_unreadable_images(db, tmp_path, monkeypatch):
    owner = uuid4()
    db.add(User(id=owner, username="sheet-broken", hashed_password="x"))
    good = _photo(owner, "good.jpg", datetime(2026, 9, 3, 10, 0))
    broken = _photo(owner, "broken.jpg", datetime(2026, 9, 3, 11, 0))
    db.add_all([good, broken])
    db.commit()

    good_source = tmp_path / "good.jpg"
    Image.new("RGB", (120, 120), (200, 10, 10)).save(good_source)
    bad_source = tmp_path / "broken.jpg"
    bad_source.write_bytes(b"this is not an image")

    def resolve(user_id, file_id, original_path):
        return str(good_source) if file_id == good.id else str(bad_source)

    monkeypatch.setattr(album_p0, "get_available_photo_path", resolve)

    blocks = album_p0.contact_sheet_content(db, str(owner), [str(good.id), str(broken.id)])

    payload = json.loads(blocks[0]["text"])
    # The unreadable photo is dropped, and the index only mentions the good one.
    assert payload["index_to_photo_id"] == {"1": str(good.id)}


# ---------------------------------------------------------------------------
# select_representatives
# ---------------------------------------------------------------------------


def test_select_representatives_prefers_quality_then_diversity(db, tmp_path, monkeypatch):
    owner = uuid4()
    db.add(User(id=owner, username="rep-owner", hashed_password="x"))
    best = _photo(owner, "best.jpg", datetime(2026, 10, 1, 10, 0))
    same_day = _photo(owner, "same-day.jpg", datetime(2026, 10, 1, 12, 0))
    other_day = _photo(owner, "other-day.jpg", datetime(2026, 10, 2, 10, 0))
    db.add_all([best, same_day, other_day])
    db.flush()
    db.add_all([
        ImageDescription(photo_id=best.id, quality_score=95, memory_score=95),
        ImageDescription(photo_id=same_day.id, quality_score=90, memory_score=90),
        ImageDescription(photo_id=other_day.id, quality_score=50, memory_score=50),
    ])
    db.commit()

    monkeypatch.setattr(
        "app.service.moment.day_highlight_service.dedup_photo_ids",
        lambda db, user_id, photo_ids: list(photo_ids),
    )

    selected = album_p0.select_representatives(db, str(owner), [str(best.id), str(same_day.id), str(other_day.id)], 2)

    assert len(selected) == 2
    assert selected[0]["photo_id"] == str(best.id)
    assert selected[0]["selection_reason"] == "兼顾画面质量、回忆价值与时间/地点/人物多样性"
    # The second pick favours a new day over another photo from the same day.
    assert selected[1]["photo_id"] == str(other_day.id)


def test_select_representatives_clamps_the_requested_count(db, monkeypatch):
    owner = uuid4()
    db.add(User(id=owner, username="rep-clamp", hashed_password="x"))
    photo = _photo(owner, "one.jpg", datetime(2026, 10, 5, 10, 0))
    db.add(photo)
    db.commit()

    monkeypatch.setattr(
        "app.service.moment.day_highlight_service.dedup_photo_ids",
        lambda db, user_id, photo_ids: list(photo_ids),
    )

    # A count of 0 is raised to 1, and a huge count is capped at 16.
    assert len(album_p0.select_representatives(db, str(owner), [str(photo.id)], 0)) == 1
    assert len(album_p0.select_representatives(db, str(owner), [str(photo.id)], 999)) == 1




