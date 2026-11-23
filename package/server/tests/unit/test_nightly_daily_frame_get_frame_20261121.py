"""Daily-frame single-day endpoint guards."""
from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.api import daily_frame as daily_frame_api

pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


def test_get_frame_returns_service_payload_in_success_envelope(monkeypatch):
    captured = {}

    def fake_frame(db, owner_id, day):
        captured["db"] = db
        captured["owner_id"] = owner_id
        captured["day"] = day
        return {"day": day.isoformat(), "version": 3}

    monkeypatch.setattr(daily_frame_api.service, "frame", fake_frame)
    user = SimpleNamespace(id=uuid4())
    db = object()

    response = daily_frame_api.get_frame(date(2026, 5, 1), user=user, db=db)

    assert response.code == 0
    assert response.data == {"day": "2026-05-01", "version": 3}
    assert captured["owner_id"] == user.id
    assert captured["day"] == date(2026, 5, 1)
    assert captured["db"] is db


def test_get_frame_propagates_removed_marker(monkeypatch):
    monkeypatch.setattr(
        daily_frame_api.service,
        "frame",
        lambda db, owner_id, day: {"day": day.isoformat(), "version": 0, "removed": True},
    )
    response = daily_frame_api.get_frame(
        date(2026, 5, 2), user=SimpleNamespace(id=uuid4()), db=object()
    )
    assert response.code == 0
    assert response.data["removed"] is True
    assert response.data["version"] == 0


def test_get_frame_uses_the_requested_day_only(monkeypatch):
    seen = []
    monkeypatch.setattr(
        daily_frame_api.service,
        "frame",
        lambda db, owner_id, day: seen.append(day) or {"day": day.isoformat()},
    )
    target = date(2026, 12, 31)
    daily_frame_api.get_frame(target, user=SimpleNamespace(id=uuid4()), db=object())
    assert seen == [target]
