"""Annual-report location metrics and search-planner visibility guards."""
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.api.annual_report import get_report_location
from app.service.agent import search_planner

pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


def _recording_chain(record):
    chain = MagicMock()
    for method in ("join", "group_by", "order_by", "limit"):
        getattr(chain, method).return_value = chain
    chain.filter.side_effect = lambda *args, **kwargs: (record.append(args), chain)[1]
    chain.scalar.return_value = 0
    chain.all.return_value = []
    chain.first.return_value = None
    return chain


def test_get_report_location_returns_zeroed_metrics_without_data():
    chain = _recording_chain([])
    db = MagicMock()
    db.query.return_value = chain
    user = SimpleNamespace(id=uuid4())

    result = get_report_location(
        start_time=datetime(2026, 1, 1),
        end_time=datetime(2026, 12, 31),
        db=db,
        current_user=user,
    )

    assert result.lightenProvinceNum == 0
    assert result.lightenCityNum == 0
    assert result.topCities == []
    assert result.locationPoints == []
    assert result.farthestCity is None
    assert result.farthestDistance == 0
    assert result.farthestCityPhotos == []


def test_get_report_location_scopes_queries_to_owner_and_window():
    record = []
    chain = _recording_chain(record)
    db = MagicMock()
    db.query.return_value = chain
    user = SimpleNamespace(id=uuid4())

    get_report_location(
        start_time=datetime(2026, 1, 1),
        end_time=datetime(2026, 12, 31),
        db=db,
        current_user=user,
    )

    rendered = " ".join(str(arg) for args in record for arg in args)
    assert "owner_id" in rendered
    assert "photo_time" in rendered


def test_visible_metadata_scopes_to_owner_and_live_photos():
    record = []
    chain = _recording_chain(record)
    db = MagicMock()
    db.query.return_value = chain
    owner_id = uuid4()

    result = search_planner._visible_metadata(db, owner_id)

    assert result is chain
    rendered = " ".join(str(arg) for args in record for arg in args)
    assert "owner_id" in rendered
    assert "is_deleted" in rendered

