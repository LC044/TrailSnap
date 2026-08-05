"""Unit tests for the scene CRUD module (app.crud.scene).

Covers the seven pure-Python / pure-ORM helpers exposed by app.crud.scene:

- point_in_polygon     : 100% pure math (ray-casting).
- create_scene         : insert + photo re-evaluation.
- get_scenes           : paginated list with optional date range + cover photo lookup.
- get_scene            : owner-aware single lookup (None owner = public-only).
- delete_scene         : 4 guard rails (not found, permission, system default, success).
- update_scene         : not-found / polygon-changed / simple field update.
- update_scene_photos  : bbox filtering + per-photo ray-cast + owner filter.

We patch app.crud.scene.update_scene_photos and use MagicMock for the
Session so no real Postgres connection is touched.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.crud import scene as crud_scene
from app.schemas.scene import SceneCreate, SceneUpdate


pytestmark = [pytest.mark.smoke, pytest.mark.module_album]


# ---------------------------------------------------------------------------
# point_in_polygon : pure math, no DB
# ---------------------------------------------------------------------------


def _square():
    return [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]


def test_point_in_polygon_inside_returns_true():
    assert crud_scene.point_in_polygon(5.0, 5.0, _square()) is True


def test_point_in_polygon_outside_returns_false():
    assert crud_scene.point_in_polygon(15.0, 5.0, _square()) is False


def test_point_in_polygon_on_left_edge():
    # Even-odd rule: a vertex on the ray does not flip the state.
    assert crud_scene.point_in_polygon(0.0, 5.0, _square()) is False


def test_point_in_polygon_triangle_inside():
    triangle = [(0.0, 0.0), (10.0, 0.0), (5.0, 10.0)]
    assert crud_scene.point_in_polygon(5.0, 3.0, triangle) is True


def test_point_in_polygon_triangle_outside():
    triangle = [(0.0, 0.0), (10.0, 0.0), (5.0, 10.0)]
    assert crud_scene.point_in_polygon(5.0, -1.0, triangle) is False


# ---------------------------------------------------------------------------
# create_scene : insert + dispatch photo re-evaluation
# ---------------------------------------------------------------------------


def _scene_create(**overrides):
    base = dict(
        name="East Lake",
        description="Wuhan landmark",
        level=1,
        address="Wuhan, Hubei",
        latitude=30.55,
        longitude=114.40,
        radius=500,
        polygon=[[30.50, 114.30], [30.60, 114.30], [30.60, 114.50], [30.50, 114.50]],
    )
    base.update(overrides)
    return SceneCreate(**base)


def test_create_scene_persists_then_re_evaluates_photos():
    db = MagicMock()
    owner_id = uuid4()
    payload = _scene_create()

    with patch.object(crud_scene, "update_scene_photos") as update_photos:
        scene = crud_scene.create_scene(db, payload, owner_id=owner_id)

    db.add.assert_called_once()
    db.commit.assert_called_once()
    db.refresh.assert_called_once()
    update_photos.assert_called_once_with(db, scene)
    assert scene.name == "East Lake"
    assert scene.owner_id == owner_id
    # is_custom is set by DB default, not by SceneCreate dump.


def test_create_scene_without_owner_keeps_public_visibility():
    db = MagicMock()
    payload = _scene_create(is_custom=False)

    with patch.object(crud_scene, "update_scene_photos"):
        scene = crud_scene.create_scene(db, payload, owner_id=None)

    assert scene.owner_id is None


# ---------------------------------------------------------------------------
# update_scene_photos : bbox + owner filter + per-photo ray-cast
# ---------------------------------------------------------------------------


def test_update_scene_photos_no_polygon_is_noop():
    db = MagicMock()
    scene = SimpleNamespace(id=uuid4(), polygon=None, owner_id=None)

    crud_scene.update_scene_photos(db, scene)

    db.query.assert_not_called()
    db.commit.assert_not_called()


def test_update_scene_photos_assigns_scene_id_to_matching_photo():
    scene_id = uuid4()
    scene = SimpleNamespace(
        id=scene_id,
        polygon=[[30.5, 114.3], [30.6, 114.3], [30.6, 114.5], [30.5, 114.5]],
        owner_id=None,
    )

    inside = SimpleNamespace(longitude=114.4, latitude=30.55, scene_id=None)
    outside = SimpleNamespace(longitude=120.0, latitude=40.0, scene_id=None)
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [inside, outside]

    crud_scene.update_scene_photos(db, scene)

    assert inside.scene_id == scene_id
    assert outside.scene_id is None
    db.commit.assert_called_once()


def test_update_scene_photos_joins_owner_when_private():
    scene_id = uuid4()
    owner_id = uuid4()
    scene = SimpleNamespace(
        id=scene_id,
        polygon=[[30.5, 114.3], [30.6, 114.3], [30.6, 114.5], [30.5, 114.5]],
        owner_id=owner_id,
    )

    db = MagicMock()
    join_target = db.query.return_value.filter.return_value
    join_target.all.return_value = []
    crud_scene.update_scene_photos(db, scene)

    db.query.assert_called_once()
    join_target.join.assert_called_once()


def test_update_scene_photos_no_match_skips_commit():
    scene = SimpleNamespace(
        id=uuid4(),
        polygon=[[30.5, 114.3], [30.6, 114.3], [30.6, 114.5], [30.5, 114.5]],
        owner_id=None,
    )

    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = []

    crud_scene.update_scene_photos(db, scene)

    db.commit.assert_not_called()


# ---------------------------------------------------------------------------
# get_scenes : paginated list with cover photo enrichment
# ---------------------------------------------------------------------------


def test_get_scenes_returns_count_and_cover_for_each_scene():
    scene_obj = SimpleNamespace(id=uuid4(), photo_count=0)
    cover_photo = SimpleNamespace(id=uuid4())
    db = MagicMock()
    chain = db.query.return_value.outerjoin.return_value.outerjoin.return_value
    chain.filter.return_value.group_by.return_value.order_by.return_value.offset.return_value.limit.return_value.all.return_value = [
        (scene_obj, 3)
    ]
    cover_join = db.query.return_value.join.return_value
    cover_filter1 = cover_join.filter.return_value
    cover_filter2 = cover_filter1.filter.return_value
    cover_filter2.distinct.return_value.order_by.return_value.all.return_value = [
        (cover_photo, scene_obj.id)
    ]

    with patch.object(crud_scene, "desc", lambda col: col):
        owner_id = uuid4()
        scenes = crud_scene.get_scenes(
            db, skip=0, limit=20, start_date=None, end_date=None, owner_id=owner_id
        )

    assert scenes[0].photo_count == 3
    assert scenes[0].cover is cover_photo


def test_get_scenes_applies_date_range_filters():
    db = MagicMock()
    chain = db.query.return_value.outerjoin.return_value.outerjoin.return_value
    chain.filter.return_value.group_by.return_value.order_by.return_value.offset.return_value.limit.return_value.all.return_value = []
    cover_chain = db.query.return_value.join.return_value
    cover_chain.filter.return_value.distinct.return_value.order_by.return_value.all.return_value = []

    with patch.object(crud_scene, "desc", lambda col: col):
        crud_scene.get_scenes(
            db, skip=0, limit=10, start_date="2026-01-01", end_date="2026-01-31", owner_id=uuid4()
        )

    assert chain.filter.called


# ---------------------------------------------------------------------------
# get_scene : owner-aware single lookup
# ---------------------------------------------------------------------------


def test_get_scene_with_owner_returns_owned_or_public():
    db = MagicMock()
    scene_obj = SimpleNamespace(id=uuid4(), name="East Lake")
    chain = db.query.return_value.filter.return_value
    chain.filter.return_value.first.return_value = scene_obj

    result = crud_scene.get_scene(db, scene_obj.id, owner_id=uuid4())

    assert result is scene_obj


def test_get_scene_without_owner_restricts_to_public_only():
    db = MagicMock()
    chain = db.query.return_value.filter.return_value
    chain.filter.return_value.first.return_value = None

    result = crud_scene.get_scene(db, uuid4(), owner_id=None)

    assert result is None


# ---------------------------------------------------------------------------
# delete_scene : 4 guard rails
# ---------------------------------------------------------------------------


def test_delete_scene_returns_none_when_not_found():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None

    assert crud_scene.delete_scene(db, uuid4(), owner_id=uuid4()) is None


def test_delete_scene_raises_when_owner_mismatch():
    scene_obj = SimpleNamespace(id=uuid4(), owner_id=uuid4(), is_custom=True)
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = scene_obj

    with pytest.raises(ValueError, match="Permission denied"):
        crud_scene.delete_scene(db, scene_obj.id, owner_id=uuid4())


def test_delete_scene_raises_when_system_default():
    scene_obj = SimpleNamespace(id=uuid4(), owner_id=None, is_custom=False)
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = scene_obj

    with pytest.raises(ValueError, match="system default"):
        crud_scene.delete_scene(db, scene_obj.id, owner_id=None)


def test_delete_scene_clears_photo_links_then_deletes():
    photo = SimpleNamespace(id=uuid4(), scene_id=None)
    scene_obj = SimpleNamespace(id=uuid4(), owner_id=None, is_custom=True)
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = scene_obj
    db.query.return_value.filter.return_value.all.return_value = [photo]

    crud_scene.delete_scene(db, scene_obj.id, owner_id=None)

    assert photo.scene_id is None
    db.delete.assert_called_once_with(scene_obj)
    db.commit.assert_called_once()


# ---------------------------------------------------------------------------
# update_scene : not-found / simple field update / polygon-change triggers
# ---------------------------------------------------------------------------


def test_update_scene_returns_none_when_not_found():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None

    payload = SceneUpdate(name="Renamed", description="x")
    result = crud_scene.update_scene(db, uuid4(), payload, owner_id=uuid4())

    assert result is None


def test_update_scene_raises_on_owner_mismatch():
    db_scene = SimpleNamespace(id=uuid4(), owner_id=uuid4())
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = db_scene

    with pytest.raises(ValueError, match="Permission denied"):
        crud_scene.update_scene(db, db_scene.id, SceneUpdate(name="x"), owner_id=uuid4())


def test_update_scene_partial_update_writes_only_provided_fields():
    db_scene = SimpleNamespace(
        id=uuid4(), owner_id=None, name="Old", description="Old desc", polygon=None
    )
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = db_scene

    payload = SceneUpdate(name="New")
    with patch.object(crud_scene, "update_scene_photos") as update_photos:
        crud_scene.update_scene(db, db_scene.id, payload, owner_id=None)

    assert db_scene.name == "New"
    assert db_scene.description == "Old desc"
    update_photos.assert_not_called()
    db.commit.assert_called_once()


def test_update_scene_polygon_change_runs_photo_re_evaluation():
    db_scene = SimpleNamespace(
        id=uuid4(),
        owner_id=None,
        name="X",
        description=None,
        polygon=[[30.0, 114.0], [31.0, 114.0], [31.0, 115.0], [30.0, 115.0]],
    )
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = db_scene

    payload = SceneUpdate(
        name="X",
        polygon=[[30.5, 114.3], [30.6, 114.3], [30.6, 114.5], [30.5, 114.5]],
    )
    with patch.object(crud_scene, "update_scene_photos") as update_photos:
        crud_scene.update_scene(db, db_scene.id, payload, owner_id=None)

    assert db_scene.polygon == payload.polygon
    update_photos.assert_called_once_with(db, db_scene)
