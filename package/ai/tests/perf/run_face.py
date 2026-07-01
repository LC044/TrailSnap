"""压测 AI 接口：人脸识别  POST /face/face-recognition

示例：
    python -m tests.perf.run_face -c 8 -k 4 -n 50
    python -m tests.perf.run_face -c 4 -d 30 --verbose
"""
import sys

from .endpoints import get_endpoint
from .runner import main_for

if __name__ == "__main__":
    sys.exit(main_for(get_endpoint("face")))
