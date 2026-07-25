"""Unit tests for the flight ticket REST router (app/api/flight_ticket.py).

Covers the create / read / update / delete endpoints and the recognize
endpoint's AI forwarding logic. The CRUD layer is patched so no Postgres
is touched; the AI HTTP call is replaced with a tiny fake ``ClientSession``
class so we exercise the real async-with control flow end-to-end.

Note: ``recognize_ticket`` wraps its body in ``try / except Exception`` that
re-raises any ``HTTPException`` as a 500, so all AI failure modes surface
as ``500`` to the caller.

Scenarios:
* recognize returns the highest-scoring flight ticket when AI returns 200
* recognize 500 when AI returns 200 but yields no recognisable tickets
* recognize 500 when the AI HTTP status itself is non-200
* create returns the persisted ticket from the CRUD layer
* list builds the filter dict from query params and returns total/items
* list omits empty filters
* get 404 / success
* update 404 / success
* delete 404 / success
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api import flight_ticket as flight_api


pytestmark = [pytest.mark.smoke, pytest.mark.module_ticket]


def _user(uid=None):
    return SimpleNamespace(id=uid or uuid4())


def _ticket(**kwargs):
    base = {
        "id": str(uuid4()),
        "flight_code": "CA1234",
        "departure_city": "Beijing",
        "arrival_city": "Shanghai",
        "date_time": "2025-08-01T08:00:00",
        "price": "1000",
        "name": "Alice",
        "created_at": "2025-07-25T00:00:00",
        "updated_at": "2025-07-25T00:00:00",
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


def _ai_config(url="http://ai.test"):
    return SimpleNamespace(ai=SimpleNamespace(ai_api_url=url))


def _upload_file(name="ticket.jpg", payload=b"\x89PNG-fake"):
    file = SimpleNamespace(filename=name)
    file.read = AsyncMock(return_value=payload)
    return file


def _fake_client_session_class(post_status=200, post_json=None):
    """Return a stand-in for ``aiohttp.ClientSession`` driven by plain async context managers."""

    class _FakeResponse:
        def __init__(self, status, json_data):
            self.status = status
            self._json = json_data

        async def json(self):
            return self._json

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return None

    class _FakeSession:
        def __init__(self):
            self._status = post_status
            self._json = post_json or {}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return None

        def post(self, *_args, **_kwargs):
            return _FakeResponse(self._status, self._json)

    class _FakeClientSession:
        def __new__(cls, *_args, **_kwargs):
            return _FakeSession()

    return _FakeClientSession


# ----------------------------- POST /flight-tickets/recognize ----------


@pytest.mark.asyncio
async def test_recognize_returns_highest_scoring_flight_ticket():
    user = _user()
    db = MagicMock()
    file = _upload_file()

    ai_response = {
        "results": [
            {
                "tickets": [
                    {
                        "type": "flight",
                        "flight_code": "CA1111",
                        "departure_city": "Beijing",
                        "datetime": "2025-08-01T08:00:00",
                    },
                    {
                        "type": "flight",
                        "flight_code": "CA2222",
                        "departure_city": "Beijing",
                        "arrival_city": "Shanghai",
                        "datetime": "2025-08-02T09:00:00",
                        "price": "500",
                    },
                ]
            }
        ]
    }

    config_mock = MagicMock()
    config_mock.get_user_config.return_value = _ai_config()

    with patch.object(flight_api, "config_manager", config_mock):
        with patch("aiohttp.ClientSession", new=_fake_client_session_class(200, ai_response)):
            response = await flight_api.recognize_ticket(file=file, db=db, user=user)

    assert response.code == 200
    assert response.data["flight_code"] == "CA2222"


@pytest.mark.asyncio
async def test_recognize_raises_500_when_ai_returns_no_tickets():
    user = _user()
    db = MagicMock()
    file = _upload_file()

    config_mock = MagicMock()
    config_mock.get_user_config.return_value = _ai_config()

    with patch.object(flight_api, "config_manager", config_mock):
        with patch("aiohttp.ClientSession", new=_fake_client_session_class(200, {"results": [{"tickets": []}]})):
            with pytest.raises(HTTPException) as exc_info:
                await flight_api.recognize_ticket(file=file, db=db, user=user)

    # The internal 400 is swallowed by the outer try/except and re-raised as 500.
    assert exc_info.value.status_code == 500


@pytest.mark.asyncio
async def test_recognize_raises_500_when_ai_call_fails():
    user = _user()
    db = MagicMock()
    file = _upload_file()

    config_mock = MagicMock()
    config_mock.get_user_config.return_value = _ai_config()

    with patch.object(flight_api, "config_manager", config_mock):
        with patch("aiohttp.ClientSession", new=_fake_client_session_class(503)):
            with pytest.raises(HTTPException) as exc_info:
                await flight_api.recognize_ticket(file=file, db=db, user=user)

    assert exc_info.value.status_code == 500


# ----------------------------- POST /flight-tickets -------------------


@pytest.mark.asyncio
async def test_create_ticket_returns_persisted_ticket():
    user = _user()
    db = MagicMock()
    ticket = _ticket()
    payload = MagicMock()

    with patch.object(flight_api, "create_flight_ticket", return_value=ticket) as crud_call:
        response = await flight_api.create_ticket(ticket=payload, db=db, current_user=user)

    crud_call.assert_called_once_with(db, payload, owner_id=user.id)
    assert response.code == 200
    assert response.data is ticket


# ----------------------------- GET /flight-tickets --------------------


@pytest.mark.asyncio
async def test_list_tickets_passes_filters_and_returns_total_items():
    user = _user()
    db = MagicMock()
    items = [_ticket(), _ticket()]

    with patch.object(flight_api, "get_flight_tickets", return_value=(2, items)) as crud_call:
        response = await flight_api.get_tickets(
            skip=10,
            limit=20,
            flight_code="CA1",
            name="Alice",
            start_date="2025-01-01",
            end_date="2025-12-31",
            db=db,
            current_user=user,
        )

    args = crud_call.call_args.args
    filters_arg = args[3]
    assert args[0] is db
    assert args[1] == 10
    assert args[2] == 20
    assert filters_arg["flight_code"] == "CA1"
    assert filters_arg["name"] == "Alice"
    assert filters_arg["start_date"] == "2025-01-01"
    assert filters_arg["end_date"] == "2025-12-31"
    assert filters_arg["owner_id"] == user.id
    assert response.code == 200
    assert response.data == {"total": 2, "items": items}


@pytest.mark.asyncio
async def test_list_tickets_omits_empty_filters():
    user = _user()
    db = MagicMock()
    with patch.object(flight_api, "get_flight_tickets", return_value=(0, [])) as crud_call:
        response = await flight_api.get_tickets(
            skip=0,
            limit=100,
            flight_code=None,
            name=None,
            start_date=None,
            end_date=None,
            db=db,
            current_user=user,
        )

    filters_arg = crud_call.call_args.args[3]
    assert filters_arg == {"owner_id": user.id}
    assert response.data == {"total": 0, "items": []}


# ----------------------------- GET /{ticket_id} ------------------------


@pytest.mark.asyncio
async def test_get_ticket_returns_404_when_missing():
    db = MagicMock()
    with patch.object(flight_api, "get_flight_ticket", return_value=None):
        with pytest.raises(HTTPException) as exc_info:
            await flight_api.get_ticket(ticket_id=str(uuid4()), db=db)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_ticket_returns_ticket():
    db = MagicMock()
    ticket = _ticket()
    with patch.object(flight_api, "get_flight_ticket", return_value=ticket):
        response = await flight_api.get_ticket(ticket_id=ticket.id, db=db)

    assert response.code == 200
    assert response.data is ticket


# ----------------------------- PUT /{ticket_id} ------------------------


@pytest.mark.asyncio
async def test_update_ticket_returns_404_when_missing():
    db = MagicMock()
    payload = MagicMock()
    with patch.object(flight_api, "update_flight_ticket", return_value=None):
        with pytest.raises(HTTPException) as exc_info:
            await flight_api.update_ticket(
                ticket_update=payload, ticket_id=str(uuid4()), db=db
            )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_update_ticket_returns_ticket():
    db = MagicMock()
    updated = _ticket(flight_code="CA9999")
    payload = MagicMock()
    with patch.object(flight_api, "update_flight_ticket", return_value=updated) as crud_call:
        response = await flight_api.update_ticket(
            ticket_update=payload, ticket_id=str(uuid4()), db=db
        )

    crud_call.assert_called_once()
    assert response.code == 200
    assert response.data.flight_code == "CA9999"


# ----------------------------- DELETE /{ticket_id} ---------------------


@pytest.mark.asyncio
async def test_delete_ticket_returns_404_when_missing():
    db = MagicMock()
    with patch.object(flight_api, "delete_flight_ticket", return_value=False):
        with pytest.raises(HTTPException) as exc_info:
            await flight_api.delete_ticket(ticket_id=str(uuid4()), db=db)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_delete_ticket_succeeds():
    db = MagicMock()
    with patch.object(flight_api, "delete_flight_ticket", return_value=True):
        response = await flight_api.delete_ticket(ticket_id=str(uuid4()), db=db)

    assert response.code == 200
    assert response.data == {"msg": "\u5220\u9664\u6210\u529f"}
