"""Nightly watch 2026-11-26 · package/ai/app/services/desktop_device.py 的 CUDA DLL 与回退盲区。

2026-11-22 的补测已经覆盖了设备探测的主流程（nvidia-smi 取名、OpenVINO 设备列表、
加速器失败回退 CPU、CPU 失败抛错），但覆盖率报告里仍有三段分支没有跑到：

- ``prepare_cuda_libraries``：Windows 上按 nvidia-* wheel 找出 bin 目录并注册 DLL 目录，
  同时把该目录前置到 PATH（cuDNN 惰性编译 NVRTC 时走 LoadLibrary，只认 PATH）。
  缺 wheel 的机器必须安静跳过，不能让探测崩掉。
- ``probe_device``：nvidia-smi 存在但返回非零退出码（或空输出）时，设备名退回
  「NVIDIA GPU 0」，探测本身仍然算成功。
- ``desktop_device``：OpenVINO 探测失败后回退 CPU 时，若连 Core() 都建不起来，
  设备列表必须留空而不是再抛一次异常。

本文件覆盖：
- Windows 上找到 nvidia wheel 时注册 DLL 目录并前置 PATH（happy）
- find_spec 抛 ModuleNotFoundError 时安静跳过（edge）
- nvidia-smi 返回非零退出码时退回默认设备名（edge）
- OpenVINO 回退时 Core() 失败也不抛异常（error）
"""

import importlib.util
import os
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
        self.providers = list(providers or [])

    def disable_fallback(self):
        pass

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


@pytest.fixture(autouse=True)
def _reset_cuda_state():
    desktop_device.desktop_device.cache_clear()
    desktop_device._dll_directories.clear()
    yield
    desktop_device.desktop_device.cache_clear()
    desktop_device._dll_directories.clear()


def test_prepare_cuda_libraries_registers_the_wheel_bin_directory(tmp_path, monkeypatch):
    package_dir = tmp_path / "nvidia" / "cudnn"
    bin_dir = package_dir / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "cudnn_ops64_9.dll").write_bytes(b"stub")

    class _Spec:
        submodule_search_locations = [str(package_dir)]

    monkeypatch.setattr(sys, "platform", "win32")
    # 只有 cudnn 这个 wheel 装了，其余 nvidia-* 包一律缺失。
    monkeypatch.setattr(
        importlib.util, "find_spec",
        lambda name: _Spec() if name == "nvidia.cudnn" else None)
    monkeypatch.setattr(os, "add_dll_directory", lambda path: f"handle:{path}", raising=False)
    monkeypatch.setenv("PATH", "original-path")

    desktop_device.prepare_cuda_libraries()

    assert desktop_device._dll_directories == [f"handle:{bin_dir}"]
    assert os.environ["PATH"].startswith(str(bin_dir))
    assert "original-path" in os.environ["PATH"]


def test_prepare_cuda_libraries_skips_a_machine_without_the_nvidia_wheels(monkeypatch):
    def _missing(name):
        raise ModuleNotFoundError(f"No module named {name!r}")

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(importlib.util, "find_spec", _missing)

    desktop_device.prepare_cuda_libraries()

    assert desktop_device._dll_directories == []


def test_cuda_probe_falls_back_when_nvidia_smi_reports_a_failure(monkeypatch):
    monkeypatch.setitem(sys.modules, "onnxruntime", _fake_onnxruntime())

    class _Result:
        returncode = 9
        stdout = ""

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: _Result())

    result = desktop_device.probe_device("cuda", "0")

    assert result["provider"] == "CUDAExecutionProvider"
    assert result["deviceName"] == "NVIDIA GPU 0"
    assert result["error"] is None


def test_desktop_device_keeps_an_empty_device_list_when_openvino_cannot_start(monkeypatch):
    monkeypatch.setenv("TS_AI_BACKEND", "openvino")
    monkeypatch.setattr(
        desktop_device, "probe_device",
        lambda backend, device: (_ for _ in ()).throw(RuntimeError("probe failed")))

    def _broken_core():
        raise RuntimeError("openvino runtime is broken")

    module = types.ModuleType("openvino")
    module.Core = _broken_core
    monkeypatch.setitem(sys.modules, "openvino", module)

    result = desktop_device.desktop_device()

    assert result["backend"] == "cpu"
    assert result["provider"] == "CPUExecutionProvider"
    assert result["error"] == "probe failed"
    assert result["devices"] == []

