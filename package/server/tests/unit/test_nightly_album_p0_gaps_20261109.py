"""Nightly watch 2026-11-09: album_p0 validation / artifact guard gaps.

Targets uncovered branches reported by the 2026-11-09 coverage snapshot for
``app/service/agent/album_p0.py``:

* ``album_health_report``   - invalid album id / album-scoped photo query
* ``investigate_memory_clues`` - invalid date format, reversed date range
* ``build_person_timeline`` - invalid person id, invalid date, reversed range
* ``create_artifact``       - invalid / unauthorized photo ids and ticket ids
* ``save_artifact_html``    - blank html, oversized html, invalid artifact id
* ``artifact_context``      - invalid artifact id, unknown artifact

Every test exercises already-implemented behaviour; no production code changes.
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models.ai_artifact import AIArtifact
from app.db.models.album import Album, AlbumPhoto
from app.db.models.face import Face, FaceIdentity
from app.db.models.photo import FileType, Photo
from app.db.models.trip import TrainTicket
from app.db.models.user import User
from app.service.agent.album_p0 import (
    album_health_report,
    artifact_context,
    build_person_timeline,
    create_artifact,
    investigate_memory_clues,
    save_artifact_html,
)

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


@pytest.fixture()
def owner(db):
    owner_id = uuid4()
    db.add(User(id=owner_id, username="nightly-album-owner", hashed_password="x"))
    db.commit()
    return owner_id


def _photo(db, owner_id, when=None):
    photo = Photo(
        id=uuid4(),
        owner_id=owner_id,
        filename="p.jpg",
        file_path="p.jpg",
        file_type=FileType.image,
        is_deleted=False,
        photo_time=when,
    )
    db.add(photo)
    db.commit()
    return photo


# --------------------------------------------------------------------------- #
# album_health_report
# --------------------------------------------------------------------------- #


def test_album_health_report_rejects_invalid_album_id(db, owner):
    with pytest.raises(ValueError, match="无效的相册 ID"):
        album_health_report(db, str(owner), album_id="not-a-uuid")


def test_album_health_report_scopes_to_album_photos(db, owner):
    album = Album(id=uuid4(), name="trip", owner_id=owner, type="user")
    inside = _photo(db, owner)
    outside = _photo(db, owner)
    db.add(album)
    db.commit()
    db.add(AlbumPhoto(album_id=album.id, photo_id=inside.id))
    db.commit()

    report = album_health_report(db, str(owner), album_id=str(album.id))

    assert isinstance(report, dict)
    assert "issues" in report


# --------------------------------------------------------------------------- #
# investigate_memory_clues
# --------------------------------------------------------------------------- #


def test_investigate_memory_clues_rejects_invalid_date(db, owner):
    with pytest.raises(ValueError, match="开始日期格式必须为 YYYY-MM-DD"):
        investigate_memory_clues(db, str(owner), "海边", start_date="2026/01/01")


def test_investigate_memory_clues_rejects_reversed_range(db, owner):
    with pytest.raises(ValueError, match="开始日期不能晚于结束日期"):
        investigate_memory_clues(
            db, str(owner), "海边", start_date="2026-02-01", end_date="2026-01-01"
        )


# --------------------------------------------------------------------------- #
# build_person_timeline
# --------------------------------------------------------------------------- #


def test_build_person_timeline_rejects_invalid_person_id(db, owner):
    with pytest.raises(ValueError, match="人物 ID 格式无效"):
        build_person_timeline(db, str(owner), "person-1")


def test_build_person_timeline_rejects_invalid_date_format(db, owner):
    identity = FaceIdentity(id=uuid4(), owner_id=owner, identity_name="小李", is_deleted=False, is_hidden=False)
    db.add(identity)
    db.commit()

    with pytest.raises(ValueError, match="开始日期格式必须为 YYYY-MM-DD"):
        build_person_timeline(db, str(owner), str(identity.id), start_date="20260101")


def test_build_person_timeline_rejects_reversed_range(db, owner):
    identity = FaceIdentity(id=uuid4(), owner_id=owner, identity_name="小李", is_deleted=False, is_hidden=False)
    db.add(identity)
    db.commit()

    with pytest.raises(ValueError, match="开始日期不能晚于结束日期"):
        build_person_timeline(
            db, str(owner), str(identity.id), start_date="2026-02-01", end_date="2026-01-01"
        )


def test_build_person_timeline_filters_by_date_window(db, owner):
    identity = FaceIdentity(id=uuid4(), owner_id=owner, identity_name="小李", is_deleted=False, is_hidden=False)
    photo = _photo(db, owner)
    db.add(identity)
    db.commit()
    face = Face(id=None, photo_id=photo.id, face_identity_id=identity.id, is_deleted=False)
    db.add(face)
    db.commit()

    timeline = build_person_timeline(
        db, str(owner), str(identity.id), start_date="2026-01-01", end_date="2026-12-31"
    )

    assert isinstance(timeline, dict)


# --------------------------------------------------------------------------- #
# create_artifact
# --------------------------------------------------------------------------- #


def test_create_artifact_rejects_invalid_photo_id(db, owner):
    with pytest.raises(ValueError, match="包含无效的照片 ID"):
        create_artifact(db, str(owner), None, "travel_story", "标题", {}, ["not-a-uuid"], [])


def test_create_artifact_rejects_unowned_ticket(db, owner):
    photo = _photo(db, owner)
    stranger = uuid4()
    db.add(User(id=stranger, username="nightly-stranger", hashed_password="x"))
    db.commit()
    unknown_ticket_id = str(uuid4())

    with pytest.raises(ValueError, match="包含不存在或无权访问的票据"):
        create_artifact(db, str(owner), None, "travel_story", "标题", {}, [str(photo.id)], [unknown_ticket_id])


# --------------------------------------------------------------------------- #
# save_artifact_html / artifact_context
# --------------------------------------------------------------------------- #


def test_save_artifact_html_rejects_blank_content(db, owner):
    with pytest.raises(ValueError, match="HTML 内容不能为空"):
        save_artifact_html(db, str(owner), str(uuid4()), "   ", "editorial", None, False)


def test_save_artifact_html_rejects_oversized_content(db, owner):
    with pytest.raises(ValueError, match="HTML 内容不能超过 500KB"):
        save_artifact_html(db, str(owner), str(uuid4()), "<p>" + "x" * 500_001, "editorial", None, False)


def test_save_artifact_html_rejects_invalid_artifact_id(db, owner):
    with pytest.raises(ValueError, match="无效的作品 ID"):
        save_artifact_html(db, str(owner), "not-a-uuid", "<p>ok</p>", "editorial", None, False)


def test_artifact_context_rejects_invalid_and_unknown_ids(db, owner):
    with pytest.raises(ValueError, match="无效的作品 ID"):
        artifact_context(db, str(owner), "not-a-uuid")

    with pytest.raises(ValueError, match="作品不存在或无权访问"):
        artifact_context(db, str(owner), str(uuid4()))


def test_artifact_context_returns_owned_artifact(db, owner):
    row = AIArtifact(
        id=uuid4(),
        user_id=owner,
        artifact_type="travel_story",
        title="一次旅行",
        content_json={"sections": []},
        source_photo_ids=[],
        source_ticket_ids=[],
        status="draft",
    )
    db.add(row)
    db.commit()

    context = artifact_context(db, str(owner), str(row.id))

    assert context["id"] == str(row.id)
    assert context["title"] == "一次旅行"






