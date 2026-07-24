"""Unit tests for the AI service embedding router.

The router exposes ``POST /text`` and ``POST /image`` for vector
generation. We use a stripped FastAPI app + TestClient so no models are
loaded; ``embedding_service`` is patched to return stub vectors.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


pytestmark = [pytest.mark.smoke, pytest.mark.module_ai_embedding]


@pytest.fixture
def embedding_client(monkeypatch):
    # Patch the imported module inside the router so both endpoints
    # route through the same stub.
    from app.routers import embedding as ai_embedding

    async def _embed_texts(texts):
        return [[float(len(t)), 0.5] for t in texts]

    async def _embed_images(images):
        return [[0.1, 0.2, 0.3] for _ in images]

    monkeypatch.setattr(ai_embedding.embedding_service, "embed_texts", _embed_texts)
    monkeypatch.setattr(ai_embedding.embedding_service, "embed_images", _embed_images)

    app = FastAPI()
    app.include_router(ai_embedding.router)
    return TestClient(app)


def test_embed_text_rejects_empty_texts(embedding_client):
    res = embedding_client.post("/text", json={"texts": []})
    assert res.status_code == 400
    assert "No texts" in res.json()["detail"]


def test_embed_text_returns_vector_per_text(embedding_client):
    res = embedding_client.post("/text", json={"texts": ["a", "bb"]})
    assert res.status_code == 200
    body = res.json()
    assert len(body) == 2
    assert body[0][0] == pytest.approx(1.0)
    assert body[1][0] == pytest.approx(2.0)


def test_embed_text_wraps_service_errors_in_500(embedding_client, monkeypatch):
    from app.routers import embedding as ai_embedding

    async def _boom(texts):
        raise RuntimeError("clip offline")

    monkeypatch.setattr(ai_embedding.embedding_service, "embed_texts", _boom)
    res = embedding_client.post("/text", json={"texts": ["x"]})
    assert res.status_code == 500
    assert "clip offline" in res.json()["detail"]


def test_embed_image_rejects_empty_images(embedding_client):
    res = embedding_client.post("/image", json={"images": []})
    assert res.status_code == 400


def test_embed_image_returns_vector_per_image(embedding_client):
    res = embedding_client.post("/image", json={"images": ["ZmFrZQ==", "Zm9v"]})
    assert res.status_code == 200
    body = res.json()
    assert len(body) == 2
    assert body[0] == pytest.approx([0.1, 0.2, 0.3])


def test_embed_image_wraps_service_errors_in_500(embedding_client, monkeypatch):
    from app.routers import embedding as ai_embedding

    async def _boom(images):
        raise RuntimeError("clip offline")

    monkeypatch.setattr(ai_embedding.embedding_service, "embed_images", _boom)
    res = embedding_client.post("/image", json={"images": ["x"]})
    assert res.status_code == 500
    assert "clip offline" in res.json()["detail"]
