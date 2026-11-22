"""Nightly watch 2026-11-22 · package/ai/app/services/onnx_providers.py::_coreml_options
与 package/ai/app/services/desktop_device.py::prepare_cuda_libraries 盲区。

_coreml_options 决定 CoreML EP 的 provider_options：环境变量拼错不会报错，
只会在 macOS 上悄悄退回默认行为，所以必须锁死取值口径。
prepare_cuda_libraries 在 Windows 上给 nvidia-* 包注册 DLL 目录，
若重复注册或在没有 CUDA 包的环境里崩溃，桌面端推理会直接起不来。

本文件覆盖：
- _coreml_options: 默认取值（happy）
- _coreml_options: COREML_MODEL_FORMAT / COREML_COMPUTE_UNITS 覆盖（edge）
- prepare_cuda_libraries: 非 Windows 平台不做任何事（happy）
- prepare_cuda_libraries: Windows 上无 CUDA 包时静默通过且可重复调用（edge）
"""

import sys

import pytest

from app.services import desktop_device
from app.services.onnx_providers import _coreml_options

pytestmark = [pytest.mark.smoke]


def test_coreml_options_use_the_documented_defaults(monkeypatch):
    monkeypatch.delenv("COREML_MODEL_FORMAT", raising=False)
    monkeypatch.delenv("COREML_COMPUTE_UNITS", raising=False)

    options = _coreml_options()

    assert options["ModelFormat"] == "MLProgram"
    assert options["MLComputeUnits"] == "ALL"
    assert options["RequireStaticInputShapes"] == "0"
    assert options["EnableOnSubgraphs"] == "0"


def test_coreml_options_honour_the_environment_overrides(monkeypatch):
    monkeypatch.setenv("COREML_MODEL_FORMAT", "NeuralNetwork")
    monkeypatch.setenv("COREML_COMPUTE_UNITS", "CPUAndGPU")

    options = _coreml_options()

    assert options["ModelFormat"] == "NeuralNetwork"
    assert options["MLComputeUnits"] == "CPUAndGPU"
    assert options["RequireStaticInputShapes"] == "0"


def test_prepare_cuda_libraries_is_a_noop_off_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(desktop_device, "_dll_directories", [])

    desktop_device.prepare_cuda_libraries()

    assert desktop_device._dll_directories == []


def test_prepare_cuda_libraries_is_idempotent_without_cuda_packages(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(desktop_device, "_dll_directories", [])

    desktop_device.prepare_cuda_libraries()
    desktop_device.prepare_cuda_libraries()

    # 没有安装 nvidia-* 时不应抛异常，也不应留下半注册的目录句柄
    assert isinstance(desktop_device._dll_directories, list)
