import functools
import logging
import os
import platform
import subprocess

logger = logging.getLogger("app.services.onnx_providers")

# EP 优先级：CUDA > OpenVINO > CoreML（仅 Apple Silicon）> CPU。
_PRIORITY = [
    "CUDAExecutionProvider",
    "OpenVINOExecutionProvider",
    "CoreMLExecutionProvider",
    "CPUExecutionProvider",
]


def _is_apple_silicon() -> bool:
    """当前进程是否运行在 Apple Silicon（arm64 macOS）上。"""
    return platform.system() == "Darwin" and platform.machine() == "arm64"


def _openvino_device() -> str:
    """OpenVINO device_type：OPENVINO_DEVICE 覆盖 > 探测到 NPU > CPU。"""
    override = os.getenv("OPENVINO_DEVICE", "").strip()
    if override:
        return override
    try:
        from openvino import Core
        devices = set(Core().available_devices)
        if "NPU" in devices:
            return "NPU"
    except Exception as e:
        logger.warning(f"Failed to probe OpenVINO devices, fallback to CPU: {e}")
    return "CPU"


def _coreml_options() -> dict:
    """CoreML EP provider_options。可用环境变量 COREML_MODEL_FORMAT / COREML_COMPUTE_UNITS 覆盖。"""
    return {
        "ModelFormat": os.getenv("COREML_MODEL_FORMAT", "MLProgram"),
        "MLComputeUnits": os.getenv("COREML_COMPUTE_UNITS", "ALL"),
        "RequireStaticInputShapes": "0",
        "EnableOnSubgraphs": "0",
    }


@functools.lru_cache(maxsize=1)
def get_onnx_providers():
    """返回 (providers, provider_options)，按可用性筛选并保持优先级。DISABLE_COREML=1 可强制禁用 CoreML。"""
    try:
        import onnxruntime as ort
        available = set(ort.get_available_providers())
    except Exception as e:
        logger.warning(f"Failed to probe onnxruntime providers, fallback to CPU: {e}")
        return ["CPUExecutionProvider"], [{}]

    if os.getenv("DISABLE_COREML", "").strip() in ("1", "true", "TRUE", "yes"):
        available.discard("CoreMLExecutionProvider")
        logger.info("DISABLE_COREML=1 detected, CoreMLExecutionProvider skipped.")

    # CoreML 仅在 Apple Silicon 启用；Intel Mac 的 CoreML 实测慢于 CPU，显式剔除。
    if not _is_apple_silicon() and "CoreMLExecutionProvider" in available:
        available.discard("CoreMLExecutionProvider")
        logger.info("Non-Apple-Silicon platform: CoreMLExecutionProvider disabled.")

    providers = [p for p in _PRIORITY if p in available]
    if not providers:
        providers = ["CPUExecutionProvider"]

    options = []
    for p in providers:
        if p == "CUDAExecutionProvider":
            options.append({"device_id": 0})
        elif p == "OpenVINOExecutionProvider":
            options.append({"device_type": _openvino_device()})
        elif p == "CoreMLExecutionProvider":
            options.append(_coreml_options())
        else:
            options.append({})

    logger.info(f"ONNX Runtime providers selected: {providers} with options {options}")
    return providers, options


def _detect_apple_perf_cores() -> int:
    """读 Apple Silicon 的 P-core 物理数（避免 E-core 拖慢推理），失败回退 os.cpu_count()。"""
    try:
        out = subprocess.run(
            ["sysctl", "-n", "hw.perflevel0.physicalcpu"],
            capture_output=True, text=True, timeout=1.0,
        )
        n = int(out.stdout.strip())
        if n > 0:
            return n
    except Exception as e:
        logger.debug(f"detect perf cores via sysctl failed: {e}")
    return max(1, os.cpu_count() or 1)

@functools.lru_cache(maxsize=1)
def get_session_options():
    """Apple Silicon 专用 SessionOptions（图优化 + P-core 线程 + SEQUENTIAL）；其它平台返回 None。

    ORT_INTRA_OP_THREADS 可覆盖 intra_op 线程数（仅 Apple Silicon 生效）。
    """
    if not _is_apple_silicon():
        logger.info("Non-Apple-Silicon platform: using ONNX Runtime default SessionOptions.")
        return None

    import onnxruntime as ort

    so = ort.SessionOptions()
    so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

    override = os.getenv("ORT_INTRA_OP_THREADS", "").strip()
    if override.isdigit() and int(override) > 0:
        intra = int(override)
    else:
        intra = _detect_apple_perf_cores()

    so.intra_op_num_threads = intra
    so.inter_op_num_threads = 1
    so.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL

    logger.info(
        f"Apple Silicon ONNX Runtime SessionOptions: graph_opt=ORT_ENABLE_ALL, "
        f"intra_op_threads={intra}, inter_op_threads=1, mode=SEQUENTIAL"
    )
    return so


# CoreML 创建失败的 model_path 黑名单，下次直接 CPU-only
_coreml_blacklist: set[str] = set()


def _make_session(model_path, sess_options, providers, provider_options):
    """sess_options 为 None 时不传该 kwarg，保持 ORT 默认行为。"""
    import onnxruntime as ort
    if sess_options is None:
        return ort.InferenceSession(
            model_path, providers=providers, provider_options=provider_options,
        )
    return ort.InferenceSession(
        model_path, sess_options=sess_options,
        providers=providers, provider_options=provider_options,
    )

def create_inference_session(model_path: str, sess_options=None):
    """创建 ort.InferenceSession，带 CoreML 创建失败 → CPU-only 降级。"""
    so = sess_options if sess_options is not None else get_session_options()

    if model_path in _coreml_blacklist:
        logger.info(f"[{model_path}] previously failed on CoreML, using CPU-only.")
        return _make_session(model_path, so, ["CPUExecutionProvider"], [{}])

    providers, provider_options = get_onnx_providers()

    if "CoreMLExecutionProvider" not in providers:
        return _make_session(model_path, so, providers, provider_options)

    try:
        return _make_session(model_path, so, providers, provider_options)
    except Exception as e:
        _coreml_blacklist.add(model_path)
        logger.warning(
            f"[{model_path}] CoreML session creation failed, falling back to CPU. "
            f"Cause: {type(e).__name__}: {str(e)[:200]}"
        )
        return _make_session(model_path, so, ["CPUExecutionProvider"], [{}])
