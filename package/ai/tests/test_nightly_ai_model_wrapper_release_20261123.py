"""Nightly watch 2026-11-23 - app/services/model_manager.py 的释放路径盲区。

ModelWrapper 负责按需加载 / 释放 AI 模型。_release_locked 必须在锁保护下
卸载模型、调用可选的 release_func 并清理 CUDA 缓存；release_async 还要在
后台释放期间阻止其它线程拿到旧模型。

本文件覆盖：

- get() 惰性加载并缓存模型（happy）
- release() 调用 release_func 并清空模型（happy）
- release_func 抛错时模型依然被卸载（error）
- 对未加载的模型调用 release() 不报错（edge）
- release_async() 在模型为空时返回 False（edge）
- release_async() 在后台释放并返回 True（happy）
- 释放进行中 get() 会等待（happy）
"""

import threading
import time

import pytest

from app.services.model_manager import ModelWrapper

pytestmark = [pytest.mark.smoke]


def test_get_loads_the_model_lazily_and_caches_it():
    calls = []

    def load():
        calls.append(1)
        return "model"

    wrapper = ModelWrapper("demo", load)

    assert wrapper.model is None
    assert wrapper.get() == "model"
    assert wrapper.get() == "model"
    assert len(calls) == 1


def test_release_calls_the_release_func_and_clears_the_model():
    released = []

    wrapper = ModelWrapper("demo", lambda: "model", lambda model: released.append(model))
    wrapper.get()

    wrapper.release()

    assert released == ["model"]
    assert wrapper.model is None


def test_release_survives_a_failing_release_func():
    def boom(model):
        raise RuntimeError("release failed")

    wrapper = ModelWrapper("demo", lambda: "model", boom)
    wrapper.get()

    wrapper.release()

    assert wrapper.model is None


def test_release_on_an_unloaded_model_is_a_no_op():
    wrapper = ModelWrapper("demo", lambda: "model")

    wrapper.release()

    assert wrapper.model is None


def test_release_async_returns_false_without_a_model():
    wrapper = ModelWrapper("demo", lambda: "model")

    assert wrapper.release_async() is False


def test_release_async_releases_in_the_background():
    released = threading.Event()

    def release_func(model):
        released.set()

    wrapper = ModelWrapper("demo", lambda: "model", release_func)
    wrapper.get()

    assert wrapper.release_async() is True
    assert released.wait(5)
    # 后台线程在 _release_locked 之后才复位 releasing，所以要等这个信号。
    for _ in range(200):
        if wrapper.releasing is False:
            break
        time.sleep(0.02)
    assert wrapper.model is None
    assert wrapper.releasing is False


def test_get_waits_while_a_release_is_in_progress():
    wrapper = ModelWrapper("demo", lambda: "model")
    wrapper.model = "model"
    wrapper.releasing = True
    result = []

    worker = threading.Thread(target=lambda: result.append(wrapper.get()))
    worker.start()
    time.sleep(0.2)

    assert result == []

    with wrapper.condition:
        wrapper.releasing = False
        wrapper.condition.notify_all()
    worker.join(5)

    assert result == ["model"]
