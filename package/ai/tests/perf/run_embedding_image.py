"""压测 AI 接口：图像向量(CLIP)  POST /embedding/image

示例：
    python -m tests.perf.run_embedding_image -c 4 -k 8 -n 40
"""
import sys

from .endpoints import get_endpoint
from .runner import main_for

if __name__ == "__main__":
    sys.exit(main_for(get_endpoint("embedding-image")))
