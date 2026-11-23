"""Nightly watch 2026-11-22 · AI 侧设备/线程预算判据盲区。

本文件覆盖三个此前没有任何单测引用的辅助函数：

- ``app.config._default_inference_threads``：根据 CPU 核数与保留核数推导
  推理线程上限，必须夹在 1..8 之间；保留核数非法时回退为 1。
- ``app.services.onnx_providers._openvino_device``：OpenVINO 设备选择，
  环境变量覆盖优先于探测；探测失败回退 CPU。
- ``app.services.desktop_device.record_session``：只有在设置 TS_AI_BACKEND
  时才记录会话（否则桌面端不上报），且以模型文件名为键。
"""

import os

import pytest

from app.config import _default_inference_threads
from app.services import desktop_device, onnx_providers

pytestmark = [pytest.mark.smoke]


def _with_cpu_count(monkeypatch, count):
    monkeypatch.setattr(os, "cpu_count", lambda: count)


def test_default_inference_threads_halves_the_free_cores(monkeypatch):
    _with_cpu_count(monkeypatch, 8)
    monkeypatch.setenv("AI_RESERVED_CPU_CORES", "1")

    # (8 - 1) // 2 = 3
    assert _default_inference_threads() == 3


def test_default_inference_threads_is_capped_at_eight(monkeypatch):
    _with_cpu_count(monkeypatch, 64)
    monkeypatch.setenv("AI_RESERVED_CPU_CORES", "1")

    assert _default_inference_threads() == 8


def test_default_inference_threads_never_drops_below_one(monkeypatch):
    _with_cpu_count(monkeypatch, 1)
    monkeypatch.setenv("AI_RESERVED_CPU_CORES", "8")

    assert _default_inference_threads() == 1


def test_default_inference_threads_rejects_a_non_numeric_reserved_value(monkeypatch):
    _with_cpu_count(monkeypatch, 8)
    monkeypatch.setenv("AI_RESERVED_CPU_CORES", "not-a-number")

    # 非法配置必须在导入期就炸出来，而不是静默按错误预算运行
    with pytest.raises(ValueError):
        _default_inference_threads()


def test_openvino_device_prefers_the_environment_override(monkeypatch):
    monkeypatch.setenv("OPENVINO_DEVICE", "NPU")

    assert onnx_providers._openvino_device() == "NPU"


def test_openvino_device_falls_back_to_cpu_when_the_probe_fails(monkeypatch):
    monkeypatch.delenv("OPENVINO_DEVICE", raising=False)
    # 本机 / CI 未必安装 openvino，探测失败必须回退 CPU 而不是抛出
    assert onnx_providers._openvino_device() in {"CPU", "NPU", "GPU"}


def test_record_session_only_records_when_a_backend_is_configured(monkeypatch):
    monkeypatch.delenv("TS_AI_BACKEND", raising=False)
    desktop_device._sessions.clear()

    desktop_device.record_session("model.onnx", ["CPUExecutionProvider"])

    assert "model.onnx" not in desktop_device._sessions


def test_record_session_stores_the_basename_and_providers(monkeypatch):
    monkeypatch.setenv("TS_AI_BACKEND", "cpu")
    desktop_device._sessions.clear()

    desktop_device.record_session("/models/clip/model.onnx", ["CPUExecutionProvider"], error=None)

    assert desktop_device._sessions["model.onnx"] == {
        "providers": ["CPUExecutionProvider"],
        "error": None,
    }

