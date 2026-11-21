"""夜间盲区补测：CLIP 分类的文本向量批量获取与缓存。

覆盖 app/service/clip_classification.py 的 ``_category_vectors``
（此前未被任何单测按名引用）。
"""
from collections import OrderedDict

import pytest

from app.service import clip_classification as cc

pytestmark = [pytest.mark.smoke, pytest.mark.regression]

MODEL = "clip-vit-base"


class _Response:
    def __init__(self, payload, model=MODEL):
        self._payload = payload
        self.headers = {"X-Embedding-Model": model}

    def json(self):
        return self._payload


@pytest.fixture(autouse=True)
def _clear_cache(monkeypatch):
    """每个用例都用干净的向量缓存，避免用例之间互相污染。"""
    monkeypatch.setattr(cc, "_cache", OrderedDict())


def _patch_ai(monkeypatch, response, calls):
    def fake_ai_request(method, url, **kwargs):
        calls.append({"method": method, "url": url, **kwargs})
        return response

    monkeypatch.setattr(cc, "ai_request", fake_ai_request)
    monkeypatch.setattr(cc, "prototype", lambda vectors: [sum(row) / len(row) for row in vectors])


def test_category_vectors_batches_missing_groups_only(monkeypatch):
    """只有缺失的分组才会触发 AI 请求，并按分组返回均值向量。"""
    calls = []
    _patch_ai(monkeypatch, _Response([[1.0, 3.0], [2.0, 2.0]]), calls)
    groups = [["猫"], ["狗"]]

    result = cc._category_vectors("http://ai", MODEL, groups)

    assert len(calls) == 1
    assert calls[0]["url"] == "http://ai/embedding/text"
    assert calls[0]["json"]["texts"] == ["猫", "狗"]
    assert result == [[2.0], [2.0]]


def test_category_vectors_reuses_cached_entry(monkeypatch):
    """命中缓存的分组不得再次调用 AI。"""
    calls = []
    _patch_ai(monkeypatch, _Response([[2.0, 4.0]]), calls)

    first = cc._category_vectors("http://ai", MODEL, [["猫"]])
    second = cc._category_vectors("http://ai", MODEL, [["猫"]])

    assert len(calls) == 1
    assert first == second == [[3.0]]


def test_category_vectors_returns_independent_copies(monkeypatch):
    """返回的向量必须是副本，调用方修改不得污染缓存。"""
    calls = []
    _patch_ai(monkeypatch, _Response([[2.0, 4.0]]), calls)

    result = cc._category_vectors("http://ai", MODEL, [["猫"]])
    result[0][0] = 99.0

    again = cc._category_vectors("http://ai", MODEL, [["猫"]])
    assert again == [[3.0]]


def test_category_vectors_rejects_model_mismatch(monkeypatch):
    """AI 返回的模型与请求不一致时必须报错，不得静默使用。"""
    calls = []
    _patch_ai(monkeypatch, _Response([[1.0, 1.0]], model="other-model"), calls)

    with pytest.raises(ValueError):
        cc._category_vectors("http://ai", MODEL, [["猫"]])


def test_category_vectors_rejects_length_mismatch(monkeypatch):
    """AI 返回的向量条数与请求文本数不一致时必须报错。"""
    calls = []
    _patch_ai(monkeypatch, _Response([[1.0, 1.0]]), calls)

    with pytest.raises(ValueError):
        cc._category_vectors("http://ai", MODEL, [["猫"], ["狗"]])
