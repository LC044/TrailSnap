from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models.agent import AgentSession
from app.db.models.ai_artifact import AIArtifact
from app.db.models.album import Album, AlbumPhoto
from app.db.models.face import Face, FaceIdentity
from app.db.models.image_description import ImageDescription
from app.db.models.ocr import OCR
from app.db.models.photo import FileType, Photo
from app.db.models.photo_metadata import PhotoMetadata
from app.db.models.user import User
from app.service.agent.album_p0 import album_health_report, build_person_timeline, create_artifact, discover_travel_periods, investigate_memory_clues, photo_contexts, save_artifact_html
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
    assert {"trailsnap-search", "travel-story", "nine-grid-selection", "album-organizer", "travel-album", "album-doctor", "memory-detective", "person-timeline"} <= names
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


def test_album_health_report_is_owner_scoped_and_explainable(db):
    owner, stranger = uuid4(), uuid4()
    db.add_all([
        User(id=owner, username="doctor-owner", hashed_password="x"),
        User(id=stranger, username="doctor-stranger", hashed_password="x"),
    ])
    album = Album(id=uuid4(), owner_id=owner, name="待体检", type="user", num_photos=9)
    p1 = Photo(
        id=uuid4(), owner_id=owner, filename="one.jpg", file_path="one.jpg", file_type=FileType.image,
        is_deleted=False, photo_time=datetime(2026, 1, 1), md5="same",
    )
    p2 = Photo(
        id=uuid4(), owner_id=owner, filename="two.jpg", file_path="two.jpg", file_type=FileType.image,
        is_deleted=False, photo_time=None, md5="same",
    )
    p3 = Photo(
        id=uuid4(), owner_id=owner, filename="three.jpg", file_path="three.jpg", file_type=FileType.image,
        is_deleted=False, photo_time=datetime(2026, 1, 2), md5=None,
    )
    foreign = Photo(
        id=uuid4(), owner_id=stranger, filename="foreign.jpg", file_path="foreign.jpg", file_type=FileType.image,
        is_deleted=False, photo_time=None, md5="same",
    )
    db.add_all([album, p1, p2, p3, foreign]); db.flush()
    db.add_all([
        AlbumPhoto(album_id=album.id, photo_id=p1.id), AlbumPhoto(album_id=album.id, photo_id=p2.id),
        PhotoMetadata(photo_id=p1.id, city="西安", country="中国"),
        ImageDescription(photo_id=p1.id, description="城市街景"),
    ])
    db.commit()

    report = album_health_report(db, str(owner), sample_limit=3)
    by_key = {item["key"]: item for item in report["issues"]}
    assert report["photo_count"] == 3
    assert by_key["missing_time"]["count"] == 1
    assert by_key["missing_location"]["count"] == 2
    assert by_key["missing_description"]["count"] == 2
    assert by_key["missing_hash"]["count"] == 1
    assert by_key["unassigned"]["count"] == 1
    assert by_key["exact_duplicates"]["count"] == 1
    assert by_key["exact_duplicates"]["group_count"] == 1
    assert report["album_issues"]["count_mismatches"][0]["actual_count"] == 2
    assert report["album_issues"]["missing_covers"] == [{"album_id": str(album.id), "name": "待体检"}]

    with pytest.raises(ValueError, match="无权"):
        album_health_report(db, str(stranger), str(album.id))


def test_memory_detective_fuses_clues_into_owner_scoped_events(db):
    owner, stranger = uuid4(), uuid4()
    db.add_all([
        User(id=owner, username="detective-owner", hashed_password="x"),
        User(id=stranger, username="detective-stranger", hashed_password="x"),
    ])
    friend = FaceIdentity(id=uuid4(), owner_id=owner, identity_name="小周", is_deleted=False, is_hidden=False)
    hidden_friend = FaceIdentity(id=uuid4(), owner_id=owner, identity_name="小周", is_deleted=False, is_hidden=True)
    p1 = Photo(id=uuid4(), owner_id=owner, filename="beach.jpg", file_path="beach.jpg", file_type=FileType.image,
               is_deleted=False, photo_time=datetime(2024, 7, 1, 18, 0))
    p2 = Photo(id=uuid4(), owner_id=owner, filename="sunset.jpg", file_path="sunset.jpg", file_type=FileType.image,
               is_deleted=False, photo_time=datetime(2024, 7, 2, 19, 0))
    p3 = Photo(id=uuid4(), owner_id=owner, filename="other.jpg", file_path="other.jpg", file_type=FileType.image,
               is_deleted=False, photo_time=datetime(2024, 8, 20, 12, 0))
    foreign = Photo(id=uuid4(), owner_id=stranger, filename="foreign.jpg", file_path="foreign.jpg", file_type=FileType.image,
                    is_deleted=False, photo_time=datetime(2024, 7, 1, 18, 0))
    hidden_face_photo = Photo(
        id=uuid4(), owner_id=owner, filename="hidden-person.jpg", file_path="hidden-person.jpg",
        file_type=FileType.image, is_deleted=False, photo_time=datetime(2024, 9, 1, 10, 0),
    )
    db.add_all([friend, hidden_friend, p1, p2, p3, foreign, hidden_face_photo]); db.flush()
    db.add_all([
        PhotoMetadata(photo_id=p1.id, city="青岛", address="海边"),
        PhotoMetadata(photo_id=p2.id, city="青岛", address="海边"),
        PhotoMetadata(photo_id=p3.id, city="北京"),
        PhotoMetadata(photo_id=foreign.id, city="青岛", address="海边"),
        ImageDescription(photo_id=p1.id, description="朋友在海边吃烧烤", narrative="夏日晚餐"),
        ImageDescription(photo_id=p2.id, description="海边日落", narrative="晚霞"),
        ImageDescription(photo_id=p3.id, description="室内烧烤", narrative="午餐"),
        ImageDescription(photo_id=foreign.id, description="朋友在海边吃烧烤"),
        Face(photo_id=p1.id, face_identity_id=friend.id, is_deleted=False),
        Face(photo_id=hidden_face_photo.id, face_identity_id=hidden_friend.id, is_deleted=False),
        OCR(photo_id=p1.id, text="海鲜烧烤", text_score=0.98),
    ])
    db.commit()

    result = investigate_memory_clues(
        db, str(owner), "前年夏天和朋友在海边吃烧烤", "2024-01-01", "2024-12-31",
        locations=["青岛"], persons=["小周"], text_terms=["烧烤", "海鲜"],
        semantic_photo_ids=[str(p2.id), str(foreign.id)],
    )

    assert result["candidate_photo_count"] == 3
    assert result["candidate_event_count"] == 2
    best = result["events"][0]
    assert best["start_date"] == "2024-07-01"
    assert best["end_date"] == "2024-07-02"
    assert best["photo_count"] == 2
    assert best["confidence"] == "high"
    assert {"location", "person", "description", "ocr", "semantic"} <= set(best["matched_types"])
    evidence_ids = {row["photo_id"] for event in result["events"] for row in event["evidence_photos"]}
    assert str(foreign.id) not in evidence_ids

    with pytest.raises(ValueError, match="至少需要"):
        investigate_memory_clues(db, str(owner), "只有模糊描述")


def test_memory_detective_splits_distant_periods_on_the_same_day(db):
    owner = uuid4()
    db.add(User(id=owner, username="time-split-owner", hashed_password="x"))
    morning = Photo(
        id=uuid4(), owner_id=owner, filename="morning.jpg", file_path="morning.jpg",
        file_type=FileType.image, is_deleted=False, photo_time=datetime(2026, 1, 17, 1, 0),
    )
    noon = Photo(
        id=uuid4(), owner_id=owner, filename="noon.jpg", file_path="noon.jpg",
        file_type=FileType.image, is_deleted=False, photo_time=datetime(2026, 1, 17, 12, 0),
    )
    db.add_all([morning, noon]); db.flush()
    db.add_all([
        PhotoMetadata(photo_id=morning.id, city="西安"),
        PhotoMetadata(photo_id=noon.id, city="西安"),
    ])
    db.commit()

    result = investigate_memory_clues(
        db, str(owner), "那天在西安的两段经历", "2026-01-17", "2026-01-17", locations=["西安"],
    )

    assert result["candidate_photo_count"] == 2
    assert result["candidate_event_count"] == 2
    assert [event["photo_count"] for event in result["events"]] == [1, 1]


def test_person_timeline_groups_years_events_and_visible_companions(db):
    owner, stranger = uuid4(), uuid4()
    db.add_all([
        User(id=owner, username="timeline-owner", hashed_password="x"),
        User(id=stranger, username="timeline-stranger", hashed_password="x"),
    ])
    person = FaceIdentity(id=uuid4(), owner_id=owner, identity_name="小周", is_deleted=False, is_hidden=False)
    companion = FaceIdentity(id=uuid4(), owner_id=owner, identity_name="小林", is_deleted=False, is_hidden=False)
    hidden = FaceIdentity(id=uuid4(), owner_id=owner, identity_name="隐藏人物", is_deleted=False, is_hidden=True)
    unnamed = FaceIdentity(id=uuid4(), owner_id=owner, identity_name="未命名", is_deleted=False, is_hidden=False)
    photos = [
        Photo(id=uuid4(), owner_id=owner, filename="2020-a.jpg", file_path="2020-a.jpg", file_type=FileType.image,
              is_deleted=False, photo_time=datetime(2020, 5, 1, 10, 0)),
        Photo(id=uuid4(), owner_id=owner, filename="2020-b.jpg", file_path="2020-b.jpg", file_type=FileType.image,
              is_deleted=False, photo_time=datetime(2020, 5, 2, 11, 0)),
        Photo(id=uuid4(), owner_id=owner, filename="2024.jpg", file_path="2024.jpg", file_type=FileType.image,
              is_deleted=False, photo_time=datetime(2024, 10, 1, 9, 0)),
    ]
    db.add_all([person, companion, hidden, unnamed, *photos]); db.flush()
    db.add_all([
        Face(photo_id=photos[0].id, face_identity_id=person.id, is_deleted=False),
        Face(photo_id=photos[0].id, face_identity_id=companion.id, is_deleted=False),
        Face(photo_id=photos[0].id, face_identity_id=hidden.id, is_deleted=False),
        Face(photo_id=photos[0].id, face_identity_id=unnamed.id, is_deleted=False),
        Face(photo_id=photos[1].id, face_identity_id=person.id, is_deleted=False),
        Face(photo_id=photos[2].id, face_identity_id=person.id, is_deleted=False),
        PhotoMetadata(photo_id=photos[0].id, city="杭州", address="西湖"),
        PhotoMetadata(photo_id=photos[1].id, city="杭州", address="西湖"),
        PhotoMetadata(photo_id=photos[2].id, city="西安", address="城墙"),
        ImageDescription(photo_id=photos[0].id, narrative="湖边散步", memory_score=80, quality_score=70),
        ImageDescription(photo_id=photos[1].id, narrative="春日合影", memory_score=70, quality_score=80),
        ImageDescription(photo_id=photos[2].id, narrative="秋日街景", memory_score=90, quality_score=90),
    ])
    db.commit()

    result = build_person_timeline(db, str(owner), str(person.id))

    assert result["person"]["name"] == "小周"
    assert result["total_photo_count"] == 3
    assert result["year_count"] == 2
    assert [(year["year"], year["photo_count"]) for year in result["years"]] == [(2024, 1), (2020, 2)]
    assert result["event_count"] == 2
    assert result["co_travelers"] == [{"name": "小林", "shared_photo_count": 1}]
    assert result["events"][0]["representative_photos"][0]["thumbnail_url"].endswith("/thumbnail")

    with pytest.raises(ValueError, match="已隐藏"):
        build_person_timeline(db, str(owner), str(hidden.id))
    with pytest.raises(ValueError, match="无权"):
        build_person_timeline(db, str(stranger), str(person.id))
