"""压测 AI 接口：OCR 文字识别  POST /ocr/predict

示例：
    python -m tests.perf.run_ocr -c 4 -k 2 -n 30
"""
import sys

from .endpoints import get_endpoint
from .runner import main_for

if __name__ == "__main__":
    sys.exit(main_for(get_endpoint("ocr")))
