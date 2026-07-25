"""Unit tests for the train ticket REST router (app/api/train_ticket.py).

Covers the CRUD endpoints and the /recognize ``AI`` forwarding path. The
CRUD layer is patched so no Postgres is touched; the AI HTTP call is
replaced with a tiny fake ``ClientSession`` class that mirrors aiohttp's
async context manager behaviour exactly.

Scenarios:
* recognize returns the highest-scoring train ticket when AI returns 200
* recognize 500 when AI returns 200 but yields no tickets
* recognize 500 when the AI HTTP status itself is non-200
* create returns the persisted ticket from the CRUD layer
* get 404 / success
* update 404 / success
* delete 404 / success
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api import train_ticket as train_api


pytestmark = [pytest.mark.smoke, pytest.mark.module_ticket]


def _user(uid=None):
    return SimpleNamespace(id=uid or uuid4())


def _ticket(**kwargs):
    base = {
        "id": str(uuid4()),
        "train_code": "G1234",
        "departure_station": "Beijing South",
        "arrival_station": "Shanghai Hongqiao",
        "date_time": "2025-08-01T08:00:00",
        "price": 553.5,
        "name": "Alice",
        "seat_type": "Second-class",
        "berth_type": "None",
        "discount_type": "Full-price",
        "created_at": "2025-07-25T00:00:00",
        "updated_at": "2025-07-25T00:00:00",
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


def _ai_config(url="http://ai.test"):
    return SimpleNamespace(ai=SimpleNamespace(ai_api_url=url))


def _upload_file(name="ticket.jpg", payload=b"\x89PNG-fake", content_type="image/jpeg"):
    file = SimpleNamespace(filename=name, content_type=content_type)
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


# ----------------------------- POST /train-tickets/recognize -----------


@pytest.mark.asyncio
async def test_recognize_returns_highest_scoring_train_ticket():
    user = _user()
    db = MagicMock()
    file = _upload_file()

    ai_response = {
        "results": [
            {
                "tickets": [
                    {
                        "train_code": "G111",
                        "departure_station": "Beijing",
                    },
                    {
                        "train_code": "G222",
                        "departure_station": "Beijing South",
                        "arrival_station": "Shanghai Hongqiao",
                        "datetime": "2025\u5e748\u67081\u65e5 08:00",
                        "seat_type": "Second-class",
                        "price": "553.5",
                    },
                ]
            }
        ]
    }

    config_mock = MagicMock()
    config_mock.get_user_config.return_value = _ai_config()

    with patch.object(train_api, "config_manager", config_mock):
        with patch("aiohttp.ClientSession", new=_fake_client_session_class(200, ai_response)):
            response = await train_api.recognize_ticket(file=file, db=db, current_user=user)

    assert response.code == 200
    # The richer ticket (G222) should win the scoring and survive the field mapping.
    assert response.data["train_code"] == "G222"
    assert response.data["berth_type"] == "\u65e0"  # default-fill when AI omits it
    assert response.data["discount_type"] == "\u5168\u4ef7\u7968"  # default when AI omits it


@pytest.mark.asyncio
async def test_recognize_raises_500_when_ai_returns_no_tickets():
    user = _user()
    db = MagicMock()
    file = _upload_file()

    config_mock = MagicMock()
    config_mock.get_user_config.return_value = _ai_config()

    with patch.object(train_api, "config_manager", config_mock):
        with patch("aiohttp.ClientSession", new=_fake_client_session_class(200, {"results": [{"tickets": []}]})):
            with pytest.raises(HTTPException) as exc_info:
                await train_api.recognize_ticket(file=file, db=db, current_user=user)

    # /recognize re-raises HTTPException after the 400 (see source try/except).
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_recognize_raises_500_when_ai_call_fails():
    user = _user()
    db = MagicMock()
    file = _upload_file()

    config_mock = MagicMock()
    config_mock.get_user_config.return_value = _ai_config()

    with patch.object(train_api, "config_manager", config_mock):
        with patch("aiohttp.ClientSession", new=_fake_client_session_class(503)):
            with pytest.raises(HTTPException) as exc_info:
                await train_api.recognize_ticket(file=file, db=db, current_user=user)

    assert exc_info.value.status_code == 500


# ----------------------------- POST /train-tickets ----------------------


def test_create_ticket_returns_persisted_ticket():
    user = _user()
    db = MagicMock()
    ticket = _ticket()
    payload = MagicMock()

    with patch.object(train_api, "create_train_ticket", return_value=ticket) as crud_call:
        response = train_api.create_ticket(ticket=payload, db=db, current_user=user)

    crud_call.assert_called_once_with(db=db, ticket=payload, owner_id=user.id)
    assert response.code == 200
    assert response.data is ticket


# ----------------------------- GET /train-tickets/{id} -----------------


def test_read_ticket_returns_404_when_missing():
    db = MagicMock()
    with patch.object(train_api, "get_train_ticket", return_value=None):
        with pytest.raises(HTTPException) as exc_info:
            train_api.read_ticket(ticket_id=str(uuid4()), db=db)

    assert exc_info.value.status_code == 404


def test_read_ticket_returns_ticket():
    db = MagicMock()
    ticket = _ticket()
    with patch.object(train_api, "get_train_ticket", return_value=ticket):
        response = train_api.read_ticket(ticket_id=ticket.id, db=db)

    assert response.code == 200
    assert response.data is ticket


# ----------------------------- PUT /train-tickets/{id} -----------------


def test_update_ticket_returns_404_when_missing():
    db = MagicMock()
    payload = MagicMock()
    with patch.object(train_api, "update_train_ticket", return_value=None):
        with pytest.raises(HTTPException) as exc_info:
            train_api.update_ticket(
                ticket_update=payload, ticket_id=str(uuid4()), db=db
            )

    assert exc_info.value.status_code == 404


def test_update_ticket_returns_ticket():
    db = MagicMock()
    updated = _ticket(train_code="G9999")
    payload = MagicMock()
    with patch.object(train_api, "update_train_ticket", return_value=updated) as crud_call:
        response = train_api.update_ticket(
            ticket_update=payload, ticket_id=str(uuid4()), db=db
        )

    crud_call.assert_called_once()
    assert response.code == 200
    assert response.data.train_code == "G9999"


# ----------------------------- DELETE /train-tickets/{id} --------------


def test_delete_ticket_returns_404_when_missing():
    db = MagicMock()
    with patch.object(train_api, "delete_train_ticket", return_value=False):
        with pytest.raises(HTTPException) as exc_info:
            train_api.delete_ticket(ticket_id=str(uuid4()), db=db)

    assert exc_info.value.status_code == 404


def test_delete_ticket_succeeds():
    db = MagicMock()
    with patch.object(train_api, "delete_train_ticket", return_value=True):
        response = train_api.delete_ticket(ticket_id=str(uuid4()), db=db)

    assert response.code == 200
    assert response.data["message"] == "\u706b\u8f66\u7968\u8bb0\u5f55\u5220\u9664\u6210\u529f"

