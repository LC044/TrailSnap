"""Focused nightly coverage for 2026-11-02 scanner gaps.

The tests deliberately exercise router guard/delegation branches and the
storage migration conflict branch without touching real user data.
"""

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.api import flight_ticket as flight_api
from app.api import location_stats as location_stats_api
from app.api import media as media_api
from app.service import user_storage


pytestmark = pytest.mark.smoke


def test_media_existing_backup_photo_queries_owner_and_key():
    db = MagicMock()
    owner_id = uuid4()
    backup_key = "backup-key-1"
    photo = SimpleNamespace(id=uuid4())
    db.query.return_value.filter.return_value.first.return_value = photo

    assert media_api._existing_backup_photo(db, owner_id, backup_key) is photo
    db.query.assert_called_once_with(media_api.Photo)
    db.query.return_value.filter.assert_called_once()
    assert str(db.query.return_value.filter.call_args.args[0]) == f"photos.owner_id = :owner_id_1"
    assert str(db.query.return_value.filter.call_args.args[1]) == "photos.backup_key = :backup_key_1"


def test_location_stats_top_person_places_rejects_inverted_date_range():
    db = MagicMock()
    user = SimpleNamespace(id=uuid4())

    response = location_stats_api.get_top_person_places(
        level="city",
        start_date=date(2025, 12, 31),
        end_date=date(2025, 1, 1),
        parent_region=None,
        limit=5,
        db=db,
        current_user=user,
    )

    assert response.code == 400
    assert response.msg == "开始日期不能晚于结束日期"
    db.query.assert_not_called()


class _FakeResponse:
    def __init__(self, json_data):
        self.status = 200
        self._json = json_data

    async def json(self):
        return self._json

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None


class _FakeSession:
    def __init__(self, json_data):
        self._json = json_data

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    def post(self, *_args, **_kwargs):
        return _FakeResponse(self._json)


@pytest.mark.asyncio
async def test_flight_recognition_returns_non_flight_fallback_ticket(monkeypatch):
    """AI sometimes labels a flight ticket as train; the router preserves it."""
    user = SimpleNamespace(id=uuid4())
    db = MagicMock()
    upload = SimpleNamespace(filename="flight.jpg")
    upload.read = AsyncMock(return_value=b"image")
    ticket = {"type": "train", "departure_station": "北京南", "arrival_station": "上海虹桥"}
    config_manager = MagicMock()
    config_manager.get_user_config.return_value = SimpleNamespace(
        ai=SimpleNamespace(ai_api_url="http://ai.test")
    )
    monkeypatch.setattr(flight_api, "config_manager", config_manager)
    monkeypatch.setattr(
        "aiohttp.ClientSession",
        lambda *_args, **_kwargs: _FakeSession({"results": [{"tickets": [ticket]}]}),
    )

    response = await flight_api.recognize_ticket(file=upload, db=db, user=user)

    assert response.code == 200
    assert response.data is ticket


def test_user_storage_move_preserves_a_conflicting_file(tmp_path):
    source = tmp_path / "source.jpg"
    target = tmp_path / "target.jpg"
    source.write_bytes(b"new-data")
    target.write_bytes(b"old")

    result = user_storage._move_file(str(source), str(target), preserve_conflict=True)

    assert result == str(tmp_path / "target-migrated-1.jpg")
    assert not source.exists()
    assert target.read_bytes() == b"old"
    assert (tmp_path / "target-migrated-1.jpg").read_bytes() == b"new-data"
