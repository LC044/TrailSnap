"""Run real AI inference with the benchmark's explicit ONNX thread policy.

InsightFace and RapidOCR create sessions outside the application's ONNX factory.
Bound their thread pools too, preserving all other supplied session options.
No inference results or business handlers are replaced.
"""
import sys

sys.path.insert(0, "/app")

from app.core.runtime_limits import configure_inference_runtime

configure_inference_runtime()

import onnxruntime as ort
import uvicorn
from app.services.onnx_providers import get_session_options

OriginalSession = ort.InferenceSession


class BenchmarkInferenceSession(OriginalSession):
    def __init__(self, path_or_bytes, sess_options=None, *args, **kwargs):
        options = sess_options if sess_options is not None else get_session_options()
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        super().__init__(path_or_bytes, options, *args, **kwargs)


# Install before uvicorn imports the real app and its inference libraries.
ort.InferenceSession = BenchmarkInferenceSession
uvicorn.run("main:app", host="0.0.0.0", port=8001)
