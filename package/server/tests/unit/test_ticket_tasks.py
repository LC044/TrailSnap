"""Unit tests for ticket task schedule calculations and skip behavior."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.service.tasks import tickets


pytestmark = [pytest.mark.smoke, pytest.mark.module_ticket]


def _ticket(departure="Alpha", arrival="Charlie"):
    return SimpleNamespace(
        train_code="G100",
        departure_station=departure,
        arrival_station=arrival,
    )


def _schedule():
    return {'distance_km': 250, 'duration_minutes': 130, 'stops': [
        {'c': code, 'n': name, 'a': '08:00', 'd': '08:05'}
        for code, name in [('AAA', 'Alpha'), ('BBB', 'Bravo'), ('CCC', 'Charlie')]
    ]}


@pytest.mark.asyncio
async def test_calculate_ticket_mileage_and_time_uses_schedule_segments():
    with patch.object(tickets, "get_schedule_info", new=AsyncMock(return_value=_schedule())):
        result = await tickets.calculate_ticket_mileage_and_time(_ticket())

    assert result["total_mileage"] == 250
    assert result["total_time"] == 130
    assert [stop["station_name"] for stop in result["stop_stations"]] == ["Alpha", "Bravo", "Charlie"]


@pytest.mark.asyncio
async def test_calculate_ticket_mileage_and_time_handles_missing_station():
    with patch.object(tickets, "get_schedule_info", new=AsyncMock(return_value={"distance_km": None, "duration_minutes": None, "stops": []})):
        result = await tickets.calculate_ticket_mileage_and_time(_ticket(arrival="Missing"))

    assert result == {"total_mileage": None, "total_time": None, "stop_stations": []}


@pytest.mark.asyncio
async def test_recognize_ticket_strategy_skips_missing_photo():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    task = SimpleNamespace(payload={"photo_id": "missing-photo"})

    result = await tickets.RecognizeTicketStrategy().process(MagicMock(), task, db)

    assert result == {"status": "skipped", "reason": "photo not found"}
