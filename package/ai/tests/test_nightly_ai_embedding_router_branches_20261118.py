"""2026-11-18 nightly coverage for the remaining branches of ``app/routers/embedding.py``.

PR #487 already covers the "model switched while encoding" guard, the
``ValueError`` -> 422 translation and the ``X-Embedding-Model`` response header
(``tests/test_nightly_ai_embedding_switch_20261116.py``).

The branches that were still uncovered are the *request-shape* ones:

* an empty ``texts`` list is a client error (400), not a server error;
* an explicit ``model`` that differs from the selected runtime is refused (409);
* an explicit ``model`` that matches is passed through with
  ``reject_truncation=True`` so a truncated answer can never be cached;
* ``cache=True`` without an explicit model goes through the cached path;
* the image route refuses a mismatching model and a model that is switched
  while the images are encoded.
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


def _selected(monkeypatch, names):
    """Answer ``get_selected_spec`` with the given runtime names in order."""
    from app.routers import embedding as ai_embedding

    pending = list(names)

    def _get_selected_spec(_kind):
        if pending:
            return {"runtimeName": pending.pop(0)}
        return {"runtimeName": names[-1]}

    monkeypatch.setattr(ai_embedding.ai_model_manager, "get_selected_spec", _get_selected_spec)


def _record_text_calls(monkeypatch):
    """Patch the embedding service and record the kwargs of every call."""
    from app.routers import embedding as ai_embedding

    calls = []

    async def _embed_texts(texts, **kwargs):
        calls.append(kwargs)
        return [[0.1, 0.2] for _ in texts]

    monkeypatch.setattr(ai_embedding.embedding_service, "embed_texts", _embed_texts)
    return calls


def _record_image_calls(monkeypatch):
    from app.routers import embedding as ai_embedding

    calls = []

    async def _embed_images(images):
        calls.append(list(images))
        return [[0.3, 0.4] for _ in images]

    monkeypatch.setattr(ai_embedding.embedding_service, "embed_images", _embed_images)
    return calls


def test_an_empty_text_list_is_a_client_error(client, monkeypatch):
    calls = _record_text_calls(monkeypatch)
    _selected(monkeypatch, ["clip-a"])

    res = client.post("/text", json={"texts": []})

    assert res.status_code == 400
    assert "No texts provided" in res.json()["detail"]
    assert calls == []


def test_a_mismatching_explicit_model_is_refused(client, monkeypatch):
    calls = _record_text_calls(monkeypatch)
    _selected(monkeypatch, ["clip-a"])

    res = client.post("/text", json={"texts": ["x"], "model": "clip-b"})

    assert res.status_code == 409
    assert "目标不一致" in res.json()["detail"]
    assert calls == []


def test_a_matching_explicit_model_disables_truncation_and_honours_the_cache_flag(
    client, monkeypatch
):
    calls = _record_text_calls(monkeypatch)
    _selected(monkeypatch, ["clip-a"])

    res = client.post("/text", json={"texts": ["x"], "model": "clip-a", "cache": True})

    assert res.status_code == 200
    assert calls and calls[0].get("use_cache") is True
    assert calls[0].get("reject_truncation") is True


def test_a_matching_explicit_model_without_cache_flag_does_not_use_the_cache(
    client, monkeypatch
):
    calls = _record_text_calls(monkeypatch)
    _selected(monkeypatch, ["clip-a"])

    res = client.post("/text", json={"texts": ["x"], "model": "clip-a"})

    assert res.status_code == 200
    assert calls and calls[0].get("use_cache") is False
    assert calls[0].get("reject_truncation") is True


def test_the_cache_flag_without_a_model_uses_the_cached_path(client, monkeypatch):
    calls = _record_text_calls(monkeypatch)
    _selected(monkeypatch, ["clip-a"])

    res = client.post("/text", json={"texts": ["x"], "cache": True})

    assert res.status_code == 200
    assert calls and calls[0].get("use_cache") is True
    assert "reject_truncation" not in calls[0]


def test_the_image_route_refuses_a_mismatching_model(client, monkeypatch):
    calls = _record_image_calls(monkeypatch)
    _selected(monkeypatch, ["clip-a"])

    res = client.post("/image", json={"images": ["a"], "model": "clip-b"})

    assert res.status_code == 409
    assert "clip-b" in res.json()["detail"]
    assert calls == []


def test_the_image_route_refuses_a_model_switched_while_encoding(client, monkeypatch):
    calls = _record_image_calls(monkeypatch)
    _selected(monkeypatch, ["clip-a", "clip-b"])

    res = client.post("/image", json={"images": ["a"]})

    assert res.status_code == 409
    assert "模型已切换" in res.json()["detail"]
    assert calls == [["a"]]
