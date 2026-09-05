from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models.agent import AgentSession
from app.db.models.ai_artifact import AIArtifact
from app.db.models.photo import FileType, Photo
from app.db.models.photo_metadata import PhotoMetadata
from app.db.models.user import User
from app.service.agent.album_p0 import create_artifact, discover_travel_periods, photo_contexts, save_artifact_html
from app.service.agent.skills import get_skill_catalog, load_skill
from app.service.agent.service import ThinkTagStreamFilter

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


def test_skill_registry_is_allowlisted_and_loads_expected_workflows():
    names = {item["name"] for item in get_skill_catalog()}
    assert {"trailsnap-search", "travel-story", "nine-grid-selection", "album-organizer", "travel-album"} <= names
    assert "create_artifact_draft" in load_skill("travel-story")["instructions"]
    with pytest.raises(ValueError):
        load_skill("../../secrets")


def test_think_tag_filter_handles_tags_split_across_stream_chunks():
    parser = ThinkTagStreamFilter()
    visible, reasoning = [], []
    for chunk in ("开场<th", "ink>内部", "思考</thi", "nk>答案"):
        current_visible, current_reasoning = parser.feed(chunk)
        visible.append(current_visible); reasoning.append(current_reasoning)
    tail_visible, tail_reasoning = parser.flush()
    assert "".join(visible) + tail_visible == "开场答案"
    assert "".join(reasoning) + tail_reasoning == "内部思考"


def test_photo_context_and_artifact_are_owner_scoped(db):
    owner, stranger = uuid4(), uuid4()
    db.add_all([
        User(id=owner, username="owner", hashed_password="x"),
        User(id=stranger, username="stranger", hashed_password="x"),
    ])
    session = AgentSession(id=uuid4(), user_id=owner, title="trip")
    owned_photo = Photo(id=uuid4(), owner_id=owner, filename="owned.jpg", file_path="owned.jpg", file_type=FileType.image, is_deleted=False)
    foreign_photo = Photo(id=uuid4(), owner_id=stranger, filename="foreign.jpg", file_path="foreign.jpg", file_type=FileType.image, is_deleted=False)
    db.add_all([session, owned_photo, foreign_photo]); db.commit()

    contexts = photo_contexts(db, str(owner), [str(owned_photo.id), str(foreign_photo.id)])
    assert [row["photo_id"] for row in contexts] == [str(owned_photo.id)]
    artifact = create_artifact(db, str(owner), str(session.id), "travel_story", "一次旅行", {"sections": []}, [str(owned_photo.id)], [])
    assert isinstance(artifact, AIArtifact)
    assert artifact.status == "draft"
    updated = save_artifact_html(
        db, str(owner), str(artifact.id),
        f"<!doctype html><main><h1>{'旅行故事' * 25}</h1><img src='/api/medias/{owner}/{owned_photo.id}/thumbnail'></main>",
        "editorial", "留白和大标题", True,
    )
    assert updated.html_content.startswith("<!doctype html>")
    assert updated.html_config["server_api_access"] is True
    assert updated.version == 2
    with pytest.raises(ValueError):
        create_artifact(db, str(owner), str(session.id), "travel_story", "越权", {}, [str(foreign_photo.id)], [])
    with pytest.raises(ValueError):
        save_artifact_html(db, str(stranger), str(artifact.id), "<p>越权</p>", "custom", None, False)
    with pytest.raises(ValueError, match="DOM"):
        save_artifact_html(
            db, str(owner), str(artifact.id),
            f"<main><h1>{'A' * 90}</h1></main><script>const photo = '{owned_photo.id}'</script>",
            "custom", None, False,
        )


def test_artifact_content_normalizes_model_field_aliases(db):
    owner = uuid4()
    db.add(User(id=owner, username="normalizer", hashed_password="x"))
    session = AgentSession(id=uuid4(), user_id=owner, title="trip")
    photo = Photo(
        id=uuid4(), owner_id=owner, filename="memory.jpg", file_path="memory.jpg",
        file_type=FileType.image, is_deleted=False,
    )
    db.add_all([session, photo]); db.commit()

    artifact = create_artifact(
        db, str(owner), str(session.id), "travel_story", "旅行", {
            "summary": "摘要",
            "sections": [{"title": "城墙", "narrative": "冬日的光。", "photo_id": str(photo.id)}],
        }, [str(photo.id)], [],
    )
    assert artifact.content_json["sections"] == [{
        "title": "城墙", "narrative": "冬日的光。", "photo_id": str(photo.id),
        "heading": "城墙", "body": "冬日的光。", "photo_ids": [str(photo.id)],
    }]


def test_discover_travel_periods_groups_consecutive_location_days(db):
    owner = uuid4()
    db.add(User(id=owner, username="traveler", hashed_password="x"))
    photos = []
    for index, (offset, city) in enumerate(((0, "西安"), (0, "西安"), (1, "咸阳"), (5, "上海"))):
        photo = Photo(
            id=uuid4(), owner_id=owner, filename=f"trip-{index}.jpg", file_path=f"trip-{index}.jpg",
            file_type=FileType.image, is_deleted=False,
            photo_time=datetime(2026, 10, 1) + timedelta(days=offset),
        )
        photos.append(photo)
        db.add(photo)
        db.flush()
        db.add(PhotoMetadata(photo_id=photo.id, city=city, country="中国"))
    db.commit()

    result = discover_travel_periods(db, str(owner), "2026-10-01", "2026-10-07", min_photos=3)
    assert result["candidate_count"] == 1
    candidate = result["candidates"][0]
    assert candidate["start_date"] == "2026-10-01"
    assert candidate["end_date"] == "2026-10-02"
    assert candidate["photo_count"] == 3
    assert candidate["locations"] == ["西安", "咸阳"]
