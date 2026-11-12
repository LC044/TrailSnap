from concurrent.futures import ThreadPoolExecutor
import threading
from unittest.mock import MagicMock

import pytest
import requests

from app.db.models.task import TaskType
from app.service import ai_model_state as state

pytestmark = [pytest.mark.smoke, pytest.mark.module_system]
TASK = TaskType.RECOGNIZE_FACE
URL = "http://one"


def snapshot(status):
    return {"models": [{"id": "face", "name": "Face", "status": status}],
            "tasks": {"face": {"selected": "face"}}}


def response(status):
    result = MagicMock()
    result.json.return_value = snapshot(status)
    return result


@pytest.fixture(autouse=True)
def cache(monkeypatch):
    monkeypatch.setattr(state, "_cache", {})
    monkeypatch.setattr(state, "_refreshing", {})


def stale(status, url=URL):
    state._cache[url + "/ai/models"] = (state.time.monotonic() - 10, snapshot(status))


def test_ready_refresh_returns_immediately_and_is_shared(monkeypatch):
    stale("ready")
    entered, release = threading.Event(), threading.Event()
    def get(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return response("downloading")
    get_mock = MagicMock(side_effect=get)
    monkeypatch.setattr(state.requests, "get", get_mock)
    pending = None
    try:
        assert state.get_model_wait_reason(URL, TASK) is None
        assert entered.wait(2)
        pending = state._refreshing[URL + "/ai/models"]
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(state.get_model_wait_reason, URL, TASK) for _ in range(8)]
            assert all(f.result(timeout=1) is None for f in futures)
        get_mock.assert_called_once()
    finally:
        release.set()
        if pending:
            assert pending.wait(2)
    assert "正在下载" in state.get_model_wait_reason(URL, TASK)


def test_slow_service_does_not_block_another_service(monkeypatch):
    stale("pending")
    entered, release = threading.Event(), threading.Event()
    def get(url, **kwargs):
        if url.startswith(URL):
            entered.set()
            assert release.wait(5)
        return response("ready")
    monkeypatch.setattr(state.requests, "get", get)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(state.get_model_wait_reason, URL, TASK)
        try:
            assert entered.wait(2)
            assert pool.submit(state.get_model_wait_reason, "http://two", TASK).result(timeout=1) is None
            assert not first.done()
        finally:
            release.set()
        assert first.result(timeout=2) is None


def test_first_query_is_shared_and_download_can_resume(monkeypatch):
    entered, release = threading.Event(), threading.Event()
    def get(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return response("downloading")
    get_mock = MagicMock(side_effect=get)
    monkeypatch.setattr(state.requests, "get", get_mock)
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(state.get_model_wait_reason, URL, TASK) for _ in range(4)]
        try:
            assert entered.wait(2)
            assert not futures[0].done()
        finally:
            release.set()
        assert all("正在下载" in f.result(timeout=2) for f in futures)
    get_mock.assert_called_once()
    stale("downloading")
    get_mock.side_effect = None
    get_mock.return_value = response("ready")
    assert state.get_model_wait_reason(URL, TASK) is None
    assert get_mock.call_count == 2


@pytest.mark.parametrize("initial", [None, "ready", "downloading"])
def test_query_failure_is_throttled_and_recovers(monkeypatch, initial):
    if initial:
        stale(initial)
    get = MagicMock(side_effect=requests.ConnectionError("offline"))
    monkeypatch.setattr(state.requests, "get", get)
    reason = state.get_model_wait_reason(URL, TASK)
    with state._lock:
        pending = state._refreshing.get(URL + "/ai/models")
    if pending:
        assert pending.wait(2)
    assert (reason is not None) == (initial == "downloading")
    assert state.get_model_wait_reason(URL, TASK) == reason
    assert get.call_count == 1
    state.invalidate_model_state(URL)
    get.side_effect = None
    get.return_value = response("ready")
    assert state.get_model_wait_reason(URL, TASK) is None
    assert get.call_count == 2


def test_invalidation_prevents_old_background_result_overwriting_new_state(monkeypatch):
    stale("ready")
    entered, release = threading.Event(), threading.Event()
    def get(*args, **kwargs):
        if not entered.is_set():
            entered.set()
            assert release.wait(5)
            return response("ready")
        return response("downloading")
    monkeypatch.setattr(state.requests, "get", get)
    assert state.get_model_wait_reason(URL, TASK) is None
    assert entered.wait(2)
    pending = state._refreshing[URL + "/ai/models"]
    try:
        state.invalidate_model_state(URL)
        assert "正在下载" in state.get_model_wait_reason(URL, TASK)
    finally:
        release.set()
        # The detached request's event is already signalled by invalidation;
        # join the daemon to verify its late completion cannot republish ready.
        for thread in threading.enumerate():
            if thread.name == "ai-model-refresh":
                thread.join(timeout=2)
    assert pending.is_set()
    assert "正在下载" in state.get_model_wait_reason(URL, TASK)
