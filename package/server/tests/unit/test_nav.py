"""Unit tests for custom navigation item resolution and validation."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.nav import (
    resolve_album,
    resolve_classification,
    resolve_location,
    resolve_nav_items,
    resolve_person,
    resolve_single_entity,
    update_nav_items,
)
from app.schemas.nav import NavItemRef, NavItemsUpdate


def test_resolve_single_entity_dispatches_location():
    """Location references use their name directly instead of UUID parsing."""
    ref = NavItemRef(entity_type="location", entity_id="杭州/西湖")
    user_id = uuid4()
    db = MagicMock()
    expected = MagicMock()

    with patch("app.api.nav.resolve_location", return_value=expected) as resolver:
        assert resolve_single_entity(ref, user_id, db) is expected

    resolver.assert_called_once_with("杭州/西湖", user_id, db)


def test_resolve_single_entity_returns_none_for_unknown_type():
    """Unknown reference types are ignored so stale config can be pruned."""
    ref = NavItemRef(entity_type="unknown", entity_id="anything")

    assert resolve_single_entity(ref, uuid4(), MagicMock()) is None


def test_resolve_single_entity_returns_none_when_resolver_raises():
    """Exceptions raised by a resolver are swallowed and return None."""
    ref = NavItemRef(entity_type="album", entity_id=str(uuid4()))

    with patch("app.api.nav.resolve_album", side_effect=RuntimeError("boom")):
        assert resolve_single_entity(ref, uuid4(), MagicMock()) is None


def test_resolve_album_returns_none_when_query_empty():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None

    assert resolve_album(str(uuid4()), uuid4(), db) is None


def test_resolve_album_builds_route_and_uses_cover():
    album_id = uuid4()
    user_id = uuid4()
    album = SimpleNamespace(
        id=album_id,
        name="Trip",
        cover_id=uuid4(),
        num_photos=12,
    )
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = album

    resolved = resolve_album(str(album_id), user_id, db)

    assert resolved.entity_type == "album"
    assert resolved.name == "Trip"
    assert resolved.cover_photo_id == str(album.cover_id)
    assert resolved.photo_count == 12
    assert resolved.route_path == f"/album/{album_id}"


def test_resolve_album_handles_missing_cover_and_zero_count():
    album = SimpleNamespace(name="Empty", cover_id=None, num_photos=None)
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = album

    resolved = resolve_album(str(uuid4()), uuid4(), db)

    assert resolved.cover_photo_id is None
    assert resolved.photo_count == 0


def test_resolve_person_falls_back_to_first_face_when_default_missing():
    identity_id = uuid4()
    default_face_id = uuid4()
    fallback_face = SimpleNamespace(
        photo_id=uuid4(), face_rect=[1, 2, 3, 4], is_deleted=False
    )
    identity = SimpleNamespace(
        id=identity_id,
        identity_name="Alice",
        default_face_id=default_face_id,
        is_deleted=False,
    )
    db = MagicMock()
    db.query.return_value.filter.return_value.first.side_effect = [identity, None, fallback_face]
    db.query.return_value.filter.return_value.scalar.return_value = 5

    resolved = resolve_person(str(identity_id), uuid4(), db)

    assert resolved.entity_type == "person"
    assert resolved.cover_photo_id == str(fallback_face.photo_id)
    assert resolved.cover_photo_face_rect == [1, 2, 3, 4]
    assert resolved.photo_count == 5
    assert resolved.route_path == f"/album/people/{identity_id}"


def test_resolve_person_returns_none_for_missing_identity():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None

    assert resolve_person(str(uuid4()), uuid4(), db) is None


def test_resolve_location_returns_none_when_no_photos():
    db = MagicMock()
    db.query.return_value.join.return_value.filter.return_value.scalar.return_value = 0

    assert resolve_location("上海", uuid4(), db) is None


def test_resolve_location_picks_most_recent_photo_as_cover():
    db = MagicMock()
    db.query.return_value.join.return_value.filter.return_value.scalar.return_value = 9
    cover = SimpleNamespace(id=uuid4())
    db.query.return_value.join.return_value.filter.return_value.order_by.return_value.first.return_value = cover

    resolved = resolve_location("上海", uuid4(), db)

    assert resolved.entity_type == "location"
    assert resolved.cover_photo_id == str(cover.id)
    assert resolved.photo_count == 9
    assert resolved.route_path == "/album/location/上海"


def test_resolve_location_returns_null_cover_when_no_time_photos():
    db = MagicMock()
    db.query.return_value.join.return_value.filter.return_value.scalar.return_value = 1
    db.query.return_value.join.return_value.filter.return_value.order_by.return_value.first.return_value = None

    resolved = resolve_location("上海", uuid4(), db)

    assert resolved.cover_photo_id is None
    assert resolved.photo_count == 1


def test_resolve_classification_uses_tag_cover_when_present():
    tag_id = uuid4()
    tag = SimpleNamespace(id=tag_id, tag_name="beach", cover_id=uuid4())
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = tag
    db.query.return_value.filter.return_value.scalar.return_value = 7

    resolved = resolve_classification(str(tag_id), uuid4(), db)

    assert resolved.entity_type == "classification"
    assert resolved.name == "beach"
    assert resolved.photo_count == 7
    assert resolved.route_path == "/album/classification/beach"


def test_resolve_classification_falls_back_to_relation_for_cover():
    tag = SimpleNamespace(id=uuid4(), tag_name="food", cover_id=None)
    relation = SimpleNamespace(photo_id=uuid4())
    db = MagicMock()
    db.query.return_value.filter.return_value.first.side_effect = [tag, relation]
    db.query.return_value.filter.return_value.scalar.return_value = 3

    resolved = resolve_classification(str(tag.id), uuid4(), db)

    assert resolved.cover_photo_id == str(relation.photo_id)
    assert resolved.photo_count == 3


def test_resolve_classification_returns_none_when_tag_missing():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None

    assert resolve_classification(str(uuid4()), uuid4(), db) is None


def test_resolve_nav_items_returns_items_without_pruning_when_all_valid():
    user_id = uuid4()
    db = MagicMock()
    ref_album = NavItemRef(entity_type="album", entity_id=str(uuid4()))
    ref_location = NavItemRef(entity_type="location", entity_id="上海")
    valid_config = SimpleNamespace(nav=SimpleNamespace(items=[ref_album, ref_location]))

    with patch.object(
        resolve_nav_items.__globals__["config_manager"],
        "get_user_config",
        return_value=valid_config,
    ):
        with patch("app.api.nav.resolve_album", return_value="ALBUM"):
            with patch("app.api.nav.resolve_location", return_value="LOCATION"):
                resolved = resolve_nav_items(user_id, db)

    assert resolved == ["ALBUM", "LOCATION"]


def test_resolve_nav_items_prunes_missing_refs():
    user_id = uuid4()
    db = MagicMock()
    good_ref = NavItemRef(entity_type="album", entity_id=str(uuid4()))
    bad_ref = NavItemRef(entity_type="album", entity_id=str(uuid4()))
    config = SimpleNamespace(nav=SimpleNamespace(items=[good_ref, bad_ref]))

    with patch.object(
        resolve_nav_items.__globals__["config_manager"],
        "get_user_config",
        return_value=config,
    ):
        with patch("app.api.nav.resolve_album", side_effect=[SimpleNamespace(name="A"), None]):
            with patch.object(
                resolve_nav_items.__globals__["config_manager"],
                "update_user_config",
            ) as update_cfg:
                resolved = resolve_nav_items(user_id, db)

    assert len(resolved) == 1
    assert resolved[0].name == "A"
    update_cfg.assert_called_once()
    args = update_cfg.call_args.args
    assert args[0] == user_id
    persisted = args[1]["nav"]["items"]
    assert persisted == [good_ref.model_dump()]
    assert args[2] is db


def test_resolve_nav_items_rolls_back_when_resolver_raises():
    """resolve_single_entity 自带 try/except；让 resolve_nav_items 直接捕获到的异常场景，
    由 patch 顶替 resolve_single_entity 让异常外抛，从而触发 resolve_nav_items 的 except 分支。"""
    user_id = uuid4()
    db = MagicMock()
    good_ref = NavItemRef(entity_type="album", entity_id=str(uuid4()))
    bad_ref = NavItemRef(entity_type="album", entity_id=str(uuid4()))
    config = SimpleNamespace(nav=SimpleNamespace(items=[good_ref, bad_ref]))

    with patch.object(
        resolve_nav_items.__globals__["config_manager"],
        "get_user_config",
        return_value=config,
    ):
        with patch(
            "app.api.nav.resolve_single_entity",
            side_effect=[SimpleNamespace(name="A"), RuntimeError("boom")],
        ):
            with patch.object(
                resolve_nav_items.__globals__["config_manager"],
                "update_user_config",
            ) as update_cfg:
                resolved = resolve_nav_items(user_id, db)

    assert len(resolved) == 1
    # resolve_nav_items 在 except 分支里调用 rollback
    db.rollback.assert_called_once()
    # bad_ref 触发的 prune + valid_refs 不等于 refs → 写入
    update_cfg.assert_called_once()


def test_resolve_nav_items_skips_prune_when_nothing_changed():
    user_id = uuid4()
    db = MagicMock()
    ref = NavItemRef(entity_type="album", entity_id=str(uuid4()))
    config = SimpleNamespace(nav=SimpleNamespace(items=[ref]))

    with patch.object(
        resolve_nav_items.__globals__["config_manager"],
        "get_user_config",
        return_value=config,
    ):
        with patch("app.api.nav.resolve_album", return_value=SimpleNamespace(name="A")):
            with patch.object(
                resolve_nav_items.__globals__["config_manager"],
                "update_user_config",
            ) as update_cfg:
                resolve_nav_items(user_id, db)

    update_cfg.assert_not_called()


def test_update_nav_items_rejects_invalid_uuid_before_writing_config():
    """UUID-backed references fail with HTTP 400 before config persistence."""
    body = NavItemsUpdate(
        items=[NavItemRef(entity_type="album", entity_id="not-a-uuid")]
    )
    current_user = SimpleNamespace(id=uuid4())

    with patch("app.api.nav.config_manager.update_user_config") as update_config:
        with pytest.raises(HTTPException) as exc_info:
            update_nav_items(body, current_user=current_user, db=MagicMock())

    assert exc_info.value.status_code == 400
    assert "Invalid UUID for album" in exc_info.value.detail
    update_config.assert_not_called()
