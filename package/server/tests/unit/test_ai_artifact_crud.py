from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.crud import ai_artifact
from app.db.base import Base
from app.db.models.ai_artifact import AIArtifact
from app.db.models.user import User
from app.schemas.ai_artifact import AIArtifactUpdate

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


def _user(db, name: str):
    user = User(id=uuid4(), username=name, hashed_password="x")
    db.add(user)
    db.commit()
    return user


def _artifact(user_id, title: str, updated_at: datetime):
    return AIArtifact(
        user_id=user_id,
        artifact_type="travel_story",
        title=title,
        content_json={"summary": "旅行摘要"},
        html_content=None,
        html_config={"style_name": "editorial"},
        source_photo_ids=[],
        source_ticket_ids=[],
        status="draft",
        version=1,
        updated_at=updated_at,
    )


def test_get_owned_is_user_scoped(db):
    owner, stranger = _user(db, "artifact-owner"), _user(db, "artifact-stranger")
    artifact = _artifact(owner.id, "西安秋日", datetime(2026, 9, 5, 8, 0, 0))
    db.add(artifact)
    db.commit()

    assert ai_artifact.get_owned(db, artifact.id, owner.id).id == artifact.id
    assert ai_artifact.get_owned(db, artifact.id, stranger.id) is None
    assert ai_artifact.get_owned(db, str(artifact.id), owner.id).id == artifact.id


def test_list_owned_orders_recent_and_paginates(db):
    owner = _user(db, "artifact-list-owner")
    stranger = _user(db, "artifact-list-stranger")
    old = _artifact(owner.id, "old", datetime(2026, 9, 1, 8, 0, 0))
    middle = _artifact(owner.id, "middle", datetime(2026, 9, 3, 8, 0, 0))
    newest = _artifact(owner.id, "newest", datetime(2026, 9, 5, 8, 0, 0))
    foreign = _artifact(stranger.id, "foreign", datetime(2026, 9, 6, 8, 0, 0))
    db.add_all([old, middle, newest, foreign])
    db.commit()

    assert [item.title for item in ai_artifact.list_owned(db, owner.id)] == ["newest", "middle", "old"]
    assert [item.title for item in ai_artifact.list_owned(db, owner.id, skip=1, limit=1)] == ["middle"]
    assert [item.title for item in ai_artifact.list_owned(db, stranger.id)] == ["foreign"]


def test_update_only_changes_supplied_fields_and_bumps_version(db):
    owner = _user(db, "artifact-update-owner")
    artifact = _artifact(owner.id, "原标题", datetime(2026, 9, 5, 8, 0, 0))
    db.add(artifact)
    db.commit()

    updated = ai_artifact.update(
        db,
        artifact,
        AIArtifactUpdate(title="新标题", html_config={"style_name": "cinematic", "server_api_access": True}),
    )

    assert updated.title == "新标题"
    assert updated.html_config == {"style_name": "cinematic", "server_api_access": True}
    assert updated.content_json == {"summary": "旅行摘要"}
    assert updated.status == "draft"
    assert updated.version == 2

    published = ai_artifact.update(db, artifact, AIArtifactUpdate(status="published"))
    assert published.title == "新标题"
    assert published.status == "published"
    assert published.version == 3
