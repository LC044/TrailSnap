"""Nightly watch 2026-11-04: media backup hash-only lookup contract."""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.api import media as media_api

pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


def test_backup_check_without_keys_returns_only_existing_hashes():
    owner_id = uuid4()
    digest = "a" * 32
    db = MagicMock()

    with patch.object(media_api, "_existing_content_hashes", return_value=[digest]) as existing:
        result = media_api.check_mobile_backup_assets(
            {"keys": [], "hashes": [digest.upper()]},
            db=db,
            current_user=SimpleNamespace(id=owner_id),
        )

    assert result.data == {
        "existing": [],
        "complete": [],
        "live_photos": [],
        "hashes": [digest],
    }
    existing.assert_called_once_with(db, owner_id, [digest])
    db.query.assert_not_called()
