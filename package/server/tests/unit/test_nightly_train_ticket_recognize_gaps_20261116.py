"""2026-11-16 nightly coverage for the ticket recognition endpoint.

The 2026-11-16 backend coverage scan reported ``api/train_ticket.py`` at
95.5% with 8 missed lines, all inside ``POST /recognize``:

* the "the AI service returned no result" guard (line 75);
* the "none of the parsed tickets is a train ticket" guard (line 97);
* the date fallback that cannot build a valid date (lines 154-155);
* the price that cannot be parsed (lines 162-163);
* the default discount type (line 172);
* the generic failure of the endpoint (line 182).

The AI HTTP call is stubbed, no network access is required.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api import train_ticket as train_ticket_api


pytestmark = [pytest.mark.smoke, pytest.mark.module_ticket]


class _FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status = status

    async def json(self):
        return self._payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False


class _FakeSession:
    def __init__(self, responder):
        self._responder = responder

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False

    def post(self, url, json=None):
        return self._responder(url)


def _user():
    return SimpleNamespace(id=uuid4())


def _file():
    file = MagicMock()
    file.read = MagicMock()

    async def _read():
        return b"binary"

    file.read = _read
    return file


def _run(payload, status=200, tickets=None):
    """Call the endpoint with a stubbed AI service."""
    body = {"results": [{"tickets": tickets}]} if tickets is not None else payload
    config = SimpleNamespace(ai=SimpleNamespace(ai_api_url="http://ai.test"))

    def _session():
        return _FakeSession(lambda url: _FakeResponse(body, status=status))

    with patch.object(train_ticket_api.aiohttp, "ClientSession", _session), patch.object(
        train_ticket_api.config_manager, "get_user_config", lambda _uid, _db: config
    ):
        return asyncio.run(
            train_ticket_api.recognize_ticket(file=_file(), db=MagicMock(), current_user=_user())
        )


def test_an_empty_ai_result_is_rejected():
    with pytest.raises(HTTPException) as excinfo:
        _run({"results": []})
    assert excinfo.value.status_code == 400


def test_a_result_without_train_tickets_is_rejected():
    with pytest.raises(HTTPException) as excinfo:
        _run({}, tickets=[{"type": "flight", "flight_code": "CA123"}])
    assert excinfo.value.status_code == 400


def test_an_unparsable_price_falls_back_to_zero():
    response = _run({}, tickets=[{"type": "train", "train_code": "G1", "price": "面议"}])

    assert response.data["price"] == 0


def test_a_missing_discount_type_defaults_to_the_full_price():
    response = _run({}, tickets=[{"type": "train", "train_code": "G1"}])

    assert response.data["discount_type"] == "全价票"


def test_an_explicit_discount_type_is_kept():
    response = _run({}, tickets=[{"type": "train", "train_code": "G1", "discount_type": "学生票"}])

    assert response.data["discount_type"] == "学生票"


def test_an_impossible_inferred_date_is_ignored():
    response = _run(
        {},
        tickets=[{"type": "train", "train_code": "G1", "datetime": "13月45日 10:00"}],
    )

    assert "datetime" not in response.data


def test_a_year_less_datetime_uses_the_current_year():
    response = _run(
        {},
        tickets=[{"type": "train", "train_code": "G1", "datetime": "3月4日 10:30"}],
    )

    assert response.data["year_source"] == "inferred_current_year"


def test_an_explicit_datetime_is_kept():
    response = _run(
        {},
        tickets=[{"type": "train", "train_code": "G1", "datetime": "2025年03月04日 10:30"}],
    )

    assert response.data["datetime"] == "2025-03-04T10:30"
    assert response.data["year_source"] == "explicit"


def test_an_ai_error_status_is_reported():
    with pytest.raises(HTTPException) as excinfo:
        _run({"results": []}, status=500)
    assert excinfo.value.status_code == 500



def test_a_ticket_with_only_a_name_is_penalised():
    """A ticket that only carries a name must lose against a complete one."""
    response = _run(
        {},
        tickets=[
            {"type": "train", "name": "张三"},
            {"type": "train", "train_code": "G1", "departure_station": "北京"},
        ],
    )

    assert response.data["train_code"] == "G1"


def test_an_unexpected_failure_is_reported_as_a_server_error():
    def _boom(_url):
        raise RuntimeError("connection reset")

    config = SimpleNamespace(ai=SimpleNamespace(ai_api_url="http://ai.test"))

    with patch.object(
        train_ticket_api.aiohttp,
        "ClientSession",
        lambda: _FakeSession(_boom),
    ), patch.object(
        train_ticket_api.config_manager, "get_user_config", lambda _uid, _db: config
    ):
        with pytest.raises(HTTPException) as excinfo:
            asyncio.run(
                train_ticket_api.recognize_ticket(
                    file=_file(), db=MagicMock(), current_user=_user()
                )
            )

    assert excinfo.value.status_code == 500
    assert "识别处理失败" in excinfo.value.detail
