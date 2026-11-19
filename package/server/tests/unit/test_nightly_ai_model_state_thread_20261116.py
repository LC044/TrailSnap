"""2026-11-16 nightly coverage for ``app/service/ai_model_state.py``.

The 2026-11-16 backend coverage scan reported ``service/ai_model_state.py``
at 95.1% with 5 missed lines: the ``RuntimeError`` branch of the
background refresh (lines 117-121).

When the interpreter refuses to start the refresh thread (thread limit
reached during interpreter shutdown), the pending event must still be
released, otherwise every waiting task blocks forever.
"""

from __future__ import annotations

import threading
import time

import pytest

from app.db.models.task import TaskType
from app.service import ai_model_state as state


pytestmark = [pytest.mark.smoke]


@pytest.fixture(autouse=True)
def _isolated_cache():
    state._cache.clear()
    state._refreshing.clear()
    yield
    state._cache.clear()
    state._refreshing.clear()


def test_get_model_wait_reason_releases_the_pending_event_when_the_thread_cannot_start(monkeypatch):
    url = state._snapshot_url("http://ai.test")
    # A *stale* but healthy snapshot makes the caller a background refresher.
    state._cache[url] = (time.monotonic() - state._CACHE_TTL - 1, {"models": []})

    def _no_thread(*args, **kwargs):
        raise RuntimeError("can't start new thread")

    monkeypatch.setattr(threading, "Thread", _no_thread)

    reason = state.get_model_wait_reason("http://ai.test", TaskType.OCR)

    assert reason is None
    # The pending entry was dropped and its event set, so no task stays blocked.
    assert url not in state._refreshing


def test_invalidate_model_state_detaches_an_in_flight_refresh():
    url = state._snapshot_url("http://ai.test")
    pending = threading.Event()
    state._refreshing[url] = pending
    state._cache[url] = (time.monotonic(), {"models": []})

    state.invalidate_model_state("http://ai.test")

    assert url not in state._refreshing
    assert url not in state._cache
    assert pending.is_set()


def test_model_wait_reason_reports_an_unreachable_service():
    reason = state.model_wait_reason(
        {"_unavailable": True}, TaskType.IMAGE_EMBEDDING
    )
    assert reason is not None and "AI 服务暂不可达" in reason
    assert state.model_wait_reason({"_unavailable": True}, TaskType.OCR) is None


