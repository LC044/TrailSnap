"""Exercise location cover selection on SQLite with real SQL and bounded loads."""

from datetime import datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.crud.location import get_locations
from app.crud.scene import get_scenes
from app.db.base import Base
from app.db.models.photo import FileType, Photo
from app.db.models.photo_metadata import PhotoMetadata
from app.db.models.scene import Scene
from app.schemas.location import Location

pytestmark = [pytest.mark.smoke, pytest.mark.module_location]


@pytest.fixture
def location_db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db
    engine.dispose()


def add_photo(db, owner, *, at="2024-01-01", deleted=False, scene_id=None,
              city="城市", province="省份", district="区县", photo_id=None):
    photo_id = photo_id or uuid4()
    db.add(Photo(
        id=photo_id, owner_id=owner, filename="cover.jpg", file_path="/isolated/cover.jpg",
        file_type=FileType.image, size=123, is_deleted=deleted,
        photo_time=datetime.fromisoformat(at) if at else None,
    ))
    db.add(PhotoMetadata(photo_id=photo_id, city=city, province=province,
                         district=district, scene_id=scene_id))
    return photo_id


@pytest.mark.parametrize("level", ["city", "province", "district"])
def test_latest_cover_loads_one_photo_per_group(location_db, level):
    db = location_db
    owner = uuid4()
    for _ in range(250):
        add_photo(db, owner)
    latest = add_photo(db, owner, at="2024-03-01")
    add_photo(db, owner, at=None)
    add_photo(db, owner, at="2025-01-01", deleted=True)
    add_photo(db, uuid4(), at="2025-01-01")
    add_photo(db, owner, city="", province="", district="")
    db.commit()
    db.expunge_all()

    loaded = []
    statements = []

    def on_load(session, instance):
        if isinstance(instance, Photo):
            loaded.append(instance.id)

    def on_execute(*args):
        statements.append(args[2])

    event.listen(db, "loaded_as_persistent", on_load)
    event.listen(db.bind, "before_cursor_execute", on_execute)
    try:
        locations = get_locations(db, owner, level)
        payload = [Location.model_validate(row).model_dump() for row in locations]
    finally:
        event.remove(db, "loaded_as_persistent", on_load)
        event.remove(db.bind, "before_cursor_execute", on_execute)

    assert len(payload) == 1
    assert payload[0]["count"] == 252
    assert payload[0]["cover"]["id"] == latest
    assert loaded == [latest]
    assert len(statements) == 2


def test_date_filters_pagination_and_cover_ties(location_db):
    db = location_db
    owner = uuid4()
    add_photo(db, owner, city="最多的城市")
    add_photo(db, owner, city="最多的城市")
    add_photo(db, owner, city="最多的城市")
    add_photo(db, owner, city="第二城市", at="2023-12-31")
    add_photo(db, owner, city="第二城市", photo_id=UUID(int=1))
    latest = add_photo(db, owner, city="第二城市", photo_id=UUID(int=2))
    add_photo(db, owner, city="第二城市", at="2024-02-01")
    add_photo(db, owner, city="第三城市", at=None)
    db.commit()

    result = get_locations(db, owner, skip=1, limit=1,
                           start_date="2024-01-01", end_date="2024-01-31")
    assert len(result) == 1
    assert result[0]["name"] == "第二城市"
    assert result[0]["count"] == 2
    assert result[0]["cover"].id == latest
    assert get_locations(db, owner, skip=10) == []


def test_same_name_scenes_keep_their_own_covers(location_db):
    db = location_db
    owner = uuid4()
    first, second = uuid4(), uuid4()
    db.add_all([Scene(id=first, name="同名景区"), Scene(id=second, name="同名景区")])
    first_cover = add_photo(db, owner, scene_id=first)
    second_cover = add_photo(db, owner, scene_id=second, at="2024-02-01")
    db.commit()

    result = get_locations(db, owner, level="scene")
    assert len(result) == 2
    covers = {row["id"]: row["cover"].id for row in result}
    assert covers == {str(first): first_cover, str(second): second_cover}


def test_scene_list_loads_only_latest_cover_and_keeps_empty_scenes(location_db):
    db = location_db
    owner = uuid4()
    scene_id, empty_id = uuid4(), uuid4()
    db.add_all([Scene(id=scene_id, name="景区"), Scene(id=empty_id, name="空景区")])
    for _ in range(250):
        add_photo(db, owner, scene_id=scene_id)
    latest = add_photo(db, owner, scene_id=scene_id, at="2024-02-01")
    add_photo(db, uuid4(), scene_id=scene_id, at="2025-01-01")
    db.commit()
    db.expunge_all()

    result = get_scenes(db, owner_id=owner)
    assert len(result) == 2
    by_id = {scene.id: scene for scene in result}
    assert by_id[scene_id].photo_count == 251
    assert by_id[scene_id].cover.id == latest
    assert by_id[empty_id].photo_count == 0
    assert by_id[empty_id].cover is None
    assert sum(isinstance(item, Photo) for item in db.identity_map.values()) == 1
    filtered = get_scenes(db, owner_id=owner, start_date="2024-02-01", end_date="2024-02-29")
    assert len(filtered) == 1
    assert filtered[0].photo_count == 1
    assert filtered[0].cover.id == latest
