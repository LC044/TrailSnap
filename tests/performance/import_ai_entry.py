"""Run real AI inference with the benchmark's explicit ONNX thread policy.

InsightFace creates its own sessions, bypassing the application's ONNX factory.
Supply the same SessionOptions so all measured inference honours the policy.
No inference results or business handlers are replaced.
"""
import sys

sys.path.insert(0, "/app")

from app.core.runtime_limits import configure_inference_runtime

configure_inference_runtime()

import insightface.app
import uvicorn
from app.services.onnx_providers import get_session_options

OriginalFaceAnalysis = insightface.app.FaceAnalysis


class BenchmarkFaceAnalysis(OriginalFaceAnalysis):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("sess_options", get_session_options())
        super().__init__(*args, **kwargs)


insightface.app.FaceAnalysis = BenchmarkFaceAnalysis
uvicorn.run("main:app", host="0.0.0.0", port=8001)
