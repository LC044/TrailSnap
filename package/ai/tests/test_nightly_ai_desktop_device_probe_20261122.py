"""Nightly watch 2026-11-22 · package/ai/app/services/desktop_device.py 的设备探测盲区。

AI 桌面端在加载模型前会做一次真实推理探测（``probe_device``），用来确认
CUDA / OpenVINO 真的能用，而不是退回到 CPU 还对外宣称「GPU 0」。
探测结果里的设备名与设备列表会直接展示在客户端上，因此：

- CUDA 探测成功时，设备名应来自 nvidia-smi 的真实输出；
- nvidia-smi 不可用时，设备名退回「NVIDIA GPU 0」，但探测仍然成功；
- OpenVINO 探测要列出全部设备，并按请求的设备号给出名称；
- 加速器探测失败时回退到 CPU 并带上错误原因；CPU 探测失败则必须抛错。

本文件覆盖：
- CUDA 设备名取自 nvidia-smi（happy）
- nvidia-smi 失败时退回默认设备名（edge）
- OpenVINO 设备列表与设备名（happy）
- OpenVINO 请求了不存在的设备号时按设备号兜底（edge）
- 加速器探测失败时回退 CPU 并保留错误原因（edge）
- CPU 探测失败时抛出 RuntimeError（error）
"""

import subprocess
import sys
import types

import numpy as np
import pytest

from app.services import desktop_device

pytestmark = [pytest.mark.smoke]


class _FakeSessionOptions:
    def __init__(self):
        self.entries = {}

    def add_session_config_entry(self, key, value):
        self.entries[key] = value


class _FakeSession:
    def __init__(self, model_bytes, sess_options=None, providers=None, provider_options=None):
        self.sess_options = sess_options
        self.providers = list(providers or [])
        self.provider_options = list(provider_options or [])
        self.fallback_disabled = False

    def disable_fallback(self):
        self.fallback_disabled = True

    def get_providers(self):
        return list(self.providers)

    def run(self, output_names, inputs):
        return [np.full((1, 2, 6, 6), 27, dtype=np.float32)]


def _fake_onnxruntime():
    module = types.ModuleType("onnxruntime")
    module.SessionOptions = _FakeSessionOptions
    module.InferenceSession = _FakeSession
    module.get_available_providers = lambda: [
        "CPUExecutionProvider", "CUDAExecutionProvider", "OpenVINOExecutionProvider"]
    module.preload_dlls = lambda: None
    return module


def _fake_openvino(devices=("0",), name="Intel(R) Core(TM) i9-13900K CPU"):
    class Core:
        def __init__(self):
            self.available_devices = list(devices)

        def get_property(self, device, key):
            return name

    module = types.ModuleType("openvino")
    module.Core = Core
    return module


@pytest.fixture(autouse=True)
def _clear_desktop_device_cache():
    desktop_device.desktop_device.cache_clear()
    yield
    desktop_device.desktop_device.cache_clear()


def test_cuda_probe_uses_the_gpu_name_reported_by_nvidia_smi(monkeypatch):
    monkeypatch.setitem(sys.modules, "onnxruntime", _fake_onnxruntime())

    class _Result:
        returncode = 0
        stdout = "NVIDIA GeForce RTX 4090\n"

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: _Result())

    result = desktop_device.probe_device("cuda", "0")

    assert result["provider"] == "CUDAExecutionProvider"
    assert result["device"] == "0"
    assert result["deviceName"] == "NVIDIA GeForce RTX 4090"
    assert result["error"] is None


def test_cuda_probe_falls_back_to_the_default_device_name(monkeypatch):
    monkeypatch.setitem(sys.modules, "onnxruntime", _fake_onnxruntime())

    def _boom(*args, **kwargs):
        raise OSError("nvidia-smi not found")

    monkeypatch.setattr(subprocess, "run", _boom)

    result = desktop_device.probe_device("cuda", "0")

    assert result["deviceName"] == "NVIDIA GPU 0"
    assert result["provider"] == "CUDAExecutionProvider"


def test_openvino_probe_lists_devices_and_names_the_requested_one(monkeypatch):
    monkeypatch.setitem(sys.modules, "onnxruntime", _fake_onnxruntime())
    monkeypatch.setitem(sys.modules, "openvino", _fake_openvino())

    result = desktop_device.probe_device("openvino", "0")

    assert result["provider"] == "OpenVINOExecutionProvider"
    assert result["devices"] == [{"id": "0", "name": "Intel(R) Core(TM) i9-13900K CPU"}]
    assert result["deviceName"] == "Intel(R) Core(TM) i9-13900K CPU"


def test_openvino_probe_falls_back_to_the_device_id_when_it_is_unknown(monkeypatch):
    monkeypatch.setitem(sys.modules, "onnxruntime", _fake_onnxruntime())
    monkeypatch.setitem(sys.modules, "openvino", _fake_openvino())

    result = desktop_device.probe_device("openvino", "7")

    assert result["deviceName"] == "7"
    assert result["device"] == "7"


def test_desktop_device_falls_back_to_cpu_when_the_accelerator_probe_fails(monkeypatch):
    monkeypatch.setenv("TS_AI_BACKEND", "openvino")
    monkeypatch.setattr(desktop_device, "probe_device", lambda backend, device: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setitem(sys.modules, "openvino", _fake_openvino())

    result = desktop_device.desktop_device()

    assert result["backend"] == "cpu"
    assert result["provider"] == "CPUExecutionProvider"
    assert result["error"] == "boom"
    assert result["devices"] == [{"id": "0", "name": "Intel(R) Core(TM) i9-13900K CPU"}]


def test_desktop_device_raises_when_the_cpu_probe_fails(monkeypatch):
    monkeypatch.setenv("TS_AI_BACKEND", "cpu")
    monkeypatch.setattr(desktop_device, "probe_device", lambda backend, device: (_ for _ in ()).throw(RuntimeError("boom")))

    with pytest.raises(RuntimeError) as error:
        desktop_device.desktop_device()

    assert "CPU 推理验证失败" in str(error.value)
