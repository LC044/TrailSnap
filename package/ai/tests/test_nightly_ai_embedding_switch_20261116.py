"""2026-11-16 nightly coverage for ``app/routers/embedding.py``.

The 2026-11-16 AI coverage scan reported ``routers/embedding.py`` at 96.9%
with 2 missed lines:

* the "the embedding model was switched while encoding" guard (line 41);
* the translation of a ``ValueError`` into a 422 response (line 48).

Both matter for the server <-> AI contract: the server must not mix
vectors produced by two different models, and a truncated input must be
reported as a client error instead of a server error.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


pytestmark = [pytest.mark.smoke]


@pytest.fixture
def client(monkeypatch):
    from app.routers import embedding as ai_embedding

    app = FastAPI()
    app.include_router(ai_embedding.router)
    return TestClient(app)


def _spec(monkeypatch, names):
    """Answer ``get_selected_spec`` with the given runtime names in order."""
    from app.routers import embedding as ai_embedding

    pending = list(names)

    def _get_selected_spec(kind):
        if pending:
            return {"runtimeName": pending.pop(0)}
        return {"runtimeName": names[-1]}

    monkeypatch.setattr(ai_embedding.ai_model_manager, "get_selected_spec", _get_selected_spec)


def test_a_model_switch_during_encoding_is_refused(client, monkeypatch):
    from app.routers import embedding as ai_embedding

    async def _embed(texts, **_kwargs):
        return [[0.1, 0.2] for _ in texts]

    monkeypatch.setattr(ai_embedding.embedding_service, "embed_texts", _embed)
    _spec(monkeypatch, ["model-a", "model-b"])

    res = client.post("/text", json={"texts": ["x"]})

    assert res.status_code == 409
    assert "模型已切换" in res.json()["detail"]


def test_a_truncated_input_is_reported_as_a_client_error(client, monkeypatch):
    from app.routers import embedding as ai_embedding

    async def _embed(texts, **_kwargs):
        raise ValueError("输入超出模型长度限制")

    monkeypatch.setattr(ai_embedding.embedding_service, "embed_texts", _embed)
    _spec(monkeypatch, ["model-a"])

    res = client.post("/text", json={"texts": ["x"]})

    assert res.status_code == 422
    assert "长度限制" in res.json()["detail"]


def test_the_selected_model_is_returned_as_a_header(client, monkeypatch):
    from app.routers import embedding as ai_embedding

    async def _embed(texts, **_kwargs):
        return [[0.1, 0.2] for _ in texts]

    monkeypatch.setattr(ai_embedding.embedding_service, "embed_texts", _embed)
    _spec(monkeypatch, ["model-a"])

    res = client.post("/text", json={"texts": ["x"]})

    assert res.status_code == 200
    assert res.headers["X-Embedding-Model"] == "model-a"
