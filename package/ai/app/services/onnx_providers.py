import functools
import logging
import os

logger = logging.getLogger("app.services.onnx_providers")

# 推理后端优先级：CUDA (gpu extra) > OpenVINO (openvino extra) > CPU (cpu extra)。
# 通过 ort.get_available_providers() 动态探测，避免硬编码导致未安装的 EP 报警告。
_PRIORITY = ["CUDAExecutionProvider", "OpenVINOExecutionProvider", "CPUExecutionProvider"]


def _openvino_device() -> str:
    """选择 OpenVINO EP 的 device_type：NPU 优先，否则 CPU。

    OPENVINO_DEVICE 环境变量可强制覆盖（设为 NPU / GPU / CPU）；留空时按
    openvino.Core().available_devices() 探测——有 NPU 走 NPU，否则回退 CPU，
    避免在无 NPU 的机器上指定 NPU 导致会话创建失败。
    """
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


@functools.lru_cache(maxsize=1)
def get_onnx_providers():
    """返回 (providers, provider_options)，按可用性筛选并保持优先级。

    结果在进程生命周期内缓存（可用 EP 不会变），避免每次加载模型都重复探测与打日志。

    provider_options 与 providers 一一对齐：
      - CUDAExecutionProvider     -> {"device_id": 0}
      - OpenVINOExecutionProvider -> {"device_type": "NPU" | "CPU"}（NPU 优先）
      - CPUExecutionProvider      -> {}
    """
    try:
        import onnxruntime as ort
        available = set(ort.get_available_providers())
    except Exception as e:
        logger.warning(f"Failed to probe onnxruntime providers, fallback to CPU: {e}")
        return ["CPUExecutionProvider"], [{}]

    providers = [p for p in _PRIORITY if p in available]
    if not providers:
        providers = ["CPUExecutionProvider"]

    options = []
    for p in providers:
        if p == "CUDAExecutionProvider":
            options.append({"device_id": 0})
        elif p == "OpenVINOExecutionProvider":
            options.append({"device_type": _openvino_device()})
        else:
            options.append({})

    logger.info(f"ONNX Runtime providers selected: {providers} with options {options}")
    return providers, options
