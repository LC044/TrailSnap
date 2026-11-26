"""Nightly watch 2026-11-25 · app/service/clip_classification.py 的 AI 可用性判定盲区。

覆盖扫描显示 clip_classification.py 未覆盖的行里有一组是「AI 到底准备好了没有」
的判定分支：模型列表里被选中的 runtimeName（L104-L107）、以及 ai_request 把
「文本模型尚未就绪 / 服务尚未就绪 / 服务暂不可达」翻译成可重试错误的三个出口
（L126-L127）。这些分支决定了分类任务是等待重试还是直接失败，属于会直接影响
用户任务状态的核心判定。

本文件用假的 HTTP 响应验证这四种判定。
"""

import pytest
import requests

from app.service import clip_classification

pytestmark = [pytest.mark.regression, pytest.mark.module_classification]


class _Response:
    def __init__(self, payload=None, text="", status_code=200):
        self._payload = payload or {}
        self.text = text
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error", response=self)


def test_selected_embedding_model_returns_the_selected_runtime_name(monkeypatch):
    response = _Response(payload={
        "tasks": {"embedding": {"selected": "clip-vit-b32"}},
        "models": [{"id": "clip-vit-b32", "runtimeName": "clip-vit-b32.onnx"},
                   {"id": "other", "runtimeName": "other.onnx"}],
    })
    monkeypatch.setattr(clip_classification.requests, "get", lambda url, **kwargs: response)

    assert clip_classification.selected_embedding_model("http://ai") == "clip-vit-b32.onnx"


def test_not_ready_body_becomes_a_retryable_error(monkeypatch):
    response = _Response(text="model not ready", status_code=400)
    monkeypatch.setattr(clip_classification.requests, "get", lambda url, **kwargs: response)

    with pytest.raises(RuntimeError) as excinfo:
        clip_classification.ai_request(clip_classification.requests.get, "http://ai/x", timeout=15)

    assert "文本模型尚未就绪" in str(excinfo.value)


def test_unavailable_status_becomes_a_retryable_error(monkeypatch):
    response = _Response(text="unavailable", status_code=503)
    monkeypatch.setattr(clip_classification.requests, "get", lambda url, **kwargs: response)

    with pytest.raises(RuntimeError) as excinfo:
        clip_classification.ai_request(clip_classification.requests.get, "http://ai/x", timeout=15)

    assert "服务或模型尚未就绪" in str(excinfo.value)


def test_connection_error_becomes_a_retryable_error(monkeypatch):
    def _boom(url, **kwargs):
        raise requests.ConnectionError("connection refused")

    with pytest.raises(RuntimeError) as excinfo:
        clip_classification.ai_request(_boom, "http://ai/x", timeout=15)

    assert "AI 服务暂不可达" in str(excinfo.value)
