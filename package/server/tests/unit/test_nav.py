"""Unit tests for custom navigation item resolution and validation."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.nav import resolve_single_entity, update_nav_items
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
