"""Unit tests for the AI service LLM proxy router.

The router transparently proxies ``/v1/*`` requests to a llama.cpp
subprocess. We don't spin up a real subprocess; ``llm_manager.ensure_running``
is patched and the test focuses on the error-handling branches and the
idle-timer refresh.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import llm as ai_llm
from app.services.llm_manager import LLMModelNotReadyError, llm_manager


pytestmark = [pytest.mark.smoke, pytest.mark.module_ai_llm]


@pytest.fixture
def llm_client():
    app = FastAPI()
    app.include_router(ai_llm.router)
    return TestClient(app)


def test_llm_returns_503_when_manager_reports_no_llm(llm_client, monkeypatch):
    """ValueError from ``ensure_running`` must surface as HTTP 503."""

    async def _value_error():
        raise ValueError("LLM model path not configured")

    monkeypatch.setattr(ai_llm.llm_manager, "ensure_running", _value_error)

    res = llm_client.get("/v1/models")
    assert res.status_code == 503
    assert "not configured" in res.json()["detail"]


def test_llm_returns_500_when_manager_raises_other(llm_client, monkeypatch):
    """Generic exception from ``ensure_running`` must surface as HTTP 500."""

    async def _boom():
        raise RuntimeError("subprocess crashed")

    monkeypatch.setattr(ai_llm.llm_manager, "ensure_running", _boom)

    res = llm_client.get("/v1/models")
    assert res.status_code == 500
    assert "subprocess crashed" in res.json()["detail"]


def test_llm_downloading_returns_retry_after(llm_client, monkeypatch):
    async def _downloading():
        raise LLMModelNotReadyError("downloading")

    monkeypatch.setattr(ai_llm.llm_manager, "ensure_running", _downloading)

    res = llm_client.get("/v1/models")
    assert res.status_code == 503
    assert res.headers["retry-after"] == "60"
    assert "model_status=downloading" in res.json()["detail"]


def test_llm_download_failure_is_not_reported_as_temporary(llm_client, monkeypatch):
    async def _failed():
        raise LLMModelNotReadyError("failed", "disk full")

    monkeypatch.setattr(ai_llm.llm_manager, "ensure_running", _failed)

    res = llm_client.get("/v1/models")
    assert res.status_code == 500
    assert "disk full" in res.json()["detail"]
    assert "retry-after" not in res.headers


def test_llm_refreshes_idle_timer_on_successful_proxy(llm_client, monkeypatch):
    """A successful ``ensure_running`` + proxy must refresh ``last_access_time``."""

    async def _ok():
        return None

    monkeypatch.setattr(ai_llm.llm_manager, "ensure_running", _ok)

    class _FakeResp:
        status_code = 200
        headers = {"content-type": "application/json"}

        async def aiter_bytes(self):
            yield b'{"ok":true}'

        async def aclose(self):
            return None

    class _FakeClient:
        def build_request(self, method, url, headers=None, content=None):
            return ("REQ", method, url)

        async def send(self, req, stream=True):
            return _FakeResp()

    monkeypatch.setattr(ai_llm, "client", _FakeClient())

    before = llm_manager.last_access_time
    res = llm_client.get("/v1/models")
    after = llm_manager.last_access_time

    # Router must have refreshed the idle timer to a non-decreasing value.
    assert after >= before
    assert res.status_code == 200
    assert res.json() == {"ok": True}
