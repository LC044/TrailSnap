"""Probe the requested desktop device with real inference, before loading models."""
import functools
import os
import subprocess
import sys
import threading

_lock = threading.Lock()
_sessions: dict[str, dict] = {}
_dll_directories = []


def prepare_cuda_libraries():
    """cuDNN loads NVRTC lazily; keep package DLL directories alive as well."""
    if sys.platform == "win32" and not _dll_directories:
        from importlib.util import find_spec
        for package in ("cuda_runtime", "cublas", "cudnn", "cuda_nvrtc", "cufft", "curand", "nvjitlink"):
            # The nvidia-* wheels only ship with the desktop-cuda extra; a machine
            # without them must not crash the probe, it simply has no CUDA DLLs.
            try:
                spec = find_spec(f"nvidia.{package}")
            except (ImportError, ModuleNotFoundError, ValueError):
                spec = None
            if spec is not None:
                from pathlib import Path
                for location in spec.submodule_search_locations or []:
                    directory = Path(location) / "bin"
                    if directory.is_dir():
                        _dll_directories.append(os.add_dll_directory(str(directory)))
                        # cuDNN also uses LoadLibrary directly for lazy NVRTC
                        # compilation, which searches this process's PATH.
                        os.environ["PATH"] = str(directory) + os.pathsep + os.environ.get("PATH", "")


def probe_device(backend: str, device: str) -> dict:
    import numpy as np
    if backend == "openvino":
        # Import registers OpenVINO's DLL directory on Windows before ORT
        # resolves its provider library.
        from openvino import Core
        core = Core()
    import onnxruntime as ort
    from onnx import TensorProto, helper

    provider = {"cpu": "CPUExecutionProvider", "cuda": "CUDAExecutionProvider",
                "openvino": "OpenVINOExecutionProvider"}[backend]
    if backend == "cuda" and hasattr(ort, "preload_dlls"):
        prepare_cuda_libraries()
        ort.preload_dlls()
    if provider not in ort.get_available_providers():
        raise RuntimeError(f"当前运行时不支持 {provider}")
    options = {"device_type": device} if backend == "openvino" else {"device_id": 0} if backend == "cuda" else {}
    # A real convolution also validates cuDNN, which a MatMul-only check cannot.
    graph = helper.make_graph(
        [helper.make_node("Conv", ["x", "w"], ["z"], kernel_shape=[3, 3])], "device-check",
        [helper.make_tensor_value_info("x", TensorProto.FLOAT, [1, 3, 8, 8]),
         helper.make_tensor_value_info("w", TensorProto.FLOAT, [2, 3, 3, 3])],
        [helper.make_tensor_value_info("z", TensorProto.FLOAT, [1, 2, 6, 6])],
    )
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)], ir_version=9)
    so = ort.SessionOptions()
    if backend != "cpu":
        so.add_session_config_entry("session.disable_cpu_ep_fallback", "1")
    session = ort.InferenceSession(model.SerializeToString(), sess_options=so,
                                  providers=[provider], provider_options=[options])
    session.disable_fallback()
    if provider not in session.get_providers():
        raise RuntimeError(f"{provider} 初始化失败，已回退 CPU")
    inputs = {"x": np.ones((1, 3, 8, 8), dtype=np.float32),
              "w": np.ones((2, 3, 3, 3), dtype=np.float32)}
    np.testing.assert_allclose(session.run(None, inputs)[0], np.full((1, 2, 6, 6), 27, dtype=np.float32))
    devices = []
    label = "CPU" if backend == "cpu" else "NVIDIA GPU 0"
    if backend == "cuda":
        try:
            result = subprocess.run(["nvidia-smi", "--query-gpu=name", "--id=0", "--format=csv,noheader"],
                                    capture_output=True, text=True, timeout=3,
                                    creationflags=0x08000000 if sys.platform == "win32" else 0)
            if result.returncode == 0 and result.stdout.strip():
                label = result.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            pass
    if backend == "openvino":
        devices = [{"id": d, "name": core.get_property(d, "FULL_DEVICE_NAME")} for d in core.available_devices]
        label = next((d["name"] for d in devices if d["id"] == device), device)
    return {"backend": backend, "device": device if backend == "openvino" else "0" if backend == "cuda" else "CPU",
            "deviceName": label, "provider": provider, "devices": devices, "error": None}


@functools.lru_cache(maxsize=1)
def desktop_device() -> dict:
    backend = os.environ.get("TS_AI_BACKEND", "cpu")
    device = os.environ.get("OPENVINO_DEVICE", "CPU")
    try:
        return probe_device(backend, device)
    except Exception as error:
        if backend == "cpu":
            raise RuntimeError(f"CPU 推理验证失败：{error}") from error
        result = {"backend": "cpu", "device": "CPU", "deviceName": "CPU",
                  "provider": "CPUExecutionProvider", "devices": [], "error": str(error)}
        # Still list Intel devices when the selected device failed its probe.
        if backend == "openvino":
            try:
                from openvino import Core
                core = Core()
                result["devices"] = [{"id": d, "name": core.get_property(d, "FULL_DEVICE_NAME")} for d in core.available_devices]
            except Exception:
                pass
        return result


def record_session(model: str, providers: list[str], error: str | None = None):
    if "TS_AI_BACKEND" in os.environ:
        with _lock:
            _sessions[os.path.basename(str(model))] = {"providers": providers, "error": error}


def runtime_status() -> dict:
    with _lock:
        return {**desktop_device(), "models": dict(_sessions)}
