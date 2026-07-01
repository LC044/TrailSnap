"""压测 AI 接口：文本向量(CLIP)  POST /embedding/text

该接口不依赖图片，使用内置样本文本，每请求取 K 条。
示例：
    python -m tests.perf.run_embedding_text -c 8 -k 4 -n 100
"""
import sys

from .endpoints import get_endpoint
from .runner import main_for

if __name__ == "__main__":
    sys.exit(main_for(get_endpoint("embedding-text")))
