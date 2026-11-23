"""Nightly watch 2026-11-23 - app/service/agent/service.py 的 FixedChatOpenAI 流式兼容盲区。

部分兼容供应商不支持流式 usage（include_usage / stream_options），会在第一个
chunk 之前就返回 400。FixedChatOpenAI 在这种情况下自动退回不带 usage 的
流式请求，让对话不至于整个失败。

本文件覆盖：

- _stream_usage_rejected 识别 usage 相关报错（happy / edge）
- 尚未产出任何 chunk 时自动降级重试（happy）
- 与 usage 无关的报错直接抛出，不吞掉真实故障（error）
- 已经产出过 chunk 时不重试，避免重复内容（edge）
- 异步版本 _astream 具备同样的降级行为（happy）
"""

import httpx
import pytest
from langchain_openai import ChatOpenAI
from openai import BadRequestError

from app.service.agent.service import FixedChatOpenAI

pytestmark = [pytest.mark.smoke]


def _client():
    return FixedChatOpenAI(
        model="gpt-4o-mini",
        api_key="test-key",
        base_url="http://localhost:9/v1",
    )


def _bad_request(message: str) -> BadRequestError:
    request = httpx.Request("POST", "http://localhost:9/v1/chat/completions")
    response = httpx.Response(400, request=request, json={"error": {"message": message}})
    return BadRequestError(message, response=response, body={"error": {"message": message}})


def test_stream_usage_rejected_detects_usage_errors():
    client = _client()

    assert client._stream_usage_rejected(_bad_request("include_usage is not supported")) is True
    assert client._stream_usage_rejected(_bad_request("stream_options is not allowed")) is True


def test_stream_usage_rejected_ignores_unrelated_errors():
    client = _client()

    assert client._stream_usage_rejected(_bad_request("model not found")) is False


def test_stream_retries_without_usage_when_the_provider_rejects_it(monkeypatch):
    client = _client()
    calls = []

    def fake_stream(self, *args, **kwargs):
        calls.append(kwargs.get("stream_usage"))
        if kwargs.get("stream_usage"):
            raise _bad_request("include_usage is not supported")
        yield "chunk-1"

    monkeypatch.setattr(ChatOpenAI, "_stream", fake_stream)

    chunks = list(client._stream([{"role": "user", "content": "hi"}], stream_usage=True))

    assert chunks == ["chunk-1"]
    assert calls == [True, False]


def test_stream_reraises_unrelated_errors(monkeypatch):
    client = _client()

    def fake_stream(self, *args, **kwargs):
        raise _bad_request("model not found")
        yield  # pragma: no cover - generator marker

    monkeypatch.setattr(ChatOpenAI, "_stream", fake_stream)

    with pytest.raises(BadRequestError):
        list(client._stream([{"role": "user", "content": "hi"}], stream_usage=True))


def test_stream_does_not_retry_after_a_chunk_was_emitted(monkeypatch):
    client = _client()
    calls = []

    def fake_stream(self, *args, **kwargs):
        calls.append(kwargs.get("stream_usage"))
        yield "chunk-1"
        raise _bad_request("include_usage is not supported")

    monkeypatch.setattr(ChatOpenAI, "_stream", fake_stream)

    with pytest.raises(BadRequestError):
        list(client._stream([{"role": "user", "content": "hi"}], stream_usage=True))

    assert calls == [True]


@pytest.mark.asyncio
async def test_astream_retries_without_usage_when_the_provider_rejects_it(monkeypatch):
    client = _client()
    calls = []

    async def fake_astream(self, *args, **kwargs):
        calls.append(kwargs.get("stream_usage"))
        if kwargs.get("stream_usage"):
            raise _bad_request("include_usage is not supported")
        yield "chunk-1"

    monkeypatch.setattr(ChatOpenAI, "_astream", fake_astream)

    chunks = [chunk async for chunk in client._astream([{"role": "user", "content": "hi"}], stream_usage=True)]

    assert chunks == ["chunk-1"]
    assert calls == [True, False]
