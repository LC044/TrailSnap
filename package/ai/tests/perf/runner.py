"""AI 微服务接口压测共享引擎。

职责：
- 解析通用 CLI 参数（并发度、每请求条数、总请求数 / 持续时长、图片目录等）；
- 预加载图片为 base64（images 接口）或样本文本（texts 接口）；
- 用 httpx.AsyncClient + asyncio.Semaphore 以固定并发度发起请求；
- 采集每次请求的延迟、状态码、成功与否，汇总 RPS / 吞吐 / 分位延迟；
- 打印表格并可选导出 JSON 报告。

每个接口的入口脚本只需：from .runner import build_parser, run；run(endpoint)。
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import httpx

from .endpoints import Endpoint, SAMPLE_TEXTS

# 默认图片目录：AI 服务 output/ 下有大量 face crop png，开箱可用。
_DEFAULT_IMAGES_DIR = Path(__file__).resolve().parents[2] / "output"
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


# ----------------------------- 数据结构 -----------------------------

@dataclass
class RequestResult:
    ok: bool
    status: int
    elapsed: float          # 秒
    items: int              # 本请求携带的图片/文本数
    error: str = ""


@dataclass
class Summary:
    endpoint_key: str
    endpoint_name: str
    path: str
    base_url: str
    concurrency: int
    items_per_request: int
    total_requests: int = 0
    success: int = 0
    failed: int = 0
    total_items: int = 0
    wall_seconds: float = 0.0
    latencies: list[float] = field(default_factory=list)
    errors: dict[str, int] = field(default_factory=dict)

    def add(self, r: RequestResult) -> None:
        self.total_requests += 1
        self.total_items += r.items
        if r.ok:
            self.success += 1
            self.latencies.append(r.elapsed)
        else:
            self.failed += 1
            tag = f"{r.status} {r.error}".strip() or "unknown"
            self.errors[tag] = self.errors.get(tag, 0) + 1

    def percentile(self, p: float) -> float:
        if not self.latencies:
            return 0.0
        if len(self.latencies) == 1:
            return self.latencies[0]
        qs = statistics.quantiles(self.latencies, n=100, method="inclusive")
        return qs[max(0, min(99, int(p) - 1))]

    def rps(self) -> float:
        return self.total_requests / self.wall_seconds if self.wall_seconds > 0 else 0.0

    def items_per_sec(self) -> float:
        return self.total_items / self.wall_seconds if self.wall_seconds > 0 else 0.0

    def latency_ms_view(self) -> dict:
        lat = self.latencies
        return {
            "min": round(min(lat) * 1000, 2) if lat else 0,
            "mean": round(statistics.mean(lat) * 1000, 2) if lat else 0,
            "p50": round(self.percentile(50) * 1000, 2),
            "p95": round(self.percentile(95) * 1000, 2),
            "p99": round(self.percentile(99) * 1000, 2),
            "max": round(max(lat) * 1000, 2) if lat else 0,
        }

    def to_dict(self) -> dict:
        return {
            "endpoint": self.endpoint_key,
            "name": self.endpoint_name,
            "path": self.path,
            "base_url": self.base_url,
            "concurrency": self.concurrency,
            "items_per_request": self.items_per_request,
            "total_requests": self.total_requests,
            "success": self.success,
            "failed": self.failed,
            "total_items": self.total_items,
            "wall_seconds": round(self.wall_seconds, 3),
            "rps": round(self.rps(), 3),
            "items_per_sec": round(self.items_per_sec(), 3),
            "latency_ms": self.latency_ms_view(),
            "errors": self.errors,
        }


# ----------------------------- 载荷准备 -----------------------------

def load_images(images_dir: Path, limit: int = 0) -> list[str]:
    """递归扫描目录，返回 base64 编码的图片列表。limit=0 表示不限制。"""
    if not images_dir.exists():
        raise FileNotFoundError(f"图片目录不存在: {images_dir}")
    paths = sorted(
        p for p in images_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in _IMAGE_EXTS
    )
    if not paths:
        raise FileNotFoundError(f"图片目录中没有图片: {images_dir}")
    if limit > 0:
        paths = paths[:limit]
    encoded: list[str] = []
    for p in paths:
        with open(p, "rb") as f:
            encoded.append(base64.b64encode(f.read()).decode("ascii"))
    return encoded


def build_payload(kind: str, pool: list[str], k: int, seq: int) -> dict:
    """从 pool 中按序循环取 k 条构造请求体。seq 为请求序号，保证可复现。"""
    if not pool:
        raise ValueError("载荷池为空")
    items = [pool[(seq * k + i) % len(pool)] for i in range(k)]
    if kind == "images":
        return {"images": items}
    if kind == "texts":
        return {"texts": items}
    raise ValueError(f"未知 payload_kind: {kind}")


# ----------------------------- 压测主循环 -----------------------------

async def _probe(client: httpx.AsyncClient, endpoint: Endpoint, payload: dict, timeout: float) -> RequestResult:
    t0 = time.perf_counter()
    items = len(payload.get("images") or payload.get("texts") or [])
    try:
        resp = await client.post(endpoint.path, json=payload, timeout=timeout)
        elapsed = time.perf_counter() - t0
        ok = resp.status_code == 200
        err = "" if ok else resp.text[:200]
        return RequestResult(ok=ok, status=resp.status_code, elapsed=elapsed, items=items, error=err)
    except Exception as e:  # 网络错误 / 超时
        elapsed = time.perf_counter() - t0
        return RequestResult(ok=False, status=0, elapsed=elapsed, items=items, error=type(e).__name__)


async def run(endpoint: Endpoint, args: argparse.Namespace) -> Summary:
    """执行单个接口的压测，返回汇总。"""
    base_url = args.base_url.rstrip("/")
    # 1. 准备载荷池
    if endpoint.payload_kind == "images":
        pool: list[str] = load_images(Path(args.images_dir), limit=args.image_limit)
        print(f"[{endpoint.name}] 加载 {len(pool)} 张图片: {args.images_dir}")
    else:
        pool = list(SAMPLE_TEXTS)
        print(f"[{endpoint.name}] 使用 {len(pool)} 条样本文本")

    # 2. 探测服务可达性（一次同步请求），避免空跑
    async with httpx.AsyncClient(base_url=base_url) as probe_client:
        probe = await _probe(probe_client, endpoint, build_payload(endpoint.payload_kind, pool, 1, 0), args.timeout)
        if not probe.ok:
            print(f"[{endpoint.name}] ❌ 探测失败（{probe.status} {probe.error}），请确认服务 {base_url} 可达且模型已加载。")
            return Summary(endpoint.key, endpoint.name, endpoint.path, base_url,
                           args.concurrency, args.images_per_request)
        print(f"[{endpoint.name}] 探测成功，开始压测...")

    summary = Summary(
        endpoint_key=endpoint.key,
        endpoint_name=endpoint.name,
        path=endpoint.path,
        base_url=base_url,
        concurrency=args.concurrency,
        items_per_request=args.images_per_request,
    )

    # 3. warmup（不计入统计），复用同一连接池
    async with httpx.AsyncClient(base_url=base_url) as wc:
        for w in range(args.warmup):
            await _probe(wc, endpoint, build_payload(endpoint.payload_kind, pool, args.images_per_request, w), args.timeout)

    # 4. 正式压测
    # duration > 0 时覆盖 -n：按时长跑，数量上限置 0 表示不限。
    max_requests = 0 if args.duration > 0 else args.requests
    limits = httpx.Limits(max_connections=args.concurrency * 2, max_keepalive_connections=args.concurrency)
    headers = {"Content-Type": "application/json"}

    stop_at = time.perf_counter() + args.duration if args.duration > 0 else None
    seq = 0
    done = 0
    print_lock = asyncio.Lock()

    async def worker(client: httpx.AsyncClient):
        nonlocal seq, done
        while True:
            if stop_at is not None and time.perf_counter() >= stop_at:
                return
            if max_requests > 0 and done >= max_requests:
                return
            my_seq = seq
            seq += 1
            if max_requests > 0 and my_seq >= max_requests:
                return
            payload = build_payload(endpoint.payload_kind, pool, args.images_per_request, my_seq)
            res = await _probe(client, endpoint, payload, args.timeout)
            summary.add(res)
            done += 1
            if args.verbose:
                # 每 5% 或 duration 模式下每 10 个请求打印一次进度
                step = max(1, (max_requests // 20) if max_requests > 0 else 10)
                if done % step == 0 or stop_at is None:
                    async with print_lock:
                        print(f"  完成 {done}  请求  成功 {summary.success}  失败 {summary.failed}")

    t_start = time.perf_counter()
    async with httpx.AsyncClient(base_url=base_url, headers=headers, limits=limits) as client:
        workers = [asyncio.create_task(worker(client)) for _ in range(args.concurrency)]
        await asyncio.gather(*workers)
    summary.wall_seconds = time.perf_counter() - t_start

    return summary


# ----------------------------- 参数与入口 -----------------------------

def build_parser(description: str) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=description, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument("--base-url", default=os.environ.get("AI_API_URL", "http://localhost:8001"),
                   help="AI 微服务地址")
    p.add_argument("-c", "--concurrency", type=int, default=4, help="并发请求数")
    p.add_argument("-k", "--images-per-request", type=int, default=1,
                   help="每次请求携带的图片/文本数（batch 大小）")
    p.add_argument("-n", "--requests", type=int, default=20,
                   help="总请求数（>0 时按数量跑；=0 时按 --duration 时长跑）")
    p.add_argument("-d", "--duration", type=float, default=0.0,
                   help="压测持续秒数；>0 时覆盖 -n，按时长跑")
    p.add_argument("--images-dir", default=str(_DEFAULT_IMAGES_DIR),
                   help="测试图片目录（images 类接口）")
    p.add_argument("--image-limit", type=int, default=50,
                   help="最多加载多少张图片（避免内存爆炸）")
    p.add_argument("--warmup", type=int, default=1, help="预热请求数（不计入统计）")
    p.add_argument("--timeout", type=float, default=120.0, help="单请求超时秒数")
    p.add_argument("-o", "--output", default="", help="JSON 报告输出路径（可选）")
    p.add_argument("--append-report", action="store_true",
                   help="--output 已存在时追加到 reports 数组而非覆盖")
    p.add_argument("--verbose", action="store_true", help="打印进度")
    return p


def parse_args(endpoint: Endpoint, argv: Optional[list[str]] = None) -> argparse.Namespace:
    return build_parser(f"压测 AI 接口: {endpoint.name} ({endpoint.path})").parse_args(argv)


def print_summary(s: Summary) -> None:
    print()
    print("=" * 64)
    print(f"  {s.endpoint_name}  [{s.path}]")
    print("=" * 64)
    print(f"  并发度         : {s.concurrency}")
    print(f"  每请求条数     : {s.items_per_request}")
    print(f"  总请求         : {s.total_requests}   (成功 {s.success} / 失败 {s.failed})")
    print(f"  总条目(图片/文本): {s.total_items}")
    print(f"  总耗时         : {s.wall_seconds:.3f} s")
    print(f"  请求吞吐 RPS   : {s.rps():.2f} req/s")
    print(f"  条目吞吐       : {s.items_per_sec():.2f} items/s")
    lat = s.latency_ms_view()
    print(f"  延迟(ms)       : min={lat['min']}  mean={lat['mean']}  p50={lat['p50']}  p95={lat['p95']}  p99={lat['p99']}  max={lat['max']}")
    if s.errors:
        print(f"  错误分布       : {s.errors}")
    print("=" * 64)


def write_report(path: str, summary: Summary, append: bool) -> None:
    """把单个 summary 写入 JSON 文件。append 模式下合并到 reports 数组。"""
    out = Path(path)
    if append and out.exists():
        try:
            existing = json.loads(out.read_text(encoding="utf-8"))
            if isinstance(existing, dict) and "reports" in existing:
                report = existing
            elif isinstance(existing, list):
                report = {"reports": existing}
            else:
                report = {"reports": [existing]}
        except Exception:
            report = {"reports": []}
    else:
        report = {"reports": []}
    report.setdefault("reports", []).append(summary.to_dict())
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"📄 报告已写入: {out}")


def main_for(endpoint: Endpoint, argv: Optional[list[str]] = None) -> int:
    args = parse_args(endpoint, argv)
    if args.requests <= 0 and args.duration <= 0:
        print("请指定 -n（总请求数）或 -d（持续秒数）")
        return 2
    summary = asyncio.run(run(endpoint, args))
    print_summary(summary)
    if args.output:
        write_report(args.output, summary, args.append_report)
    return 0 if summary.failed == 0 else 1
