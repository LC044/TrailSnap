"""Unit tests for the AI ticket-recognition router."""

import base64

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import tickets as ai_tickets

pytestmark = [pytest.mark.smoke]

@pytest.fixture
def tickets_client(monkeypatch):
    monkeypatch.setattr(
        ai_tickets.ticket_service,
        "detect",
        lambda contents: {"count": 1, "tickets": [{"train_code": contents.decode("ascii")}]},
    )
    app = FastAPI()
    app.include_router(ai_tickets.router)
    return TestClient(app)

def test_tickets_rejects_empty_batch(tickets_client):
    response = tickets_client.post("/predict", json={"images": []})
    assert response.status_code == 400
    assert response.json()["detail"] == "No images provided"

def test_tickets_accepts_data_url_and_returns_each_result(tickets_client):
    first = base64.b64encode(b"G1").decode()
    second = base64.b64encode(b"D2").decode()
    response = tickets_client.post("/predict", json={"images": [f"data:image/png;base64,{first}", second]})
    assert response.status_code == 200
    assert response.json()["results"] == [
        {"ticket_count": 1, "tickets": [{"train_code": "G1"}]},
        {"ticket_count": 1, "tickets": [{"train_code": "D2"}]},
    ]

def test_tickets_maps_service_value_error_to_400(tickets_client, monkeypatch):
    def _invalid(contents):
        raise ValueError("ticket unreadable")
    monkeypatch.setattr(ai_tickets.ticket_service, "detect", _invalid)
    image = base64.b64encode(b"bad").decode()
    response = tickets_client.post("/predict", json={"images": [image]})
    assert response.status_code == 400
    assert response.json()["detail"] == "ticket unreadable"
