"""Nightly gap coverage for app/services/desktop_device.py.

The nightly coverage scan flagged three uncovered groups:

* ``prepare_cuda_libraries`` never registered the ``nvidia-*`` wheel ``bin``
  directories, so a CUDA-enabled install could not lazy-load cuDNN.
* the "provider fell back to CPU" guard was never triggered.
* the OpenVINO fallback in ``desktop_device`` did not survive a broken
  ``openvino`` installation (``Core()`` raising while listing devices).
"""

from __future__ import annotations

import importlib.util
import os
import sys
import types
from pathlib import Path

import pytest

from app.services import desktop_device as device

pytestmark = [pytest.mark.smoke, pytest.mark.module_desktop]


@pytest.fixture(autouse=True)
def _reset_module_state():
    """The module keeps process-wide state; every test starts from scratch."""
    device._dll_directories.clear()
    device.desktop_device.cache_clear()
    original_path = os.environ.get("PATH")
    yield
    device._dll_directories.clear()
    device.desktop_device.cache_clear()
    if original_path is None:
        os.environ.pop("PATH", None)
    else:
        os.environ["PATH"] = original_path


def test_prepare_cuda_libraries_registers_nvidia_bin_directories(tmp_path, monkeypatch):
    """Every ``nvidia-*`` wheel contributes its ``bin`` directory to the DLL path."""
    package_root = tmp_path / "cuda_runtime"
    binary_directory = package_root / "bin"
    binary_directory.mkdir(parents=True)

    def fake_find_spec(name, *args, **kwargs):
        if name == "nvidia.cuda_runtime":
            return types.SimpleNamespace(submodule_search_locations=[str(package_root)])
        return None

    monkeypatch.setattr(importlib.util, "find_spec", fake_find_spec)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(device.os, "add_dll_directory", lambda path: path, raising=False)

    device.prepare_cuda_libraries()

    assert device._dll_directories == [str(binary_directory)]
    assert os.environ["PATH"].startswith(str(binary_directory) + os.pathsep)


def test_prepare_cuda_libraries_survives_a_broken_nvidia_spec(monkeypatch):
    """``find_spec`` raising for a missing wheel must not abort the probe."""
    def exploding_find_spec(name, *args, **kwargs):
        if name.startswith("nvidia."):
            raise ImportError(name)
        return None

    monkeypatch.setattr(importlib.util, "find_spec", exploding_find_spec)
    monkeypatch.setattr(sys, "platform", "win32")
    device.prepare_cuda_libraries()
    assert device._dll_directories == []


def test_record_session_and_runtime_status(monkeypatch):
    """Recorded sessions are reported by ``runtime_status``."""
    monkeypatch.setenv("TS_AI_BACKEND", "cpu")
    device.record_session("clip-ViT-B-32", ["CPUExecutionProvider"])
    status = device.runtime_status()
    assert status["backend"] == "cpu"
    assert status["models"]["clip-ViT-B-32"]["providers"] == ["CPUExecutionProvider"]
    assert status["models"]["clip-ViT-B-32"]["error"] is None


def test_prepare_cuda_libraries_is_a_noop_without_nvidia_wheels(tmp_path, monkeypatch):
    """A machine without the CUDA extra must not crash the probe."""
    monkeypatch.setattr(importlib.util, "find_spec", lambda name, *a, **k: None)
    monkeypatch.setattr(sys, "platform", "win32")
    device.prepare_cuda_libraries()
    assert device._dll_directories == []


def test_probe_raises_when_the_provider_falls_back_to_cpu(monkeypatch):
    """A session that reports only the CPU provider is rejected."""
    import onnxruntime

    class FakeSession:
        def __init__(self, *args, **kwargs):
            pass

        def disable_fallback(self):
            pass

        def get_providers(self):
            return ["CPUExecutionProvider"]

    monkeypatch.setattr(onnxruntime, "get_available_providers", lambda: ["CUDAExecutionProvider"])
    monkeypatch.setattr(onnxruntime, "InferenceSession", FakeSession)
    if hasattr(onnxruntime, "preload_dlls"):
        monkeypatch.setattr(onnxruntime, "preload_dlls", lambda: None)
    monkeypatch.setenv("TS_AI_BACKEND", "cuda")
    monkeypatch.setenv("OPENVINO_DEVICE", "CPU")

    with pytest.raises(RuntimeError, match="回退 CPU"):
        device.probe_device("cuda", "CPU")


def test_desktop_device_survives_a_broken_openvino_installation(monkeypatch):
    """``Core()`` failing while listing devices is swallowed on the fallback path."""
    broken = types.ModuleType("openvino")

    def broken_core(*args, **kwargs):
        raise RuntimeError("openvino runtime is broken")

    broken.Core = broken_core
    monkeypatch.setitem(sys.modules, "openvino", broken)
    monkeypatch.setenv("TS_AI_BACKEND", "openvino")
    monkeypatch.setenv("OPENVINO_DEVICE", "CPU")

    result = device.desktop_device()

    assert result["backend"] == "cpu"
    assert result["provider"] == "CPUExecutionProvider"
    assert result["devices"] == []
    assert result["error"]


def test_desktop_device_reports_a_broken_cpu_runtime(monkeypatch):
    """A failing CPU probe is reported as a hard error instead of a silent fallback."""
    monkeypatch.setenv("TS_AI_BACKEND", "cpu")

    def broken_probe(backend, dev):
        raise RuntimeError("onnxruntime is broken")

    monkeypatch.setattr(device, "probe_device", broken_probe)
    with pytest.raises(RuntimeError, match="CPU 推理验证失败"):
        device.desktop_device()
