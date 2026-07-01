"""压测 AI 接口：车票识别  POST /tickets/predict

示例：
    python -m tests.perf.run_tickets -c 2 -k 1 -n 20
"""
import sys

from .endpoints import get_endpoint
from .runner import main_for

if __name__ == "__main__":
    sys.exit(main_for(get_endpoint("tickets")))
