"""压测 AI 接口：情绪色彩提取  POST /emotion/

示例：
    python -m tests.perf.run_emotion -c 4 -k 4 -n 30
"""
import sys

from .endpoints import get_endpoint
from .runner import main_for

if __name__ == "__main__":
    sys.exit(main_for(get_endpoint("emotion")))
