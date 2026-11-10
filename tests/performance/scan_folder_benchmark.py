#!/usr/bin/env python
"""TrailSnap 文件夹扫描性能基准。

这个脚本面向一个已经启动的 TrailSnap 后端（通常由
``tests/scripts/run-perf.ps1`` 在全新测试库上启动），通过真实 HTTP / SSE
接口完成下面的黑盒流程：

1. 生成（或复用）一个包含照片的扫描目录；
2. 添加该目录为外部图库，触发后端自动扫描；
3. 订阅 ``/tasks/events`` 并轮询 ``/tasks/``，记录每个任务的排队时间、
   执行时间和总耗时；
4. 等扫描及本地处理链路排空后，输出 Markdown / JSON / CSV 报告；
5. 删除本次添加的目录和临时照片，不污染测试库。

默认会暂停 AI 任务类型，只测 ``SCAN_FOLDER -> PROCESS_BASIC ->
EXTRACT_METADATA`` 这条本地链路，因此不需要启动 AI 服务。完整 AI 链路的
性能测试是后续扩展项，当前版本不把 AI 任务混入“链路排空”判定。

设计约束：
- 只使用 Python 标准库 + Pillow（生成测试照片时）；
- 不直接连接数据库，所有指标来自 HTTP/SSE，避免绑定 ORM 实现；
- 已完成的任务行会被后端删除，因此耗时以 SSE 事件到达的客户端单调时钟为主，
  server 时间戳只用于排队时间等辅助口径。
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import platform
import shutil
import statistics
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional

REPORT_SCHEMA_VERSION = 1
REPO_ROOT = Path(__file__).resolve().parents[2]

# 默认暂停的 AI 任务类型。它们都依赖 AI 服务，在只启动 server 的性能场景里
# 会长期 pending / 失败重试，阻塞“链路排空”的判定。
AI_TASK_TYPES = (
    "CLASSIFY_IMAGE",
    "RECOGNIZE_FACE",
    "IMAGE_EMBEDDING",
    "OCR",
    "RECOGNIZE_TICKET",
    "VISUAL_DESCRIPTION",
)

CORE_TASK_TYPES = ("SCAN_FOLDER", "PROCESS_BASIC", "EXTRACT_METADATA")
TERMINAL_STATUSES = {"completed", "failed", "cancelled"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".tif", ".tiff", ".heic", ".heif"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}


# ---------------------------------------------------------------------------
# 基础工具
# ---------------------------------------------------------------------------
def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def local_timezone():
    return datetime.now().astimezone().tzinfo


_LOCAL_TZ = local_timezone()


def parse_server_timestamp(value: Any) -> Optional[float]:
    """把后端返回的 ISO 时间戳转成 Unix 秒。

    后端混用两种写法：PG 的 timezone-aware 时间，以及 worker 里
    ``datetime.now().isoformat()`` 的 naive 本地时间。两者都按宿主机时区解释，
    因为性能测试与后端运行在同一台机器上。
    """
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_LOCAL_TZ)
    return parsed.timestamp()


def fmt_seconds(value: Optional[float]) -> str:
    if value is None:
        return "-"
    if value < 1:
        return f"{value * 1000:.0f} ms"
    if value < 60:
        return f"{value:.2f} s"
    minutes, seconds = divmod(value, 60)
    return f"{int(minutes)}m {seconds:.1f}s"


def fmt_bytes(value: int) -> str:
    size = float(value)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def percentile(values: list[float], ratio: float) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    position = (len(ordered) - 1) * ratio
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return float(ordered[lower] * (1 - weight) + ordered[upper] * weight)


def summarize_seconds(values: Iterable[Optional[float]]) -> dict[str, Any]:
    clean = sorted(float(v) for v in values if v is not None and v >= 0)
    if not clean:
        return {"count": 0, "min": None, "mean": None, "p50": None, "p95": None, "max": None, "sum": None}
    return {
        "count": len(clean),
        "min": round(clean[0], 4),
        "mean": round(statistics.fmean(clean), 4),
        "p50": round(percentile(clean, 0.50) or 0, 4),
        "p95": round(percentile(clean, 0.95) or 0, 4),
        "max": round(clean[-1], 4),
        "sum": round(sum(clean), 4),
    }


def _safe_span(start: Optional[float], end: Optional[float], *, max_seconds: float = 86_400) -> Optional[float]:
    """两个服务端时间戳的差；异常值（时钟跳变、错误字段）返回 None。"""
    if start is None or end is None:
        return None
    span = end - start
    if span < -0.5 or span > max_seconds:
        return None
    return max(0.0, span)


def _redact_database_url(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:
        return "<invalid>"
    if not parts.scheme:
        return url
    netloc = parts.netloc
    if "@" in netloc:
        credentials, host = netloc.rsplit("@", 1)
        if ":" in credentials:
            user = credentials.split(":", 1)[0]
            netloc = f"{user}:***@{host}"
    return urllib.parse.urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def count_media_files(folder: Path) -> tuple[int, int]:
    """返回 (媒体文件数, 总字节数)。只统计扫描器支持的扩展名。"""
    total = 0
    size = 0
    supported = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS
    for path in folder.rglob("*"):
        if path.is_file() and path.suffix.lower() in supported:
            total += 1
            try:
                size += path.stat().st_size
            except OSError:
                pass
    return total, size


def git_commit() -> Optional[str]:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        value = result.stdout.strip()
        return value or None
    except (OSError, subprocess.SubprocessError):
        return None


def memory_gb() -> Optional[float]:
    try:
        import psutil  # type: ignore

        return round(psutil.virtual_memory().total / (1024**3), 1)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# HTTP / SSE 客户端
# ---------------------------------------------------------------------------
class ApiError(RuntimeError):
    pass


class HttpApi:
    def __init__(self, base_url: str, *, timeout: float = 60.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.token: Optional[str] = None

    def _url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return f"{self.base_url}/{path.lstrip('/')}"

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: Any = None,
        form_body: Optional[dict[str, Any]] = None,
        timeout: Optional[float] = None,
        raw: bool = False,
    ) -> Any:
        headers = {"Accept": "application/json"}
        data: Optional[bytes] = None
        if json_body is not None:
            data = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json; charset=utf-8"
        elif form_body is not None:
            data = urllib.parse.urlencode(form_body).encode("utf-8")
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        request = urllib.request.Request(self._url(path), data=data, headers=headers, method=method.upper())
        try:
            with urllib.request.urlopen(request, timeout=timeout or self.timeout) as response:
                payload = response.read().decode("utf-8", errors="replace")
                status = response.status
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise ApiError(f"{method.upper()} {path} -> HTTP {error.code}: {detail[:500]}") from error
        except urllib.error.URLError as error:
            raise ApiError(f"{method.upper()} {path} -> {error.reason}") from error
        except TimeoutError as error:
            raise ApiError(f"{method.upper()} {path} -> 请求超时") from error

        if raw:
            return payload
        if not payload:
            return {}
        try:
            return json.loads(payload)
        except json.JSONDecodeError as error:
            raise ApiError(
                f"{method.upper()} {path} -> HTTP {status} 返回非 JSON: {payload[:300]}"
            ) from error

    def get(self, path: str, **kwargs: Any) -> Any:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> Any:
        return self.request("POST", path, **kwargs)

    def put(self, path: str, **kwargs: Any) -> Any:
        return self.request("PUT", path, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> Any:
        return self.request("DELETE", path, **kwargs)

    def unwrap(self, payload: Any) -> Any:
        """兼容 BaseResponse 与旧式的裸返回。"""
        if isinstance(payload, dict) and "code" in payload and "data" in payload:
            if payload.get("code") != 0:
                raise ApiError(f"后端返回业务错误 code={payload.get('code')}: {payload.get('msg')}")
            return payload.get("data")
        return payload


def wait_for_server(api: HttpApi, *, timeout: float = 180.0) -> None:
    deadline = time.monotonic() + timeout
    last_error: Optional[Exception] = None
    while time.monotonic() < deadline:
        try:
            response = api.get("/health-check", timeout=5)
            if isinstance(response, dict) and response.get("status") == "ok":
                return
        except ApiError as error:
            last_error = error
        time.sleep(1.0)
    raise ApiError(f"后端在 {timeout:.0f}s 内未就绪: {last_error}")


def ensure_admin_session(api: HttpApi, username: str, password: str, email: str) -> dict[str, Any]:
    """在空库上注册首个管理员；非空库则直接登录。"""
    status = api.get("/auth/status", timeout=10)
    has_users = bool(status.get("has_users")) if isinstance(status, dict) else False
    if not has_users:
        api.post(
            "/auth/register",
            json_body={"username": username, "email": email, "password": password},
            timeout=30,
        )
    token_payload = api.post(
        "/auth/login",
        form_body={"username": username, "password": password},
        timeout=30,
    )
    token = token_payload.get("access_token") if isinstance(token_payload, dict) else None
    if not token:
        raise ApiError(f"登录失败，未拿到 access_token: {token_payload}")
    api.token = token
    me = api.get("/users/me", timeout=15)
    if not isinstance(me, dict) or not me.get("is_superuser"):
        raise ApiError("性能测试需要管理员账号（添加外部图库需要 superuser 权限）")
    return me


# ---------------------------------------------------------------------------
# SSE 解析与任务事件跟踪
# ---------------------------------------------------------------------------
class SseParser:
    """最小 SSE 行解析器；一次 feed 一行，返回完整事件或 None。"""

    def __init__(self) -> None:
        self.event = "message"
        self.data_lines: list[str] = []

    def feed(self, line: str) -> Optional[tuple[str, str]]:
        if line == "":
            if not self.data_lines:
                self.event = "message"
                return None
            payload = "\n".join(self.data_lines)
            event = self.event
            self.event = "message"
            self.data_lines = []
            return event, payload
        if line.startswith(":"):
            return None
        field, separator, value = line.partition(":")
        if separator and value.startswith(" "):
            value = value[1:]
        if field == "event":
            self.event = value or "message"
        elif field == "data":
            self.data_lines.append(value)
        # id / retry 字段对本次基准没有用途。
        return None


@dataclass
class TaskTiming:
    task_id: str
    task_type: str
    status: str = "unknown"
    created_at: Optional[float] = None
    processing_at: Optional[float] = None
    completed_at: Optional[float] = None
    first_seen_mono: Optional[float] = None
    processing_mono: Optional[float] = None
    completed_mono: Optional[float] = None
    total_items: int = 0
    processed_items: int = 0
    error: Optional[str] = None
    payload: dict[str, Any] = field(default_factory=dict)

    @property
    def terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES

    def queue_seconds(self) -> Optional[float]:
        # created_at/processing_at 都来自数据库时钟，优先用服务端时间；
        # 缺失时回退到事件到达的单调时钟。
        span = _safe_span(self.created_at, self.processing_at)
        if span is not None:
            return span
        if self.processing_mono is not None and self.first_seen_mono is not None:
            return max(0.0, self.processing_mono - self.first_seen_mono)
        return None

    def execution_seconds(self) -> Optional[float]:
        # 完成时间来自 worker 进程的 datetime.now()，可能和远程数据库时钟
        # 不一致；执行耗时优先用客户端单调时钟，避免跨主机时钟混算。
        if self.processing_mono is not None and self.completed_mono is not None:
            return max(0.0, self.completed_mono - self.processing_mono)
        return _safe_span(self.processing_at, self.completed_at)

    def total_seconds(self) -> Optional[float]:
        # 下游任务通常没有 task.created 事件（由 worker 直接插入），首次
        # 观察到时已经是 processing；此时不能把 total 当成纯执行时间。
        # 用“服务端排队 + 客户端执行”组合，避免跨主机时钟混算。
        queue = self.queue_seconds()
        execution = self.execution_seconds()
        if queue is not None and execution is not None:
            return queue + execution
        if self.completed_mono is not None and self.first_seen_mono is not None:
            return max(0.0, self.completed_mono - self.first_seen_mono)
        return _safe_span(self.created_at, self.completed_at)

    def to_sample(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "type": self.task_type,
            "status": self.status,
            "queue_seconds": _rounded(self.queue_seconds()),
            "execution_seconds": _rounded(self.execution_seconds()),
            "total_seconds": _rounded(self.total_seconds()),
            "total_items": self.total_items,
            "processed_items": self.processed_items,
            "error": self.error,
        }


def _rounded(value: Optional[float]) -> Optional[float]:
    return None if value is None else round(value, 4)


class TaskEventTracker:
    """线程安全地合并 SSE 事件与 /tasks/ 轮询快照。"""

    _STATUS_RANK = {"unknown": 0, "pending": 1, "processing": 2}

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._records: dict[str, TaskTiming] = {}
        self.last_change_mono = time.monotonic()
        self.raw_event_count = 0
        self.parse_errors = 0

    @classmethod
    def _merge_status(cls, current: str, incoming: str) -> str:
        """避免 SSE / 轮询并发时把 processing 回退成 pending。"""
        if not incoming:
            return current
        if current in TERMINAL_STATUSES:
            return current
        if incoming in TERMINAL_STATUSES:
            return incoming
        return incoming if cls._STATUS_RANK.get(incoming, 0) >= cls._STATUS_RANK.get(current, 0) else current

    def _new_record(self, task_id: str, task_type: str, received_mono: float) -> TaskTiming:
        record = TaskTiming(
            task_id=task_id,
            task_type=task_type or "UNKNOWN",
            first_seen_mono=received_mono,
        )
        self._records[task_id] = record
        return record

    def observe_event(self, event_name: str, data: dict[str, Any], received_mono: float) -> None:
        if not isinstance(data, dict):
            return
        task_id = str(data.get("id") or "")
        if not task_id:
            return
        with self._lock:
            self.raw_event_count += 1
            record = self._records.get(task_id) or self._new_record(
                task_id, str(data.get("type") or "UNKNOWN"), received_mono
            )
            record.task_type = str(data.get("type") or record.task_type)
            record.status = self._merge_status(record.status, str(data.get("status") or ""))
            if data.get("created_at"):
                record.created_at = record.created_at or parse_server_timestamp(data.get("created_at"))
            if data.get("updated_at"):
                updated = parse_server_timestamp(data.get("updated_at"))
            else:
                updated = None
            if record.status == "processing":
                record.processing_at = record.processing_at or updated
                record.processing_mono = record.processing_mono or received_mono
            elif record.status in TERMINAL_STATUSES:
                record.completed_at = record.completed_at or updated
                record.completed_mono = record.completed_mono or received_mono
            record.total_items = int(data.get("total_items") or record.total_items or 0)
            record.processed_items = int(data.get("processed_items") or record.processed_items or 0)
            record.error = data.get("error") or record.error
            if isinstance(data.get("payload"), dict):
                record.payload = data["payload"]
            self.last_change_mono = received_mono

    def observe_task_rows(self, rows: Any, received_mono: float) -> None:
        if not isinstance(rows, list):
            return
        with self._lock:
            changed = False
            for row in rows:
                if not isinstance(row, dict):
                    continue
                task_id = str(row.get("id") or "")
                if not task_id:
                    continue
                record = self._records.get(task_id)
                if record is None:
                    record = self._new_record(task_id, str(row.get("type") or "UNKNOWN"), received_mono)
                    changed = True
                record.task_type = str(row.get("type") or record.task_type)
                status = str(row.get("status") or record.status)
                if status:
                    record.status = self._merge_status(record.status, status)
                if row.get("created_at"):
                    record.created_at = record.created_at or parse_server_timestamp(row.get("created_at"))
                if status == "processing" and record.processing_at is None:
                    updated = parse_server_timestamp(row.get("updated_at"))
                    record.processing_at = updated
                    record.processing_mono = received_mono
                    changed = True
                record.total_items = max(record.total_items, int(row.get("total_items") or 0))
                record.processed_items = max(record.processed_items, int(row.get("processed_items") or 0))
                if row.get("error"):
                    record.error = str(row["error"])
            if changed:
                self.last_change_mono = received_mono

    def snapshot(self) -> list[TaskTiming]:
        with self._lock:
            return [replace(record) for record in self._records.values()]

    def get(self, task_id: str) -> Optional[TaskTiming]:
        with self._lock:
            record = self._records.get(task_id)
            return replace(record) if record else None

    def scan_task(self) -> Optional[TaskTiming]:
        with self._lock:
            scans = [record for record in self._records.values() if record.task_type == "SCAN_FOLDER"]
            if not scans:
                return None
            return replace(max(scans, key=lambda record: record.first_seen_mono or 0))

    def counts(self, paused_types: set[str]) -> dict[str, int]:
        with self._lock:
            active = 0
            completed = 0
            failed = 0
            for record in self._records.values():
                if record.task_type in paused_types:
                    continue
                if record.status in {"pending", "processing"}:
                    active += 1
                elif record.status == "completed":
                    completed += 1
                elif record.status in {"failed", "cancelled"}:
                    failed += 1
            return {"active": active, "completed": completed, "failed": failed}


class TaskEventStream(threading.Thread):
    """后台读取 /tasks/events 的 SSE 流，断线自动重连。"""

    def __init__(self, api: HttpApi, tracker: TaskEventTracker, stop_event: threading.Event) -> None:
        super().__init__(name="perf-sse-reader", daemon=True)
        self.api = api
        self.tracker = tracker
        self.stop_event = stop_event
        self.connected = threading.Event()
        self.last_error: Optional[str] = None

    def run(self) -> None:
        attempt = 0
        while not self.stop_event.is_set():
            try:
                self._read_once()
                attempt = 0
            except Exception as error:  # 网络抖动时重连，真正失败由主流程超时兜底
                self.last_error = str(error)
                if self.stop_event.is_set():
                    return
                attempt += 1
                time.sleep(min(2.0, 0.2 * attempt))

    def _read_once(self) -> None:
        url = (
            f"{self.api.base_url}/tasks/events?"
            + urllib.parse.urlencode({"token": self.api.token or ""})
        )
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "text/event-stream",
                "Authorization": f"Bearer {self.api.token or ''}",
                "Cache-Control": "no-cache",
            },
        )
        parser = SseParser()
        with urllib.request.urlopen(request, timeout=45) as response:
            self.connected.set()
            self.last_error = None
            for raw_line in response:
                if self.stop_event.is_set():
                    return
                line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
                frame = parser.feed(line)
                if frame is None:
                    continue
                event_name, payload = frame
                if event_name in {"ping", "hello"}:
                    continue
                try:
                    data = json.loads(payload)
                except json.JSONDecodeError:
                    self.tracker.parse_errors += 1
                    continue
                if event_name.startswith("task."):
                    self.tracker.observe_event(event_name, data, time.monotonic())


class TaskPoller(threading.Thread):
    """SSE 的兜底：定期抓 /tasks/ 快照，补上漏掉的 processing 事件。"""

    def __init__(self, api: HttpApi, tracker: TaskEventTracker, stop_event: threading.Event, interval: float) -> None:
        super().__init__(name="perf-task-poller", daemon=True)
        self.api = api
        self.tracker = tracker
        self.stop_event = stop_event
        self.interval = max(0.1, interval)
        self.last_error: Optional[str] = None

    def run(self) -> None:
        while not self.stop_event.is_set():
            try:
                payload = self.api.get("/tasks/?limit=1000", timeout=15)
                rows = payload.get("data") if isinstance(payload, dict) else payload
                self.tracker.observe_task_rows(rows, time.monotonic())
            except Exception as error:
                self.last_error = str(error)
            self.stop_event.wait(self.interval)


# ---------------------------------------------------------------------------
# 测试照片生成
# ---------------------------------------------------------------------------
def generate_photos(folder: Path, count: int, *, seed: int = 20261108) -> float:
    """生成可被 Pillow/OpenCV 正常解码的 JPEG，返回生成耗时。"""
    try:
        from PIL import Image, ImageDraw, ImageOps
    except Exception as error:  # pragma: no cover - 仅在缺少 Pillow 的裸环境触发
        raise RuntimeError("生成测试照片需要 Pillow，请在 package/server 的 uv 环境里运行") from error

    started = time.perf_counter()
    folder.mkdir(parents=True, exist_ok=True)
    # 用固定伪随机序列生成颜色/形状，保证同一参数下内容可复现。
    state = seed & 0xFFFFFFFF

    def rand() -> int:
        nonlocal state
        state = (1103515245 * state + 12345) & 0x7FFFFFFF
        return state

    for index in range(count):
        width, height = 1280, 960
        hue = rand() % 360
        base = Image.new("RGB", (width, height), (rand() % 256, rand() % 256, rand() % 256))
        gradient = Image.linear_gradient("L").resize((width, height))
        tint = ImageOps.colorize(gradient, black=f"hsl({hue}, 35%, 12%)", white=f"hsl({hue}, 55%, 88%)")
        image = Image.blend(base, tint, 0.55)
        draw = ImageDraw.Draw(image)
        for _ in range(6):
            x0, y0 = rand() % width, rand() % height
            x1, y1 = x0 + rand() % 420, y0 + rand() % 320
            color = (rand() % 256, rand() % 256, rand() % 256)
            if rand() % 2:
                draw.rectangle([x0, y0, x1, y1], outline=color, width=4)
            else:
                draw.ellipse([x0, y0, x1, y1], outline=color, width=4)
        draw.text((32, 32), f"TrailSnap perf {index:05d}", fill=(255, 255, 255))

        exif = Image.Exif()
        exif[271] = "TrailSnapPerfCam"
        exif[272] = "PerfBody"
        exif[306] = "2026:11:08 10:00:00"
        # 每 10 张切一个子目录，覆盖递归扫描路径。
        subdir = folder / f"album_{index // 10:03d}"
        subdir.mkdir(parents=True, exist_ok=True)
        image.save(subdir / f"IMG_{index:05d}.jpg", "JPEG", quality=85, exif=exif, optimize=False)
    return time.perf_counter() - started


def prepare_dataset(source_folder: Optional[Path], count: int, work_root: Path) -> dict[str, Any]:
    if source_folder is not None:
        folder = source_folder.expanduser().resolve()
        if not folder.is_dir():
            raise FileNotFoundError(f"照片目录不存在: {folder}")
        photos, total_bytes = count_media_files(folder)
        if photos == 0:
            raise RuntimeError(f"照片目录里没有可扫描的图片/视频: {folder}")
        return {
            "kind": "existing",
            "folder": str(folder),
            "photos": photos,
            "bytes": total_bytes,
            "generate_seconds": None,
            # 真实目录可能包含 live photo 配对：服务端会把同名的
            # 图片+视频折叠成一个 PROCESS_BASIC，无法仅凭扩展名精确估算，
            # 因此不把“预期核心任务数”作为通过条件。
            "expected_core_tasks": None,
            # 每个媒体文件最多贡献一组 PROCESS_BASIC + EXTRACT_METADATA；
            # 最坏情况全部是 live photo 配对时，任务数仍至少为 1 + 文件数。
            "min_expected_core_tasks": 1 + photos,
        }

    folder = work_root.resolve()
    generation_seconds = generate_photos(folder, count)
    photos, total_bytes = count_media_files(folder)
    return {
        "kind": "generated",
        "folder": str(folder),
        "photos": photos,
        "bytes": total_bytes,
        "generate_seconds": round(generation_seconds, 3),
        "expected_core_tasks": 1 + 2 * photos,
        "min_expected_core_tasks": 1 + 2 * photos,
    }


# ---------------------------------------------------------------------------
# 基准主流程
# ---------------------------------------------------------------------------
def _unwrap_task(payload: Any) -> Optional[dict[str, Any]]:
    if isinstance(payload, dict) and "data" in payload and "code" in payload:
        return payload.get("data")
    return payload if isinstance(payload, dict) else None


def _wait_for_scan_task(tracker: TaskEventTracker, timeout: float) -> TaskTiming:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        scan = tracker.scan_task()
        if scan is not None:
            return scan
        time.sleep(0.1)
    raise TimeoutError(f"添加图库后 {timeout:.0f}s 内没有观察到 SCAN_FOLDER 任务")


def _wait_for_pipeline(
    tracker: TaskEventTracker,
    scan: TaskTiming,
    *,
    pipeline_started: float,
    total_expected: int,
    timeout: float,
    stall_seconds: float,
    settle_seconds: float,
) -> dict[str, Any]:
    started = time.monotonic()
    deadline = started + timeout
    last_print = 0.0
    timed_out = False
    stalled = False
    last_progress = pipeline_started
    last_completed = -1
    last_scan_status = "unknown"

    while True:
        now = time.monotonic()
        scan_now = tracker.get(scan.task_id) or scan
        records = tracker.snapshot()
        counts = tracker.counts(set(AI_TASK_TYPES))
        core_completed = sum(
            1
            for record in records
            if record.task_type in CORE_TASK_TYPES and record.status == "completed"
        )
        core_failed = sum(
            1
            for record in records
            if record.task_type in CORE_TASK_TYPES and record.status in {"failed", "cancelled"}
        )
        active = counts["active"]
        no_events_for = now - tracker.last_change_mono

        if core_completed != last_completed or scan_now.status != last_scan_status:
            last_completed = core_completed
            last_scan_status = scan_now.status
            last_progress = now
        # 任意任务事件也算进度，避免把后台关联任务误判成停滞。
        if tracker.last_change_mono > last_progress:
            last_progress = tracker.last_change_mono

        # 这个条件本身已经包含 settle 秒的安静窗口，满足时直接判定排空；
        # 不再额外等待第二个窗口，否则会把测量开销写进“总耗时”。
        if scan_now.terminal and active == 0 and no_events_for >= settle_seconds:
            break

        if now - last_print >= 5.0:
            last_print = now
            print(
                f"[perf] +{now - started:6.1f}s  scan={scan_now.status:<10} "
                f"core_completed={core_completed}/{total_expected} core_failed={core_failed} "
                f"active={active}",
                flush=True,
            )

        # 扫描本身只发开始/结束事件，不能因为目录大、扫描久就判定停滞；
        # 等扫描结束后，再观察核心任务是否长时间没有进展。
        if scan_now.terminal and active > 0 and now - last_progress >= stall_seconds:
            stalled = True
            break
        if now >= deadline:
            timed_out = True
            break
        time.sleep(0.25)

    finished = time.monotonic()
    # settle 只是“确认排空”的观察窗口，不应计入处理耗时。始终以最后一次
    # 核心进度（最后一个任务完成 / 扫描状态变化）作为 pipeline 终点。
    measured_pipeline = max(0.0, last_progress - pipeline_started)
    return {
        "timed_out": timed_out,
        "stalled": stalled,
        "drain_seconds": finished - started,
        "pipeline_seconds": measured_pipeline,
        "last_progress_seconds": last_progress - pipeline_started,
        "scan_status": (tracker.get(scan.task_id) or scan).status,
        "core_completed": core_completed,
        "core_failed": core_failed,
        "active": active,
    }


def run_benchmark(args: argparse.Namespace, report_dir: Path) -> dict[str, Any]:
    started_at = now_iso()
    started_mono = time.monotonic()
    report_dir.mkdir(parents=True, exist_ok=True)

    api = HttpApi(args.api_base_url)
    wait_for_server(api, timeout=args.startup_timeout)
    email = args.email or (
        args.username if "@" in args.username else f"{args.username}@example.com"
    )
    ensure_admin_session(api, args.username, args.password, email)

    work_root = Path(args.work_root).resolve() if args.work_root else (
        REPO_ROOT / "tests" / ".cache" / "performance-scan" / args.run_id
    )
    if work_root.exists() and not args.keep_fixture:
        shutil.rmtree(work_root, ignore_errors=True)
    dataset = prepare_dataset(
        Path(args.source_folder) if args.source_folder else None,
        args.photo_count,
        work_root / "photos",
    )
    folder = Path(dataset["folder"])
    print(
        f"[perf] 数据准备完成: {dataset['photos']} 张 / {fmt_bytes(dataset['bytes'])} / {folder}",
        flush=True,
    )

    # 当前场景只测本地链路，固定暂停 AI 类型；完整 AI 链路是后续扩展项。
    paused_types = list(AI_TASK_TYPES)
    for task_type in paused_types:
        api.post(f"/tasks/categories/{task_type}/pause", timeout=15)
    print(f"[perf] 已暂停 {len(paused_types)} 个 AI 任务类型；等待 worker 同步暂停状态...", flush=True)
    time.sleep(args.pause_settle_seconds)

    tracker = TaskEventTracker()
    stop_event = threading.Event()
    sse = TaskEventStream(api, tracker, stop_event)
    poller = TaskPoller(api, tracker, stop_event, args.poll_interval)
    registered = False
    scan_record: Optional[TaskTiming] = None
    cleanup_error: Optional[str] = None
    result: dict[str, Any] = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "run_id": args.run_id,
        "status": "error",
        "started_at": started_at,
        "finished_at": None,
        "environment": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "cpu_count": os.cpu_count(),
            "memory_gb": memory_gb(),
            "python": platform.python_version(),
            "git_commit": git_commit(),
            "api_base_url": args.api_base_url,
            "database": _redact_database_url(os.environ.get("TS_DB_URL")),
            "mode": os.environ.get("TS_TEST_ENV", "dev"),
        },
        "config": {
            "photo_count": args.photo_count,
            "timeout_seconds": args.timeout_seconds,
            "stall_seconds": args.stall_seconds,
            "poll_interval_seconds": args.poll_interval,
            "settle_seconds": args.settle_seconds,
            "paused_task_types": paused_types,
        },
        "dataset": dataset,
        "scan": None,
        "summary": None,
        "tasks": [],
        "task_samples": [],
        "events": {"sse_parse_errors": 0, "sse_last_error": None, "poll_last_error": None},
        "notes": [
            "已完成的任务行会被后端删除，任务耗时来自 SSE 事件到达的客户端单调时钟；排队时间优先使用数据库时间戳。",
            "queue_seconds = 开始处理时间 - 任务创建时间；execution_seconds = 完成时间 - 开始处理时间；total_seconds = 完成时间 - 创建时间。",
            "默认暂停 AI 任务类型，只测 SCAN_FOLDER -> PROCESS_BASIC -> EXTRACT_METADATA 的本地链路。",
        ],
    }

    try:
        sse.start()
        poller.start()
        if not sse.connected.wait(timeout=10):
            raise ApiError(f"SSE 连接 10s 内未建立: {sse.last_error}")
        print("[perf] SSE 已连接，开始添加扫描目录", flush=True)

        pipeline_started = time.monotonic()
        add_started = time.monotonic()
        api.post("/settings/directories", json_body={"path": str(folder)}, timeout=60)
        add_directory_seconds = time.monotonic() - add_started
        registered = True
        scan_record = _wait_for_scan_task(tracker, timeout=60)
        print(f"[perf] 扫描任务已创建: {scan_record.task_id}", flush=True)

        expected_core = dataset.get("expected_core_tasks")
        progress_total = expected_core if expected_core is not None else (1 + 2 * int(dataset["photos"]))
        pipeline = _wait_for_pipeline(
            tracker,
            scan_record,
            pipeline_started=pipeline_started,
            total_expected=progress_total,
            timeout=args.timeout_seconds,
            stall_seconds=args.stall_seconds,
            settle_seconds=args.settle_seconds,
        )
        pipeline_seconds = pipeline["pipeline_seconds"]

        # 保留型任务（SCAN_FOLDER）可以从接口再拿一次权威结果。
        scan_detail: dict[str, Any] = {}
        try:
            detail_payload = api.get(f"/tasks/{scan_record.task_id}", timeout=15)
            scan_detail = _unwrap_task(detail_payload) or {}
        except ApiError:
            pass

        records = tracker.snapshot()
        scan_now = tracker.get(scan_record.task_id) or scan_record
        summary = _build_summary(
            records,
            dataset=dataset,
            pipeline_seconds=pipeline_seconds,
            add_directory_seconds=add_directory_seconds,
            scan_record=scan_now,
            scan_detail=scan_detail,
            expected_core=expected_core,
        )
        task_groups = _aggregate_tasks(
            records,
            pipeline_seconds=pipeline_seconds,
            paused_types=set(paused_types),
        )
        failed_core = summary["core_failed"]
        scan_result = scan_detail.get("result") or {}
        status = "passed"
        status_reason = None
        if pipeline["stalled"]:
            status = "stalled"
            status_reason = f"扫描结束后 {args.stall_seconds:.0f}s 内没有新任务完成"
        elif pipeline["timed_out"]:
            status = "timeout"
            status_reason = f"等待链路排空超过 {args.timeout_seconds:.0f}s"
        elif failed_core:
            status = "failed"
            status_reason = f"核心任务失败 {failed_core} 个"
        elif expected_core is not None and summary["core_tasks_completed"] < expected_core:
            # 生成场景的预期任务数是确定的；少了任务通常意味着事件丢失或
            # 链路提前结束，不能把不完整的采集标成 passed。
            status = "failed"
            status_reason = (
                f"核心任务只采集到 {summary['core_tasks_completed']}/{expected_core} 个"
            )
        elif expected_core is None and summary["core_tasks_completed"] < dataset["min_expected_core_tasks"]:
            status = "failed"
            status_reason = (
                f"核心任务只采集到 {summary['core_tasks_completed']} 个，"
                f"低于最低期望 {dataset['min_expected_core_tasks']}"
            )
        elif scan_result.get("new_files") not in (None, dataset["photos"]):
            # new_files 与实际照片数不一致通常意味着扫描漏文件或扫描结果异常；
            # 记为 degraded 而不是直接崩溃，报告里保留真实数字。
            status = "degraded"
            status_reason = (
                f"扫描新增 {scan_result.get('new_files')}，数据目录有 {dataset['photos']} 个媒体文件"
            )
        stuck_samples = [
            record.to_sample()
            for record in records
            if record.task_type not in set(AI_TASK_TYPES)
            and record.status in {"pending", "processing"}
        ]
        result.update(
            {
                "status": status,
                "status_reason": status_reason,
                "pipeline": {
                    "timed_out": pipeline["timed_out"],
                    "stalled": pipeline["stalled"],
                    "drain_seconds": round(pipeline["drain_seconds"], 3),
                    "last_progress_seconds": round(pipeline["last_progress_seconds"], 3),
                    "active_tasks_at_stop": pipeline["active"],
                },
                "scan": {
                    "task_id": scan_record.task_id,
                    "status": summary["scan_status"],
                    "total_seconds": summary["scan_task_seconds"],
                    "new_files": scan_result.get("new_files"),
                    "deleted_files": scan_result.get("deleted_files"),
                    "result": scan_result,
                    "error": scan_detail.get("error"),
                },
                "summary": summary,
                "tasks": task_groups,
                "stuck_tasks": stuck_samples,
                "task_samples": [record.to_sample() for record in sorted(records, key=lambda r: (r.task_type, r.first_seen_mono or 0))],
            }
        )
        print(
            f"[perf] 完成: {status}，总耗时 {fmt_seconds(pipeline_seconds)}，"
            f"{dataset['photos']} 张，"
            f"{summary['photos_per_second']:.2f} 张/秒",
            flush=True,
        )
    except Exception as error:
        result["status"] = "error"
        result["error"] = f"{type(error).__name__}: {error}"
        result["traceback"] = traceback.format_exc(limit=8)
        print(f"[perf] 失败: {result['error']}", file=sys.stderr, flush=True)
    finally:
        stop_event.set()
        # 删除本次添加的图库（先取消任务/删索引），再删除临时照片。
        if registered:
            try:
                api.delete("/settings/directories", json_body={"path": str(folder)}, timeout=60)
            except Exception as error:
                cleanup_error = str(error)
                print(f"[perf] 清理图库失败: {cleanup_error}", file=sys.stderr, flush=True)
        if dataset.get("kind") == "generated" and not args.keep_fixture:
            shutil.rmtree(work_root, ignore_errors=True)
        try:
            sse.join(timeout=2)
            poller.join(timeout=2)
        except RuntimeError:
            pass
        result["finished_at"] = now_iso()
        result["elapsed_seconds"] = round(time.monotonic() - started_mono, 3)
        result["events"].update(
            {
                "sse_event_count": tracker.raw_event_count,
                "sse_parse_errors": tracker.parse_errors,
                "sse_last_error": sse.last_error,
                "poll_last_error": poller.last_error,
            }
        )
        if cleanup_error:
            result["cleanup_error"] = cleanup_error
        _write_reports(report_dir, result)
        result["report_dir"] = str(report_dir)

    return result


def _build_summary(
    records: list[TaskTiming],
    *,
    dataset: dict[str, Any],
    pipeline_seconds: float,
    add_directory_seconds: float,
    scan_record: TaskTiming,
    scan_detail: dict[str, Any],
    expected_core: int,
) -> dict[str, Any]:
    core_records = [record for record in records if record.task_type in CORE_TASK_TYPES]
    completed = [record for record in core_records if record.status == "completed"]
    failed = [record for record in core_records if record.status in {"failed", "cancelled"}]
    photos = int(dataset["photos"])
    scan_seconds = scan_record.total_seconds()
    if scan_seconds is None:
        scan_seconds = scan_record.execution_seconds()
    return {
        "pipeline_seconds": round(pipeline_seconds, 3),
        "add_directory_seconds": round(add_directory_seconds, 4),
        "scan_task_seconds": _rounded(scan_seconds),
        "photos": photos,
        "bytes": int(dataset["bytes"]),
        "photos_per_second": round(photos / pipeline_seconds, 3) if pipeline_seconds > 0 else None,
        "scan_photos_per_second": round(photos / scan_seconds, 3) if scan_seconds and scan_seconds > 0 else None,
        "bytes_per_second": round(int(dataset["bytes"]) / pipeline_seconds, 1) if pipeline_seconds > 0 else None,
        "seconds_per_photo": round(pipeline_seconds / photos, 4) if photos else None,
        "core_tasks_expected": expected_core,
        "core_tasks_min_expected": dataset.get("min_expected_core_tasks"),
        "core_tasks_observed": len(core_records),
        "core_tasks_completed": len(completed),
        "core_failed": len(failed),
        "scan_status": (scan_detail.get("status") or scan_record.status),
        "scan_new_files": (scan_detail.get("result") or {}).get("new_files"),
    }


def _aggregate_tasks(
    records: list[TaskTiming],
    *,
    pipeline_seconds: float,
    paused_types: Optional[set[str]] = None,
) -> list[dict[str, Any]]:
    paused_types = paused_types or set()
    grouped: dict[str, list[TaskTiming]] = {}
    for record in records:
        grouped.setdefault(record.task_type, []).append(record)
    rows: list[dict[str, Any]] = []
    for task_type in sorted(grouped):
        group = grouped[task_type]
        completed = [record for record in group if record.status == "completed"]
        failed = [record for record in group if record.status in {"failed", "cancelled"}]
        queue = summarize_seconds(record.queue_seconds() for record in group)
        execution = summarize_seconds(record.execution_seconds() for record in group)
        total = summarize_seconds(record.total_seconds() for record in group)
        paused = task_type in paused_types
        rows.append(
            {
                "type": task_type,
                "count": len(group),
                "completed": len(completed),
                "failed": len(failed),
                "pending_or_processing": sum(1 for record in group if record.status in {"pending", "processing"}),
                "paused": paused,
                "queue_seconds": queue,
                "execution_seconds": execution,
                "total_seconds": total,
                "throughput_tasks_per_second": (
                    None if paused or pipeline_seconds <= 0 else round(len(completed) / pipeline_seconds, 3)
                ),
            }
        )
    return rows


# ---------------------------------------------------------------------------
# 报告输出
# ---------------------------------------------------------------------------
def _write_reports(report_dir: Path, result: dict[str, Any]) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "report.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (report_dir / "report.md").write_text(_render_markdown(result), encoding="utf-8")
    _write_task_csv(report_dir / "tasks.csv", result.get("task_samples") or [])


def _write_task_csv(path: Path, samples: list[dict[str, Any]]) -> None:
    columns = [
        "task_id",
        "type",
        "status",
        "queue_seconds",
        "execution_seconds",
        "total_seconds",
        "total_items",
        "processed_items",
        "error",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for sample in samples:
            writer.writerow({column: sample.get(column) for column in columns})


def _render_markdown(result: dict[str, Any]) -> str:
    environment = result.get("environment") or {}
    dataset = result.get("dataset") or {}
    summary = result.get("summary") or {}
    tasks = result.get("tasks") or []
    scan = result.get("scan") or {}

    status = result.get("status", "unknown")
    status_label = {
        "passed": "通过",
        "degraded": "基本完成（有异常）",
        "failed": "失败",
        "stalled": "停滞（任务卡住）",
        "timeout": "超时",
        "error": "执行错误",
    }.get(status, status)

    lines: list[str] = []
    lines.append("# TrailSnap 文件夹扫描性能报告")
    lines.append("")
    lines.append(f"- 运行状态：**{status_label}** (`{status}`)")
    if result.get("status_reason"):
        lines.append(f"- 原因：{result['status_reason']}")
    lines.append(f"- 运行 ID：`{result.get('run_id', '-')}`")
    lines.append(f"- 开始时间：{result.get('started_at', '-')}")
    lines.append(f"- 结束时间：{result.get('finished_at', '-')}")
    lines.append(f"- API：`{environment.get('api_base_url', '-')}`")
    lines.append(f"- 数据库：`{environment.get('database') or '-'}`")
    lines.append(f"- Git：`{environment.get('git_commit') or '-'}`")
    lines.append("")
    if result.get("error"):
        lines.append("## 错误")
        lines.append("")
        lines.append("```")
        lines.append(str(result["error"]))
        lines.append("```")
        if result.get("traceback"):
            lines.append("")
            lines.append("<details><summary>traceback</summary>")
            lines.append("")
            lines.append("```")
            lines.append(str(result["traceback"]))
            lines.append("```")
            lines.append("</details>")
        lines.append("")
    if not summary:
        return "\n".join(lines) + "\n"

    lines.append("## 核心结果")
    lines.append("")
    lines.append("| 指标 | 数值 |")
    lines.append("|---|---:|")
    lines.append(f"| 扫描目录 | `{dataset.get('folder', '-')}` |")
    lines.append(f"| 照片数 | {summary.get('photos', '-')} |")
    lines.append(f"| 数据量 | {fmt_bytes(int(summary.get('bytes') or 0))} |")
    lines.append(f"| 添加图库接口耗时 | {fmt_seconds(summary.get('add_directory_seconds'))} |")
    lines.append(f"| 扫描任务耗时 | {fmt_seconds(summary.get('scan_task_seconds'))} |")
    lines.append(f"| 扫描 + 本地处理总耗时 | **{fmt_seconds(summary.get('pipeline_seconds'))}** |")
    lines.append(f"| 扫描任务吞吐（含排队） | {summary.get('scan_photos_per_second', '-')} 张/秒 |")
    lines.append(f"| 端到端吞吐 | **{summary.get('photos_per_second', '-')} 张/秒** |")
    lines.append(f"| 单张平均耗时 | {summary.get('seconds_per_photo', '-')} 秒 |")
    expected = summary.get("core_tasks_expected")
    completed = summary.get("core_tasks_completed", 0)
    if expected is None:
        minimum = summary.get("core_tasks_min_expected")
        suffix = f"（最低期望 {minimum}）" if minimum is not None else ""
        lines.append(f"| 核心任务完成 | {completed}{suffix} |")
    else:
        lines.append(f"| 核心任务完成 / 期望 | {completed} / {expected} |")
    lines.append(f"| 核心任务失败 | {summary.get('core_failed', 0)} |")
    if summary.get("scan_new_files") is not None:
        lines.append(f"| 扫描新增文件 | {summary.get('scan_new_files')} |")
    lines.append("")
    lines.append("> 总耗时从调用“添加图库”开始，到扫描任务完成且本地处理链路排空为止；")
    lines.append("> 默认暂停 AI 任务（人脸/OCR/分类/向量/视觉描述/票据识别），只测本地链路。")
    lines.append("")

    lines.append("## 各任务完成速度与耗时")
    lines.append("")
    if not tasks:
        lines.append("没有采集到任务事件。")
    else:
        lines.append(
            "| 任务类型 | 数量 | 完成 | 失败 | 排队均值 | 执行均值 | 总耗时 P50 | 总耗时 P95 | 完成速率 | 备注 |"
        )
        lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---|")
        for task in tasks:
            queue = task.get("queue_seconds") or {}
            execution = task.get("execution_seconds") or {}
            total = task.get("total_seconds") or {}
            lines.append(
                "| {type} | {count} | {completed} | {failed} | {queue} | {execution} | {p50} | {p95} | {rate} | {note} |".format(
                    type=task.get("type", "-"),
                    count=task.get("count", 0),
                    completed=task.get("completed", 0),
                    failed=task.get("failed", 0),
                    queue=fmt_seconds(queue.get("mean")),
                    execution=fmt_seconds(execution.get("mean")),
                    p50=fmt_seconds(total.get("p50")),
                    p95=fmt_seconds(total.get("p95")),
                    rate="-" if task.get("paused") else f"{task.get('throughput_tasks_per_second', '-')} 个/秒",
                    note="已暂停（AI）" if task.get("paused") else "",
                )
            )
        lines.append("")
        lines.append("说明：")
        lines.append("")
        lines.append("- `排队均值`：任务创建到开始处理；`执行均值`：开始处理到完成；总耗时 P50/P95：排队 + 执行。")
        lines.append("- 已完成任务行会被后端删除，任务耗时以 SSE 事件到达的客户端单调时钟为主；排队时间优先用数据库时间戳。")
        lines.append("- `完成速率` 的分母是整条链路耗时，因此适合横向比较任务类型，不代表单任务执行速度。")
        paused = (result.get("config") or {}).get("paused_task_types") or []
        if paused:
            lines.append(
                "- 被暂停的 AI 类型（"
                + "、".join(f"`{item}`" for item in paused)
                + "）仍会创建为 pending，但不计入本地链路排空判定，也不代表失败。"
            )
        lines.append("")

    lines.append("## 扫描任务")
    lines.append("")
    lines.append(f"- 任务 ID：`{scan.get('task_id') or '-'}`")
    lines.append(f"- 状态：`{scan.get('status') or '-'}`")
    lines.append(f"- 扫描新增文件：{scan.get('new_files', '-')}")
    lines.append(f"- 扫描删除文件：{scan.get('deleted_files', '-')}")
    if scan.get("error"):
        lines.append(f"- 错误：`{scan['error']}`")
    lines.append("")

    failures = [sample for sample in (result.get("task_samples") or []) if sample.get("status") in {"failed", "cancelled"}]
    if failures:
        lines.append("## 失败任务")
        lines.append("")
        lines.append("| 任务 ID | 类型 | 状态 | 错误 |")
        lines.append("|---|---|---|---|")
        for sample in failures[:50]:
            error = str(sample.get("error") or "").replace("|", "\\|").replace("\n", " ")
            lines.append(f"| `{sample.get('task_id')}` | {sample.get('type')} | {sample.get('status')} | {error[:200]} |")
        lines.append("")

    stuck = result.get("stuck_tasks") or []
    if stuck and status in {"stalled", "timeout"}:
        lines.append("## 卡住 / 未完成任务")
        lines.append("")
        lines.append("| 任务 ID | 类型 | 状态 | 已排队 | 已执行 |")
        lines.append("|---|---|---|---:|---:|")
        for sample in stuck[:50]:
            lines.append(
                f"| `{sample.get('task_id')}` | {sample.get('type')} | {sample.get('status')} | "
                f"{fmt_seconds(sample.get('queue_seconds'))} | {fmt_seconds(sample.get('execution_seconds'))} |"
            )
        lines.append("")
        lines.append(
            f"> 判定停滞时仍有 {len(stuck)} 个核心任务未收尾；总耗时按最后一次进度计算（"
            f"{fmt_seconds((result.get('summary') or {}).get('pipeline_seconds'))}），"
            "不是实际等待的上限时间。"
        )
        lines.append("")

    lines.append("## 环境")
    lines.append("")
    for key, label in (
        ("platform", "系统"),
        ("machine", "架构"),
        ("processor", "处理器"),
        ("cpu_count", "CPU 核数"),
        ("memory_gb", "内存 (GB)"),
        ("python", "Python"),
        ("mode", "测试模式"),
    ):
        lines.append(f"- {label}：{environment.get(key, '-')}")
    events = result.get("events") or {}
    lines.append(f"- SSE 事件数：{events.get('sse_event_count', '-')}，解析错误：{events.get('sse_parse_errors', '-')}")
    if events.get("sse_last_error"):
        lines.append(f"- SSE 最后错误：`{events['sse_last_error']}`")
    if events.get("poll_last_error"):
        lines.append(f"- 轮询最后错误：`{events['poll_last_error']}`")
    lines.append("")
    lines.append("## 复现")
    lines.append("")
    lines.append("```powershell")
    lines.append("pwsh .\\tests\\scripts\\run-perf.ps1")
    lines.append("```")
    lines.append("")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TrailSnap 文件夹扫描性能基准")
    parser.add_argument("--api-base-url", default=os.environ.get("TS_API_BASE_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--username", default=os.environ.get("TS_TEST_USERNAME", "perf-admin"))
    parser.add_argument("--password", default=os.environ.get("TS_TEST_PASSWORD", "PerfPassw0rd!123"))
    parser.add_argument(
        "--email",
        default=os.environ.get("TS_PERF_EMAIL"),
        help="空库注册首个管理员时使用的邮箱；默认按 username 生成 @example.com",
    )
    parser.add_argument("--photo-count", type=int, default=int(os.environ.get("TS_PERF_PHOTO_COUNT", "100")))
    parser.add_argument("--source-folder", default=os.environ.get("TS_PERF_SOURCE_FOLDER"))
    parser.add_argument("--report-dir", required=True)
    parser.add_argument("--work-root", default=os.environ.get("TS_PERF_WORK_ROOT"))
    parser.add_argument("--run-id", default=os.environ.get("TS_PERF_RUN_ID") or datetime.now().strftime("%Y%m%d-%H%M%S"))
    parser.add_argument("--timeout-seconds", type=float, default=float(os.environ.get("TS_PERF_TIMEOUT_SECONDS", "300")))
    parser.add_argument("--stall-seconds", type=float, default=float(os.environ.get("TS_PERF_STALL_SECONDS", "120")))
    parser.add_argument("--startup-timeout", type=float, default=float(os.environ.get("TS_PERF_STARTUP_TIMEOUT", "180")))
    parser.add_argument("--poll-interval", type=float, default=float(os.environ.get("TS_PERF_POLL_INTERVAL", "0.5")))
    parser.add_argument("--settle-seconds", type=float, default=float(os.environ.get("TS_PERF_SETTLE_SECONDS", "2.0")))
    parser.add_argument("--pause-settle-seconds", type=float, default=float(os.environ.get("TS_PERF_PAUSE_SETTLE_SECONDS", "6.0")))
    parser.add_argument("--keep-fixture", action="store_true")
    return parser


def _failure_result(args: argparse.Namespace, started_at: str, error: BaseException) -> dict[str, Any]:
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "run_id": args.run_id,
        "status": "error",
        "started_at": started_at,
        "finished_at": now_iso(),
        "environment": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "cpu_count": os.cpu_count(),
            "memory_gb": memory_gb(),
            "python": platform.python_version(),
            "git_commit": git_commit(),
            "api_base_url": args.api_base_url,
            "database": _redact_database_url(os.environ.get("TS_DB_URL")),
            "mode": os.environ.get("TS_TEST_ENV", "dev"),
        },
        "config": {
            "photo_count": args.photo_count,
            "timeout_seconds": args.timeout_seconds,
            "stall_seconds": args.stall_seconds,
            "poll_interval_seconds": args.poll_interval,
            "settle_seconds": args.settle_seconds,
        },
        "dataset": {},
        "scan": None,
        "summary": None,
        "tasks": [],
        "task_samples": [],
        "events": {},
        "error": f"{type(error).__name__}: {error}",
        "traceback": traceback.format_exc(limit=8),
        "notes": [],
    }


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.photo_count <= 0 and not args.source_folder:
        parser.error("--photo-count 必须大于 0")
    report_dir = Path(args.report_dir).resolve()
    started_at = now_iso()
    try:
        result = run_benchmark(args, report_dir)
    except Exception as error:
        # run_benchmark 内部已经尽力写报告；这里兜住“服务未就绪 / 登录失败”等
        # 发生在其 try/finally 之前的错误，保证一键入口始终有报告可看。
        result = _failure_result(args, started_at, error)
        _write_reports(report_dir, result)
    status = result.get("status")
    if status == "passed":
        return 0
    if status == "degraded":
        return 2
    if status == "timeout":
        return 3
    if status == "stalled":
        return 4
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
