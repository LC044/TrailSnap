"""Run real AI inference with the benchmark's explicit ONNX thread policy.

InsightFace creates its own sessions, bypassing the application's ONNX factory.
Supply the same SessionOptions so all measured inference honours the policy.
No inference results or business handlers are replaced.
"""
import sys

sys.path.insert(0, "/app")

from app.core.runtime_limits import configure_inference_runtime

configure_inference_runtime()

from insightface.model_zoo import model_zoo
import uvicorn
from app.services.onnx_providers import get_session_options

OriginalSession = model_zoo.PickableInferenceSession


class BenchmarkInferenceSession(OriginalSession):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("sess_options", get_session_options())
        super().__init__(*args, **kwargs)


# InsightFace's get_model forwards providers but discards sess_options.
# Apply the policy at the session constructor that its ModelRouter uses.
model_zoo.PickableInferenceSession = BenchmarkInferenceSession
uvicorn.run("main:app", host="0.0.0.0", port=8001)
