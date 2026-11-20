"""AI model snapshot refresh, including the invalidation race."""
import threading

import pytest
import requests

from app.service import ai_model_state

pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


class _Response:
    def __init__(self, payload, status=200):
        self._payload = payload
        self._status = status

    def raise_for_status(self):
        if self._status >= 400:
            raise requests.HTTPError("boom")

    def json(self):
        return self._payload


@pytest.fixture(autouse=True)
def _clean_state():
    with ai_model_state._lock:
        ai_model_state._cache.clear()
        ai_model_state._refreshing.clear()
    yield
    with ai_model_state._lock:
        ai_model_state._cache.clear()
        ai_model_state._refreshing.clear()


def test_publishes_a_fetched_snapshot(monkeypatch):
    monkeypatch.setattr(ai_model_state.requests, "get", lambda url, timeout=None: _Response({"models": ["a"]}))
    url = "http://ai/ai/models"
    pending = threading.Event()
    with ai_model_state._lock:
        ai_model_state._refreshing[url] = pending
    ai_model_state._refresh_snapshot(url, pending)
    assert ai_model_state._cache[url][1] == {"models": ["a"]}
    assert pending.is_set()


def test_marks_the_model_unavailable_when_the_request_fails(monkeypatch):
    def _boom(url, timeout=None):
        raise requests.RequestException("offline")

    monkeypatch.setattr(ai_model_state.requests, "get", _boom)
    url = "http://ai/ai/models"
    pending = threading.Event()
    with ai_model_state._lock:
        ai_model_state._refreshing[url] = pending
    ai_model_state._refresh_snapshot(url, pending)
    assert ai_model_state._cache[url][1] == {"_unavailable": True}


def test_keeps_the_previous_snapshot_when_the_refresh_fails(monkeypatch):
    def _boom(url, timeout=None):
        raise requests.RequestException("offline")

    url = "http://ai/ai/models"
    with ai_model_state._lock:
        ai_model_state._cache[url] = (0.0, {"models": ["stale"]})
    monkeypatch.setattr(ai_model_state.requests, "get", _boom)
    pending = threading.Event()
    with ai_model_state._lock:
        ai_model_state._refreshing[url] = pending
    ai_model_state._refresh_snapshot(url, pending)
    assert ai_model_state._cache[url][1] == {"models": ["stale"]}


def test_does_not_publish_a_detached_refresh(monkeypatch):
    monkeypatch.setattr(ai_model_state.requests, "get", lambda url, timeout=None: _Response({"models": ["late"]}))
    url = "http://ai/ai/models"
    pending = threading.Event()
    # No entry in _refreshing: the request was detached by an invalidation.
    ai_model_state._refresh_snapshot(url, pending)
    assert url not in ai_model_state._cache
    assert pending.is_set()


def test_ignores_a_non_dict_payload(monkeypatch):
    monkeypatch.setattr(ai_model_state.requests, "get", lambda url, timeout=None: _Response([1, 2, 3]))
    url = "http://ai/ai/models"
    pending = threading.Event()
    with ai_model_state._lock:
        ai_model_state._refreshing[url] = pending
    ai_model_state._refresh_snapshot(url, pending)
    assert ai_model_state._cache[url][1] == {"_unavailable": True}
