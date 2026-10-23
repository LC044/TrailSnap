"""Nightly coverage for ``app.core.model_phase`` guard branches.

The 2026-10-21 AI coverage gap ranked ``core/model_phase.py`` at 76.7%
(14 of 60 statements uncovered). ``tests/test_model_phase.py`` already
covers the concurrency contract (same-family parallelism, cross-family
serialisation, streaming drain on cancellation), but three regions were
never executed:

* ``prepare_family`` -- the actual model swap, including the "keep the LLM
  resident" rule for the ``llm`` family.
* the middleware passthrough branches -- a request that is not a POST, is
  not HTTP, targets an unknown prefix, or runs while
  ``AI_SINGLE_MODEL_FAMILY`` is disabled must NOT take a model slot.
* the coordinator's error path -- a failed preparation must leave the
  coordinator usable instead of pinning the wrong family.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.model_phase import ModelPhaseCoordinator, ModelPhaseMiddleware, prepare_family


pytestmark = [pytest.mark.smoke, pytest.mark.asyncio]


# ---------------------------------------------------------------------------
# prepare_family
# ---------------------------------------------------------------------------


async def test_prepare_family_stops_llm_before_switching(monkeypatch):
    """Moving away from the LLM family must release the LLM first."""
    calls: list[str] = []

    llm_manager = SimpleNamespace(stop=AsyncMock(side_effect=lambda: calls.append("llm.stop")))
    model_manager = SimpleNamespace(
        release_except=lambda family: calls.append(f"release:{family}")
    )
    monkeypatch.setattr(
        "app.services.model_manager.model_manager", model_manager, raising=False
    )
    monkeypatch.setattr("app.services.llm_manager.llm_manager", llm_manager, raising=False)

    await prepare_family("classification")

    assert calls == ["llm.stop", "release:classification"]
    llm_manager.stop.assert_awaited_once()


async def test_prepare_family_keeps_llm_resident(monkeypatch):
    """The ``llm`` family must not stop the LLM it is about to use."""
    calls: list[str] = []

    llm_manager = SimpleNamespace(stop=AsyncMock(side_effect=lambda: calls.append("llm.stop")))
    model_manager = SimpleNamespace(
        release_except=lambda family: calls.append(f"release:{family}")
    )
    monkeypatch.setattr(
        "app.services.model_manager.model_manager", model_manager, raising=False
    )
    monkeypatch.setattr("app.services.llm_manager.llm_manager", llm_manager, raising=False)

    await prepare_family("llm")

    assert calls == ["release:llm"]
    llm_manager.stop.assert_not_awaited()


# ---------------------------------------------------------------------------
# ModelPhaseCoordinator -- error path
# ---------------------------------------------------------------------------


async def test_failed_preparation_leaves_coordinator_usable():
    """A failed preparation must not pin the coordinator to a wrong family."""

    async def prepare(family):
        raise RuntimeError("model download failed")

    coordinator = ModelPhaseCoordinator(prepare)

    with pytest.raises(RuntimeError):
        async with coordinator.slot("face"):
            pass

    # The failed attempt must not be counted as an active slot.
    assert coordinator.active == 0
    assert coordinator.family is None

    # A later, successful preparation still works.
    prepared: list[str] = []

    async def ok(family):
        prepared.append(family)

    coordinator.prepare = ok
    async with coordinator.slot("face"):
        assert coordinator.active == 1
    assert prepared == ["face"]
    assert coordinator.family == "face"


async def test_slot_releases_active_count_on_exception():
    """An exception inside the slot still frees the slot for the next family."""
    coordinator = ModelPhaseCoordinator(AsyncMock())

    with pytest.raises(ValueError):
        async with coordinator.slot("ocr"):
            raise ValueError("boom")

    assert coordinator.active == 0


# ---------------------------------------------------------------------------
# ModelPhaseMiddleware -- passthrough branches
# ---------------------------------------------------------------------------


async def _passthrough(monkeypatch, scope) -> tuple[list[str], ModelPhaseMiddleware]:
    """Run the middleware with a recording app and return the call order."""
    order: list[str] = []

    async def app(inner_scope, receive, send):
        order.append(inner_scope.get("path", ""))
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"", "more_body": False})

    middleware = ModelPhaseMiddleware(app)
    middleware.coordinator.prepare = AsyncMock()
    await middleware(scope, AsyncMock(), AsyncMock())
    return order, middleware


async def test_middleware_passes_through_get_requests(monkeypatch):
    """Only POST requests may take a model slot."""
    monkeypatch.setattr("app.core.model_phase.settings.AI_SINGLE_MODEL_FAMILY", True)

    order, middleware = await _passthrough(
        monkeypatch, {"type": "http", "method": "GET", "path": "/face/identities"}
    )

    assert order == ["/face/identities"]
    middleware.coordinator.prepare.assert_not_awaited()


async def test_middleware_passes_through_unknown_prefix(monkeypatch):
    """A prefix without a model family must not take a model slot."""
    monkeypatch.setattr("app.core.model_phase.settings.AI_SINGLE_MODEL_FAMILY", True)

    order, middleware = await _passthrough(
        monkeypatch, {"type": "http", "method": "POST", "path": "/system/health"}
    )

    assert order == ["/system/health"]
    middleware.coordinator.prepare.assert_not_awaited()


async def test_middleware_passes_through_websocket_scope(monkeypatch):
    """A non-HTTP scope must not take a model slot."""
    monkeypatch.setattr("app.core.model_phase.settings.AI_SINGLE_MODEL_FAMILY", True)

    order, middleware = await _passthrough(
        monkeypatch, {"type": "websocket", "method": "POST", "path": "/face/stream"}
    )

    assert order == ["/face/stream"]
    middleware.coordinator.prepare.assert_not_awaited()


async def test_middleware_passes_through_when_single_family_disabled(monkeypatch):
    """With the single-family mode off every request goes straight through."""
    monkeypatch.setattr("app.core.model_phase.settings.AI_SINGLE_MODEL_FAMILY", False)

    order, middleware = await _passthrough(
        monkeypatch, {"type": "http", "method": "POST", "path": "/v1/chat/completions"}
    )

    assert order == ["/v1/chat/completions"]
    middleware.coordinator.prepare.assert_not_awaited()


@pytest.mark.parametrize(
    ("path", "family"),
    [
        ("/classification/predict", "classification"),
        ("/face/face-recognition", "face"),
        ("/embedding/text", "embedding"),
        ("/ocr/predict", "ocr"),
        ("/tickets/parse", "tickets"),
        ("/v1/chat/completions", "llm"),
    ],
)
async def test_middleware_maps_prefix_to_model_family(monkeypatch, path, family):
    """Each known prefix must be mapped to its model family."""
    monkeypatch.setattr("app.core.model_phase.settings.AI_SINGLE_MODEL_FAMILY", True)

    order, middleware = await _passthrough(
        monkeypatch, {"type": "http", "method": "POST", "path": path}
    )

    assert order == [path]
    middleware.coordinator.prepare.assert_awaited_once_with(family)
    assert middleware.coordinator.family == family
