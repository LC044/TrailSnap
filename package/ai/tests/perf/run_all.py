"""串行压测全部 AI 接口，输出汇总对比报告。

每个接口用相同的并发度 / 每请求条数 / 总请求数依次跑一遍，
最后打印横向对比表并导出一份包含所有接口结果的 JSON 报告。

示例：
    python -m tests.perf.run_all -c 4 -k 2 -n 20 -o perf_report.json
    python -m tests.perf.run_all --only face,ocr -c 8 -n 30
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from .endpoints import ENDPOINTS, get_endpoint
from .runner import Summary, build_parser, run, write_report


async def run_all(args: argparse.Namespace) -> list[Summary]:
    keys = args.only.split(",") if args.only else [e.key for e in ENDPOINTS]
    summaries: list[Summary] = []
    for k in keys:
        ep = get_endpoint(k.strip())
        print(f"\n▶ 开始压测: {ep.name} ({ep.path})")
        s = await run(ep, args)
        summaries.append(s)
    return summaries


def print_comparison(summaries: list[Summary]) -> None:
    print("\n" + "=" * 92)
    print("  全部接口性能对比")
    print("=" * 92)
    header = f"  {'接口':<14}{'并发':>4}{'每请求':>6}{'总数':>6}{'成功':>6}{'失败':>6}{'RPS':>8}{'items/s':>10}{'p50(ms)':>9}{'p95(ms)':>9}"
    print(header)
    print("  " + "-" * 90)
    for s in summaries:
        lat = s.latency_ms_view()
        print(f"  {s.endpoint_name:<14}{s.concurrency:>4}{s.items_per_request:>6}"
              f"{s.total_requests:>6}{s.success:>6}{s.failed:>6}"
              f"{s.rps():>8.2f}{s.items_per_sec():>10.2f}"
              f"{lat['p50']:>9}{lat['p95']:>9}")
    print("=" * 92)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser("串行压测全部 AI 接口")
    parser.add_argument("--only", default="",
                        help="只跑指定接口，逗号分隔，如 face,ocr")
    args = parser.parse_args(argv)
    if args.requests <= 0 and args.duration <= 0:
        print("请指定 -n（总请求数）或 -d（持续秒数）")
        return 2

    summaries = asyncio.run(run_all(args))
    print_comparison(summaries)

    if args.output:
        # 复用 write_report，逐条追加到同一份 JSON
        first = True
        for s in summaries:
            write_report(args.output, s, append=not first)
            first = False
    return 0 if all(s.failed == 0 for s in summaries) else 1


if __name__ == "__main__":
    sys.exit(main())
