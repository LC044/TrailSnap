"""Unit tests for the AI OCR router without loading OCR models."""

import base64

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import ocr as ai_ocr

pytestmark = [pytest.mark.smoke]

@pytest.fixture
def ocr_client(monkeypatch):
    monkeypatch.setattr(ai_ocr.ocr_service, "detect_text", lambda contents: [{"text": contents.decode("ascii")}])
    app = FastAPI()
    app.include_router(ai_ocr.router)
    return TestClient(app)

def test_ocr_rejects_empty_batch(ocr_client):
    response = ocr_client.post("/predict", json={"images": []})
    assert response.status_code == 400
    assert response.json()["detail"] == "No images provided"

def test_ocr_accepts_data_url_and_plain_base64(ocr_client):
    first = base64.b64encode(b"first").decode()
    second = base64.b64encode(b"second").decode()
    response = ocr_client.post("/predict", json={"images": [f"data:image/png;base64,{first}", second]})
    assert response.status_code == 200
    assert response.json()["results"] == [
        {"ocrResults": [{"text": "first"}], "dataInfo": []},
        {"ocrResults": [{"text": "second"}], "dataInfo": []},
    ]

def test_ocr_keeps_other_results_when_one_image_is_invalid(ocr_client):
    valid = base64.b64encode(b"valid").decode()
    response = ocr_client.post("/predict", json={"images": ["a", valid]})
    assert response.status_code == 200
    results = response.json()["results"]
    assert results[0]["ocrResults"] == []
    assert results[0]["error"]
    assert results[1]["ocrResults"] == [{"text": "valid"}]

