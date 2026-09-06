from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models.agent import AgentSession
from app.db.models.ai_artifact import AIArtifact
from app.db.models.album import Album, AlbumPhoto
from app.db.models.photo import FileType, Photo
from app.db.models.tag import PhotoTag, PhotoTagRelation
from app.db.models.user import User
from app.service.agent.actions import execute_plan, get_owned_plan, mark_plan_failed, propose_album_plan, reject_plan, undo_plan


pytestmark = [pytest.mark.smoke]


@pytest.fixture()
def prepared_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    # Match production SessionLocal, where autoflush is deliberately disabled.
    db = sessionmaker(bind=engine, autoflush=False)()
    owner, stranger = uuid4(), uuid4()
    db.add_all([
        User(id=owner, username="p1-owner", hashed_password="x"),
        User(id=stranger, username="p1-stranger", hashed_password="x"),
    ])
    session = AgentSession(id=uuid4(), user_id=owner, title="organize")
    photos = [
        Photo(id=uuid4(), owner_id=owner, filename=f"{index}.jpg", file_path=f"{index}.jpg", file_type=FileType.image, is_deleted=False)
        for index in range(3)
    ]
    foreign = Photo(id=uuid4(), owner_id=stranger, filename="foreign.jpg", file_path="foreign.jpg", file_type=FileType.image, is_deleted=False)
    db.add_all([session, *photos, foreign])
    db.commit()
    try:
        yield db, owner, stranger, session, photos, foreign
    finally:
        db.close()
        engine.dispose()


def test_create_album_plan_execute_and_undo(prepared_db):
    db, owner, _, session, photos, _ = prepared_db
    plan = propose_album_plan(
        db, owner, session.id, "云南六日", "按天整理的旅行相册",
        [photo.id for photo in photos], photos[1].id, ["云南", "旅行"], summary="准备创建旅行相册",
    )
    assert plan.status == "proposed"
    assert plan.preview["photo_count"] == 3
    assert db.query(Album).count() == 0
    assert db.query(PhotoTagRelation).count() == 0

    executed = execute_plan(db, owner, plan.id)
    album_id = executed.result["album_id"]
    album = db.query(Album).filter(Album.id == album_id).one()
    assert executed.status == "executed"
    assert album.name == "云南六日"
    assert album.cover_id == photos[1].id
    assert album.num_photos == 3
    assert db.query(AlbumPhoto).filter(AlbumPhoto.album_id == album.id).count() == 3
    assert db.query(PhotoTagRelation).count() == 6

    undone = undo_plan(db, owner, plan.id)
    assert undone.status == "undone"
    assert db.query(Album).filter(Album.id == album.id).first() is None
    assert db.query(PhotoTagRelation).count() == 0
    assert db.query(PhotoTag).count() == 0


def test_update_album_undo_restores_fields_and_keeps_existing_relations(prepared_db):
    db, owner, _, session, photos, _ = prepared_db
    album = Album(name="旧相册", description="旧简介", type="user", owner_id=owner, cover_id=photos[0].id, num_photos=1)
    tag = PhotoTag(tag_name="已有标签", type="custom", owner_id=owner)
    db.add_all([album, tag]); db.flush()
    db.add_all([
        AlbumPhoto(album_id=album.id, photo_id=photos[0].id),
        PhotoTagRelation(photo_id=photos[0].id, tag_id=tag.id, confidence=1.0),
    ])
    db.commit()

    plan = propose_album_plan(
        db, owner, session.id, "新相册", "新简介", [photo.id for photo in photos],
        photos[2].id, ["已有标签"], album_id=album.id,
    )
    execute_plan(db, owner, plan.id)
    db.refresh(album)
    assert (album.name, album.description, album.cover_id, album.num_photos) == ("新相册", "新简介", photos[2].id, 3)
    assert db.query(PhotoTagRelation).filter(PhotoTagRelation.tag_id == tag.id).count() == 3

    undo_plan(db, owner, plan.id)
    db.refresh(album)
    assert (album.name, album.description, album.cover_id, album.num_photos) == ("旧相册", "旧简介", photos[0].id, 1)
    assert db.query(AlbumPhoto).filter(AlbumPhoto.album_id == album.id).count() == 1
    assert db.query(PhotoTagRelation).filter(PhotoTagRelation.tag_id == tag.id).count() == 1


def test_plan_rejects_foreign_photos_and_cross_owner_access(prepared_db):
    db, owner, stranger, session, photos, foreign = prepared_db
    with pytest.raises(ValueError, match="不属于当前用户"):
        propose_album_plan(db, owner, session.id, "越权", None, [photos[0].id, foreign.id])

    plan = propose_album_plan(db, owner, session.id, "安全相册", None, [photos[0].id])
    assert get_owned_plan(db, stranger, plan.id) is None
    with pytest.raises(ValueError, match="不存在"):
        execute_plan(db, stranger, plan.id)


def test_plan_cannot_execute_or_undo_twice(prepared_db):
    db, owner, _, session, photos, _ = prepared_db
    plan = propose_album_plan(db, owner, session.id, "一次性计划", None, [photos[0].id])
    execute_plan(db, owner, plan.id)
    with pytest.raises(ValueError, match="待确认"):
        execute_plan(db, owner, plan.id)
    undo_plan(db, owner, plan.id)
    with pytest.raises(ValueError, match="已执行"):
        undo_plan(db, owner, plan.id)


def test_rejected_plan_is_auditable_and_cannot_execute(prepared_db):
    db, owner, _, session, photos, _ = prepared_db
    plan = propose_album_plan(db, owner, session.id, "不采用的方案", None, [photos[0].id])
    rejected = reject_plan(db, owner, plan.id)
    assert rejected.status == "rejected"
    assert db.query(Album).count() == 0
    with pytest.raises(ValueError, match="待确认"):
        execute_plan(db, owner, plan.id)
    with pytest.raises(ValueError, match="待确认"):
        reject_plan(db, owner, plan.id)


def test_plan_expires_and_failed_attempt_is_auditable(prepared_db):
    db, owner, _, session, photos, _ = prepared_db
    expired = propose_album_plan(db, owner, session.id, "过期计划", None, [photos[0].id])
    expired.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()
    with pytest.raises(ValueError, match="已过期"):
        execute_plan(db, owner, expired.id)
    db.refresh(expired)
    assert expired.status == "expired"
    assert expired.error_message

    failed = propose_album_plan(db, owner, session.id, "失败计划", None, [photos[0].id])
    marked = mark_plan_failed(db, owner, failed.id, "照片在执行前已被移除")
    assert marked.status == "failed"
    assert marked.attempt_count == 1
    assert marked.failed_at is not None
    assert "执行前" in marked.error_message


def test_travel_artifact_is_owner_scoped_and_linked_to_album_plan(prepared_db):
    db, owner, stranger, session, photos, _ = prepared_db
    artifact = AIArtifact(
        user_id=owner, artifact_type="travel_story", title="西安旅行日志",
        content_json={"sections": []}, source_photo_ids=[str(photos[0].id)], source_ticket_ids=[],
    )
    foreign_artifact = AIArtifact(
        user_id=stranger, artifact_type="travel_story", title="别人的日志",
        content_json={}, source_photo_ids=[], source_ticket_ids=[],
    )
    db.add_all([artifact, foreign_artifact]); db.commit()

    plan = propose_album_plan(
        db, owner, session.id, "西安旅行", None, [photos[0].id],
        artifact_id=artifact.id,
    )
    assert plan.preview["artifact_title"] == "西安旅行日志"
    assert plan.preview["artifact_url"].endswith(str(artifact.id))
    executed = execute_plan(db, owner, plan.id)
    assert executed.result["artifact_id"] == str(artifact.id)

    with pytest.raises(ValueError, match="无权访问"):
        propose_album_plan(
            db, owner, session.id, "越权旅行", None, [photos[0].id],
            artifact_id=foreign_artifact.id,
        )
