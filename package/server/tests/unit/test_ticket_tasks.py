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
    return {
        "code": 200,
        "data": {
            "list": [
                {
                    "station_telecode": "AAA",
                    "station_name": "Alpha",
                    "arrival_time": "08:00:00",
                    "departure_time": "08:05:00",
                    "accumulated_mileage": 0,
                },
                {
                    "station_telecode": "BBB",
                    "station_name": "Bravo",
                    "arrival_time": "09:00:00",
                    "departure_time": "09:05:00",
                    "accumulated_mileage": 100,
                },
                {
                    "station_telecode": "CCC",
                    "station_name": "Charlie",
                    "arrival_time": "10:00:00",
                    "departure_time": "10:05:00",
                    "accumulated_mileage": 250,
                },
            ]
        },
    }


@pytest.mark.asyncio
async def test_calculate_ticket_mileage_and_time_uses_schedule_segments():
    with patch.object(tickets, "get_schedule_info", new=AsyncMock(return_value=_schedule())):
        result = await tickets.calculate_ticket_mileage_and_time(_ticket())

    assert result["total_mileage"] == 250
    assert result["total_time"] == 130
    assert [stop["station_name"] for stop in result["stop_stations"]] == ["Alpha", "Bravo"]


@pytest.mark.asyncio
async def test_calculate_ticket_mileage_and_time_handles_missing_station():
    with patch.object(tickets, "get_schedule_info", new=AsyncMock(return_value=_schedule())):
        result = await tickets.calculate_ticket_mileage_and_time(_ticket(arrival="Missing"))

    assert result == {"total_mileage": 0, "total_time": 0, "stop_stations": []}


@pytest.mark.asyncio
async def test_recognize_ticket_strategy_skips_missing_photo():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    task = SimpleNamespace(payload={"photo_id": "missing-photo"})

    result = await tickets.RecognizeTicketStrategy().process(MagicMock(), task, db)

    assert result == {"status": "skipped", "reason": "photo not found"}
