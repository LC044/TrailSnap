"""Nightly coverage for the cancellation paths of ``app.core.model_phase``.

The 2026-10-24 AI coverage report ranked ``core/model_phase.py`` at 90.0%
with 6 statements never executed.  All of them belong to the two
cancellation paths:

* ``ModelPhaseCoordinator.slot`` -- when the *holder* of the slot is
  cancelled while the next model family is still being prepared, the
  coordinator must wait for that preparation to finish before releasing
  the lock.  Otherwise a different family could unload the model while
  the previous one is still loading.
* ``ModelPhaseMiddleware`` -- when an HTTP request is cancelled, the
  middleware drains the in-flight inference instead of letting the next
  request unload the model out from under it.

Both paths are "must not lose track of native work" guarantees, and both
were completely untested.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from app.core.model_phase import ModelPhaseCoordinator, ModelPhaseMiddleware


pytestmark = [pytest.mark.smoke, pytest.mark.asyncio]


async def _use_slot(coordinator: ModelPhaseCoordinator, family: str) -> None:
    async with coordinator.slot(family):
        pass


# ---------------------------------------------------------------------------
# ModelPhaseCoordinator.slot -- cancelled while preparing
# ---------------------------------------------------------------------------


async def test_slot_awaits_preparation_after_holder_is_cancelled():
    """A cancelled holder still waits for the in-flight preparation."""
    started = asyncio.Event()
    prepared: list[str] = []

    async def prepare(family):
        started.set()
        await asyncio.sleep(0.05)
        prepared.append(family)

    coordinator = ModelPhaseCoordinator(prepare)
    holder = asyncio.create_task(_use_slot(coordinator, "face"))

    await asyncio.wait_for(started.wait(), timeout=2)
    holder.cancel()

    with pytest.raises(asyncio.CancelledError):
        await holder

    # The preparation ran to completion despite the cancellation.
    assert prepared == ["face"]
    # The slot was never handed out, so the counter stays balanced.
    assert coordinator.active == 0


async def test_cancelled_slot_leaves_coordinator_usable():
    """After a cancelled preparation the coordinator still serves requests."""
    async def prepare(family):
        await asyncio.sleep(0.02)

    coordinator = ModelPhaseCoordinator(prepare)

    cancelled = asyncio.create_task(_use_slot(coordinator, "face"))
    await asyncio.sleep(0)
    cancelled.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cancelled

    prepared: list[str] = []

    async def ok(family):
        prepared.append(family)

    coordinator.prepare = ok
    async with coordinator.slot("face"):
        pass

    assert prepared == ["face"]
    assert coordinator.active == 0


# ---------------------------------------------------------------------------
# ModelPhaseMiddleware -- draining a cancelled request
# ---------------------------------------------------------------------------


def _scope(path: str = "/ocr/predict") -> dict:
    return {"type": "http", "method": "POST", "path": path}


async def test_middleware_drains_request_even_when_cancelled_twice(monkeypatch):
    """A second cancellation must not abandon the in-flight inference."""
    monkeypatch.setattr("app.core.model_phase.settings.AI_SINGLE_MODEL_FAMILY", True)

    started = asyncio.Event()
    release = asyncio.Event()
    finished = asyncio.Event()

    async def app(scope, receive, send):
        started.set()
        await release.wait()
        finished.set()

    middleware = ModelPhaseMiddleware(app)
    middleware.coordinator.prepare = AsyncMock()

    task = asyncio.create_task(middleware(_scope(), AsyncMock(), AsyncMock()))
    await asyncio.wait_for(started.wait(), timeout=2)

    task.cancel()
    await asyncio.sleep(0.05)
    task.cancel()
    await asyncio.sleep(0.05)
    release.set()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert finished.is_set()


async def test_middleware_stops_draining_when_the_request_fails(monkeypatch):
    """A request that errors out ends the drain loop immediately."""
    monkeypatch.setattr("app.core.model_phase.settings.AI_SINGLE_MODEL_FAMILY", True)

    started = asyncio.Event()
    release = asyncio.Event()

    async def app(scope, receive, send):
        started.set()
        await release.wait()
        raise RuntimeError("inference failed")

    middleware = ModelPhaseMiddleware(app)
    middleware.coordinator.prepare = AsyncMock()

    task = asyncio.create_task(middleware(_scope(), AsyncMock(), AsyncMock()))
    await asyncio.wait_for(started.wait(), timeout=2)

    task.cancel()
    await asyncio.sleep(0.05)
    release.set()

    with pytest.raises(asyncio.CancelledError):
        await task

    # The coordinator is usable again -- the slot was released.
    assert middleware.coordinator.active == 0
