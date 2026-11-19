"""覆盖 app/service/clip_classification.py 中此前没有测试引用的两个向量层函数。

盲区来源：函数级静态引用扫描命中 vector_generation_lock /
_multimodal_category_vectors。

- vector_generation_lock 按 (endpoint, model) 串行化冷启动向量填充，
  漏掉它会让并发预览把同一批规则重复编码；
- _multimodal_category_vectors 把文本与图片各投一票再取均值原型，
  并且用带哈希的键缓存，避免把图片字节留在内存缓存里。

既有测试只走 normalize / prototype 等纯数学函数，从未断言这两个函数。
"""
from __future__ import annotations

import threading
import time

import pytest

from app.service import clip_classification

pytestmark = [pytest.mark.smoke, pytest.mark.module_classification]


@pytest.fixture(autouse=True)
def _clear_vector_cache():
    clip_classification._cache.clear()
    yield
    clip_classification._cache.clear()


def test_vector_generation_lock_serializes_the_same_endpoint_and_model():
    entered = threading.Event()
    finish = threading.Event()

    def worker():
        with clip_classification.vector_generation_lock("http://ai.local", "embed-v1"):
            entered.set()
            finish.wait(5)

    with clip_classification.vector_generation_lock("http://ai.local", "embed-v1"):
        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        time.sleep(0.2)
        # 同一个 endpoint + model 上，第二个进入者必须等待。
        assert entered.is_set() is False
    finish.set()
    thread.join(5)
    assert entered.is_set() is True
    assert thread.is_alive() is False


def test_vector_generation_lock_does_not_block_a_different_model():
    with clip_classification.vector_generation_lock("http://ai.local", "embed-v1"):
        with clip_classification.vector_generation_lock("http://ai.local", "embed-v2"):
            pass


def test_vector_generation_lock_releases_its_registry_entry():
    key = ("http://ai.local", "embed-v1")
    with clip_classification.vector_generation_lock(*key):
        assert key in clip_classification._vector_locks
    # 退出后必须注销登记项，否则互斥量表会无限增长。
    assert key not in clip_classification._vector_locks


def test_multimodal_category_vectors_average_text_and_image_votes(monkeypatch):
    calls = []

    def fake_encode(url, model, kind, items):
        calls.append((kind, tuple(items)))
        return [[1.0, 0.0] for _ in items]

    monkeypatch.setattr(clip_classification, "_encode_rule_items", fake_encode)
    vectors = clip_classification._multimodal_category_vectors(
        "http://ai.local", "embed-v1", [["一张照片"]], [["data:image/jpeg;base64,QUJD"]],
    )
    assert len(vectors) == 1
    assert vectors[0][0] == pytest.approx(1.0)
    assert vectors[0][1] == pytest.approx(0.0)
    # 文本与图片各编码一次，图片只传 base64 负载。
    assert [kind for kind, _ in calls] == ["text", "image"]
    assert calls[1][1] == ("QUJD",)


def test_multimodal_category_vectors_reuses_the_cache(monkeypatch):
    calls = []

    def fake_encode(url, model, kind, items):
        calls.append(kind)
        return [[1.0, 0.0] for _ in items]

    monkeypatch.setattr(clip_classification, "_encode_rule_items", fake_encode)
    first = clip_classification._multimodal_category_vectors(
        "http://ai.local", "embed-v1", [["一张照片"]], [["data:image/jpeg;base64,QUJD"]],
    )
    assert len(calls) == 2
    second = clip_classification._multimodal_category_vectors(
        "http://ai.local", "embed-v1", [["一张照片"]], [["data:image/jpeg;base64,QUJD"]],
    )
    # 命中缓存后不再重复编码。
    assert len(calls) == 2
    assert second[0] == pytest.approx(first[0])


def test_multimodal_category_vectors_separates_different_payloads(monkeypatch):
    calls = []

    def fake_encode(url, model, kind, items):
        calls.append((kind, tuple(items)))
        return [[1.0, 0.0] for _ in items]

    monkeypatch.setattr(clip_classification, "_encode_rule_items", fake_encode)
    clip_classification._multimodal_category_vectors(
        "http://ai.local", "embed-v1", [["第一段"]], [["data:image/jpeg;base64,QQ=="]],
    )
    clip_classification._multimodal_category_vectors(
        "http://ai.local", "embed-v1", [["第二段"]], [["data:image/jpeg;base64,Qg=="]],
    )
    # 文本或图片不同都会换一个缓存键，因此重新编码。
    assert len(calls) == 4

