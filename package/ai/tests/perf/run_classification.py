"""压测 AI 接口：图像分类  POST /classification/

示例：
    python -m tests.perf.run_classification -c 4 -k 8 -n 30
"""
import sys

from .endpoints import get_endpoint
from .runner import main_for

if __name__ == "__main__":
    sys.exit(main_for(get_endpoint("classification")))
