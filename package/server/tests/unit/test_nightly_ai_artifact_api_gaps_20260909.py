"""2026-09-09 nightly gap tests for the AI artifact API.

These tests exercise the router layer directly so ownership checks, share
tokens, and HTML export headers are covered without starting the HTTP app.
"""
from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api import ai_artifact as artifact_api
from app.db.base import Base
from app.db.models.ai_artifact import AIArtifact
from app.db.models.user import User

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


def _user(db, name):
    user = User(id=uuid4(), username=name, hashed_password="x")
    db.add(user)
    db.commit()
    return user


def _artifact(user_id):
    return AIArtifact(
        user_id=user_id,
        artifact_type="travel_story",
        title="九寨沟流水账",
        content_json={"summary": "秋天很美", "sections": [{"heading": "湖", "body": "蓝色的水"}]},
        html_content=None,
        html_config={"style_name": "editorial"},
        source_photo_ids=[],
        source_ticket_ids=[],
        status="draft",
        version=1,
        updated_at=datetime(2026, 9, 8, 8, 0, 0),
    )


def test_list_artifact_endpoint_returns_serialized_rows(db):
    user = _user(db, "artifact-api-owner")
    artifact = _artifact(user.id)
    db.add(artifact)
    db.commit()

    response = artifact_api.list_artifacts(skip=0, limit=20, current_user=user, db=db)
    assert response.code == 0
    assert response.data[0]["title"] == "九寨沟流水账"
    assert response.data[0]["artifact_type"] == "travel_story"


def test_get_artifact_endpoint_rejects_foreign_or_missing_rows(db):
    owner, stranger = _user(db, "artifact-api-a"), _user(db, "artifact-api-b")
    artifact = _artifact(owner.id)
    db.add(artifact)
    db.commit()

    assert artifact_api.get_artifact(str(artifact.id), current_user=owner, db=db).data["id"] == str(artifact.id)
    with pytest.raises(Exception) as foreign:
        artifact_api.get_artifact(str(artifact.id), current_user=stranger, db=db)
    with pytest.raises(Exception) as missing:
        artifact_api.get_artifact(str(uuid4()), current_user=owner, db=db)
    assert foreign.value.status_code == 404
    assert missing.value.status_code == 404


def test_export_artifact_html_sets_download_and_referrer_headers(db):
    user = _user(db, "artifact-api-export")
    artifact = _artifact(user.id)
    db.add(artifact)
    db.commit()

    response = artifact_api.export_artifact_html(str(artifact.id), current_user=user, db=db)
    assert response.status_code == 200
    assert response.media_type.startswith("text/html")
    assert "attachment; filename=trailsnap-story.html" in response.headers["content-disposition"]
    assert response.headers["referrer-policy"] == "no-referrer"
    assert "蓝色的水" in response.body.decode("utf-8")


def test_share_public_and_revoke_artifact_flow(db):
    user = _user(db, "artifact-api-share")
    artifact = _artifact(user.id)
    db.add(artifact)
    db.commit()

    share = artifact_api.share_artifact(str(artifact.id), current_user=user, db=db)
    token = share.data["share_path"].rsplit(".", 1)[1]
    public = artifact_api.get_shared_artifact(f"{artifact.id}.{token}", db=db)
    assert public.status_code == 200
    assert "Content-Security-Policy" in public.headers
    assert artifact.version == 2
    assert artifact.html_config["share"]["enabled"] is True

    revoked = artifact_api.revoke_artifact_share(str(artifact.id), current_user=user, db=db)
    assert revoked.data == {"revoked": True}
    assert "share" not in artifact.html_config
    assert artifact.version == 3

    with pytest.raises(Exception) as exc:
        artifact_api.get_shared_artifact(f"{artifact.id}.{token}", db=db)
    assert exc.value.status_code == 404


def test_public_artifact_rejects_malformed_share_token(db):
    _user(db, "artifact-api-malformed")
    with pytest.raises(Exception) as exc:
        artifact_api.get_shared_artifact("not-a-token", db=db)
    assert exc.value.status_code == 404
