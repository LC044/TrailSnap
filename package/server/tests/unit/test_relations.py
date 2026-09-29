from datetime import datetime
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.db.models.face import Face, FaceIdentity
from app.db.models.image_vector import ImageVector
from app.db.models.memory import (
    Memory,
    MemoryPerson,
    MemoryPhoto,
    MemoryPlace,
    MemoryStatus,
)
from app.db.models.photo import FileType, Photo
from app.db.models.photo_metadata import PhotoMetadata
from app.db.models.user import User
from app.service.relations import (
    Relations,
    canonical_key,
    diversify_photos,
    parse_key,
    region_key,
    uuid_key,
)

pytestmark = [pytest.mark.smoke, pytest.mark.module_album]


@pytest.fixture
def graph(face_sqlite_session):
    db = face_sqlite_session
    owner = User(id=uuid4(), username="graph-owner", hashed_password="x")
    other = User(id=uuid4(), username="graph-other", hashed_password="x")
    db.add_all([owner, other])
    db.flush()
    a, b = [
        FaceIdentity(id=uuid4(), owner_id=owner.id, identity_name=name)
        for name in ("A", "B")
    ]
    foreign = FaceIdentity(id=uuid4(), owner_id=other.id, identity_name="A")
    db.add_all([a, b, foreign])
    photos = []
    for index, city in enumerate(("杭州", "杭州", "苏州")):
        photo = Photo(
            id=uuid4(),
            owner_id=owner.id,
            filename=f"p{index}.jpg",
            file_path=f"/p{index}.jpg",
            file_type=FileType.image,
            photo_time=datetime(2026, 9, index + 1),
            is_deleted=False,
        )
        db.add(photo)
        db.flush()
        db.add(
            PhotoMetadata(
                photo_id=photo.id,
                country="中国",
                province="浙江" if index < 2 else "江苏",
                city=city,
            )
        )
        photos.append(photo)
    for person, photo in [
        (a, photos[0]),
        (b, photos[1]),
        (a, photos[2]),
        (b, photos[2]),
        (b, photos[2]),
    ]:
        db.add(Face(photo_id=photo.id, face_identity_id=person.id, is_deleted=False))
    memories = []
    for index, members in enumerate(([photos[0], photos[1]], [photos[2]], [photos[2]])):
        memory = Memory(
            id=uuid4(),
            owner_id=owner.id,
            title=f"M{index}",
            status=MemoryStatus.CONFIRMED if index < 2 else MemoryStatus.CANDIDATE,
            start_time=datetime(2026, 9, index + 1),
        )
        db.add(memory)
        db.flush()
        for photo in members:
            db.add(MemoryPhoto(memory_id=memory.id, photo_id=photo.id))
        memories.append(memory)
    db.commit()
    return db, owner, other, a, b, foreign, photos, memories


def test_common_memory_is_not_the_same_as_a_shared_photo(graph):
    db, owner, _, a, b, _, photos, memories = graph
    service = Relations(db, owner.id)
    left, right = uuid_key("person", a.id), uuid_key("person", b.id)
    result = service.evidence(left, right)
    assert {node["id"] for node in result["items"]} == {
        uuid_key("memory", m.id) for m in memories[:2]
    }
    result = service.evidence(left, right, "photo")
    assert [node["id"] for node in result["items"]] == [uuid_key("photo", photos[2].id)]
    neighbors = service.neighbors(left, ["person"])
    edge = neighbors["edges"][0]
    assert edge["memory_count"] == 2
    assert edge["photo_count"] == 1


def test_hidden_people_deleted_photos_and_foreign_ids_are_filtered(graph):
    db, owner, _, a, b, foreign, photos, _ = graph
    b.is_hidden = True
    photos[0].is_deleted = True
    db.commit()
    service = Relations(db, owner.id)
    for key in [
        uuid_key("person", b.id),
        uuid_key("person", foreign.id),
        uuid_key("photo", photos[0].id),
    ]:
        with pytest.raises(HTTPException) as error:
            service.require(key)
        assert error.value.status_code == 404
    result = service.neighbors(uuid_key("person", a.id), ["person", "photo"])
    assert uuid_key("person", b.id) not in {row["id"] for row in result["nodes"]}
    assert uuid_key("photo", photos[0].id) not in {row["id"] for row in result["nodes"]}


def test_memory_status_and_same_object_semantics(graph):
    db, owner, _, a, b, _, _, memories = graph
    service = Relations(db, owner.id)
    ma, mb = [uuid_key("memory", row.id) for row in memories[:2]]
    assert service.evidence(ma, mb)["items"] == []
    assert service.evidence(ma, uuid_key("person", a.id))["items"][0]["id"] == ma
    with pytest.raises(HTTPException):
        service.evidence(ma, ma)
    memories[0].status = MemoryStatus.ARCHIVED
    db.commit()
    assert (
        len(
            service.evidence(uuid_key("person", a.id), uuid_key("person", b.id))[
                "items"
            ]
        )
        == 1
    )


def test_place_resolution_preserves_ambiguous_names_and_direct_evidence(graph):
    db, owner, _, a, _, _, photos, memories = graph
    resolved = MemoryPlace(
        memory_id=memories[0].id, name="杭州", level="city", source="inferred"
    )
    text = MemoryPlace(
        memory_id=memories[0].id, name="老家", level="custom", source="user"
    )
    stale = MemoryPlace(
        memory_id=memories[0].id, name="不存在的城市", level="city", source="inferred"
    )
    db.add_all([resolved, text, stale])
    db.commit()
    service = Relations(db, owner.id)
    key = region_key("city", ["中国", "浙江", "杭州"])
    result = service.neighbors(uuid_key("memory", memories[0].id), ["place"])
    ids = {node["id"] for node in result["nodes"]}
    assert key in ids
    assert f"place:unresolved:{text.id}" in ids
    assert f"place:unresolved:{stale.id}" not in ids
    assert service.require(key)["detail_target"]["place_key"] == key
    # Removing photos invalidates inferred text but preserves a user association.
    photos[0].is_deleted = photos[1].is_deleted = True
    db.commit()
    result = service.neighbors(uuid_key("memory", memories[0].id), ["place"])
    assert [node["id"] for node in result["nodes"]] == [f"place:unresolved:{text.id}"]


def test_pagination_is_bounded_deduplicated_and_context_bound(graph):
    db, owner, other, a, _, _, _, _ = graph
    service = Relations(db, owner.id)
    root = uuid_key("person", a.id)
    first = service.neighbors(root, ["person", "place", "memory", "photo"], limit=2)
    assert len(first["nodes"]) == 2 and first["has_more"]
    second = service.neighbors(
        root,
        ["person", "place", "memory", "photo"],
        limit=2,
        cursor=first["next_cursor"],
    )
    assert not ({n["id"] for n in first["nodes"]} & {n["id"] for n in second["nodes"]})
    with pytest.raises(HTTPException):
        service.neighbors(root, ["photo"], limit=2, cursor=first["next_cursor"])
    with pytest.raises(HTTPException):
        Relations(db, other.id)._cursor(
            first["next_cursor"],
            ["neighbors", root, sorted(["person", "place", "memory", "photo"]), 2],
        )
    with pytest.raises(HTTPException):
        service.neighbors(root, ["photo"], limit=1000)


def test_photo_neighbors_cover_different_days_and_places_before_burst_duplicates(graph):
    db, owner, _, person, _, _, original, _ = graph
    added = []
    for index in range(10):
        photo = Photo(
            id=uuid4(),
            owner_id=owner.id,
            filename=f"burst-{index}.jpg",
            file_path=f"/burst-{index}.jpg",
            file_type=FileType.image,
            photo_time=datetime(2026, 9, 6, 12, index),
            is_deleted=False,
        )
        db.add(photo)
        db.flush()
        db.add_all(
            [
                PhotoMetadata(photo_id=photo.id, country="中国", province="浙江", city="杭州"),
                Face(photo_id=photo.id, face_identity_id=person.id, is_deleted=False),
            ]
        )
        added.append(photo)
    different = Photo(
        id=uuid4(),
        owner_id=owner.id,
        filename="different-place.jpg",
        file_path="/different-place.jpg",
        file_type=FileType.image,
        photo_time=datetime(2026, 9, 5),
        is_deleted=False,
    )
    db.add(different)
    db.flush()
    db.add_all(
        [
            PhotoMetadata(photo_id=different.id, country="中国", province="广东", city="广州"),
            Face(photo_id=different.id, face_identity_id=person.id, is_deleted=False),
        ]
    )
    same_day_other_place = Photo(
        id=uuid4(),
        owner_id=owner.id,
        filename="same-day-other-place.jpg",
        file_path="/same-day-other-place.jpg",
        file_type=FileType.image,
        photo_time=datetime(2026, 9, 6, 13),
        is_deleted=False,
    )
    db.add(same_day_other_place)
    db.flush()
    db.add_all(
        [
            PhotoMetadata(photo_id=same_day_other_place.id, country="中国", province="浙江", city="宁波"),
            Face(photo_id=same_day_other_place.id, face_identity_id=person.id, is_deleted=False),
        ]
    )
    db.commit()

    service = Relations(db, owner.id)
    root = uuid_key("person", person.id)
    first = service.neighbors(root, ["photo"], limit=5)
    ids = {node["id"] for node in first["nodes"]}
    assert {
        uuid_key("photo", original[0].id),
        uuid_key("photo", original[2].id),
        uuid_key("photo", different.id),
        uuid_key("photo", same_day_other_place.id),
    } <= ids
    assert len(ids & {uuid_key("photo", photo.id) for photo in added}) == 1
    selected = next(node for node in first["nodes"] if node["id"] == uuid_key("photo", different.id))
    assert "2026年9月5日" in selected["subtitle"] and "广州" in selected["subtitle"]
    second = service.neighbors(root, ["photo"], limit=5, cursor=first["next_cursor"])
    assert not ids & {node["id"] for node in second["nodes"]}


def test_photo_neighbors_postpone_clip_near_duplicates_without_hiding_them(graph):
    db, owner, _, person, _, _, _, _ = graph
    photos = []
    for index in range(3):
        photo = Photo(
            id=uuid4(), owner_id=owner.id, filename=f"view-{index}.jpg",
            file_path=f"/view-{index}.jpg", file_type=FileType.image,
            photo_time=datetime(2026, 9, 10, 12, 3 - index), is_deleted=False,
        )
        db.add(photo)
        db.flush()
        db.add_all([
            PhotoMetadata(photo_id=photo.id, country="中国", province="浙江", city="杭州"),
            Face(photo_id=photo.id, face_identity_id=person.id, is_deleted=False),
            ImageVector(photo_id=photo.id, embedding=(
                [1.0, 0.0] if index < 2 else [0.0, 1.0]
            ) + [0.0] * 510),
        ])
        photos.append(photo)
    db.commit()

    service = Relations(db, owner.id)
    key = uuid_key("person", person.id)
    pages = []
    cursor = None
    while True:
        page = service.neighbors(key, ["photo"], limit=2, cursor=cursor)
        pages.extend(node["id"] for node in page["nodes"])
        if not page["has_more"]:
            break
        cursor = page["next_cursor"]
    ids = [uuid_key("photo", photo.id) for photo in photos]
    assert pages.index(ids[0]) < pages.index(ids[2]) < pages.index(ids[1])
    assert len(pages) == len(set(pages))


def test_visual_diversity_keeps_base_order_without_vectors():
    keys = ["first", "second", "third"]
    assert diversify_photos(keys, {}) == keys
    assert diversify_photos(keys, {
        "first": [1.0, 0.0], "second": [0.99, 0.01], "third": [0.0, 1.0]
    }) == ["first", "third", "second"]


def test_search_lists_only_owned_valid_nodes_and_escapes_wildcards(graph):
    db, owner, _, a, _, _, _, _ = graph
    service = Relations(db, owner.id)
    assert [node["id"] for node in service.search("person", "A")["items"]] == [
        uuid_key("person", a.id)
    ]
    assert service.search("person", "%")["items"] == []
    places = service.search("place", "杭州")["items"]
    assert len(places) == 1
    assert places[0]["subtitle"] == "中国 · 浙江"


def test_region_identity_is_unambiguous_even_with_separators():
    key = region_key("city", ["", "省:2", "城市😀"])
    assert parse_key(key) == ("place", ("city", ["", "省:2", "城市😀"]))
    assert canonical_key(key) == key
    assert region_key("city", ["中国", "辽宁", "朝阳"]) != region_key(
        "city", ["中国", "北京", "朝阳"]
    )
    for invalid in [
        "place:region:city:999:x",
        "place:unresolved:-1",
        "person:invalid",
        "place:region:city:0:0:1:xtrailing",
    ]:
        with pytest.raises(HTTPException):
            parse_key(invalid)


def test_explicit_person_link_survives_but_inferred_stale_link_does_not(graph):
    db, owner, _, a, b, _, photos, memories = graph
    db.add(MemoryPerson(memory_id=memories[0].id, face_identity_id=a.id, source="user"))
    db.add(
        MemoryPerson(memory_id=memories[0].id, face_identity_id=b.id, source="inferred")
    )
    photos[0].is_deleted = photos[1].is_deleted = True
    db.commit()
    nodes = Relations(db, owner.id).neighbors(
        uuid_key("memory", memories[0].id), ["person"]
    )["nodes"]
    assert [node["id"] for node in nodes] == [uuid_key("person", a.id)]


def test_photos_do_not_inherit_other_photos_people_from_the_same_memory(graph):
    db, owner, _, a, b, _, photos, _ = graph
    service = Relations(db, owner.id)
    nodes = service.neighbors(uuid_key("photo", photos[0].id), ["person"])["nodes"]
    assert [node["id"] for node in nodes] == [uuid_key("person", a.id)]
    nodes = service.neighbors(uuid_key("person", a.id), ["photo"])["nodes"]
    assert uuid_key("photo", photos[1].id) not in {node["id"] for node in nodes}


def test_hundred_neighbors_are_paged_and_scene_ownership_is_enforced(graph):
    from app.db.models.scene import Scene

    db, owner, other, a, _, _, photos, _ = graph
    for index in range(105):
        person = FaceIdentity(
            id=uuid4(), owner_id=owner.id, identity_name=f"Person {index}"
        )
        db.add(person)
        db.flush()
        db.add(
            Face(photo_id=photos[0].id, face_identity_id=person.id, is_deleted=False)
        )
    own_scene = Scene(id=uuid4(), name="空地点", owner_id=owner.id)
    foreign_scene = Scene(id=uuid4(), name="私有地点", owner_id=other.id)
    db.add_all([own_scene, foreign_scene])
    db.commit()
    service = Relations(db, owner.id)
    root, cursor, seen = uuid_key("person", a.id), None, set()
    while True:
        page = service.neighbors(root, ["person"], limit=20, cursor=cursor)
        ids = {node["id"] for node in page["nodes"]}
        assert len(ids) <= 20 and not (ids & seen)
        seen |= ids
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert len(seen) == 106
    assert (
        service.neighbors(uuid_key("place:scene", own_scene.id), ["person"])["nodes"]
        == []
    )
    with pytest.raises(HTTPException):
        service.require(uuid_key("place:scene", foreign_scene.id))


def test_exact_location_detail_does_not_mix_namesakes(graph):
    from app.crud.location import get_location_photos

    db, owner, _, _, _, _, photos, _ = graph
    for photo, province in [(photos[0], "浙江"), (photos[1], "其他省")]:
        metadata = db.get(PhotoMetadata, photo.id)
        metadata.city, metadata.province = "同名城", province
    db.commit()
    rows = get_location_photos(
        db, owner.id, "同名城", place_key=region_key("city", ["中国", "浙江", "同名城"])
    )
    assert [row.id for row in rows] == [photos[0].id]
    metadata = db.get(PhotoMetadata, photos[0].id)
    metadata.city = " 同名城 "
    db.commit()
    rows = get_location_photos(
        db, owner.id, "同名城", place_key=region_key("city", ["中国", "浙江", "同名城"])
    )
    assert [row.id for row in rows] == [photos[0].id]


def test_query_timeout_returns_an_error_and_restores_connection(graph):
    import sqlite3
    from sqlalchemy import text
    from sqlalchemy.exc import OperationalError
    from app.api.relations import _respond

    db = graph[0]

    def interrupted():
        raise OperationalError("query", {}, sqlite3.OperationalError("interrupted"))

    response = _respond(db, interrupted)
    assert response.code == 503 and response.data is None
    assert db.scalar(text("SELECT 1")) == 1


def test_api_contract_and_invalid_objects(graph):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.relations import router
    from app.api.deps import get_current_user
    from app.dependencies import get_db

    db, owner, _, a, b, foreign, _, _ = graph
    app = FastAPI()
    app.include_router(router, prefix="/relations")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: owner
    with TestClient(app) as client:
        result = client.get(
            "/relations/neighbors", params={"root": uuid_key("person", a.id)}
        ).json()
        assert result["code"] == 0 and result["data"]["center"]["type"] == "person"
        for node, code in [("person:bad", 400), (uuid_key("person", foreign.id), 404)]:
            result = client.get("/relations/neighbors", params={"root": node}).json()
            assert result["code"] == code and result["data"] is None
        result = client.get(
            "/relations/common-memories",
            params={
                "left": uuid_key("person", a.id),
                "right": uuid_key("person", b.id),
                "limit": 1,
            },
        ).json()["data"]
        assert result["has_more"] and len(result["items"]) == 1
        next_result = client.get(
            "/relations/common-memories",
            params={
                "left": uuid_key("person", a.id),
                "right": uuid_key("person", b.id),
                "limit": 1,
                "cursor": result["next_cursor"],
            },
        ).json()["data"]
        assert next_result["items"][0]["id"] != result["items"][0]["id"]
