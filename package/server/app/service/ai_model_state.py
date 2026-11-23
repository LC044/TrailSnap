"""Check only the models needed by a batch, before reading photo files."""
import json
import threading
import time

import aiohttp
import httpx
import requests
from openai import APIStatusError, APITimeoutError
from urllib3.exceptions import ReadTimeoutError

from app.core.ai_endpoint import normalize_ai_api_url
from app.db.models.task import TaskType

WAIT_PREFIX = "等待 AI 模型："
MODEL_RETRY_REASON = f"{WAIT_PREFIX}模型尚未就绪，就绪后自动继续；请在设置 → AI 模型管理查看下载状态"
AI_SERVICE_RETRY_PREFIX = "AI 服务尚未就绪（HTTP "
INFERENCE_TIMEOUT_PREFIX = "AI 推理超时"
DEPENDENCIES = {
    TaskType.CLASSIFY_IMAGE: ("classification",),
    TaskType.RECOGNIZE_FACE: ("face",),
    TaskType.OCR: ("ocr",),
    TaskType.IMAGE_EMBEDDING: ("embedding",),
    TaskType.CLASSIFY_IMAGE_CLIP: ("embedding",),
    TaskType.RECOGNIZE_TICKET: ("ticket", "ocr"),
    TaskType.VISUAL_DESCRIPTION: ("llm",),
}
_cache = {}
_lock = threading.Lock()
_refreshing = {}
_CACHE_TTL = 5


def _snapshot_url(api_url):
    return normalize_ai_api_url(str(api_url)).rstrip("/") + "/ai/models"


def invalidate_model_state(api_url):
    """A not-ready inference response supersedes even an in-flight snapshot."""
    url = _snapshot_url(api_url)
    with _lock:
        _cache.pop(url, None)
        pending = _refreshing.pop(url, None)
        if pending is not None:
            pending.set()


def _refresh_snapshot(url, pending):
    snapshot = None
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()
        if isinstance(data, dict):
            snapshot = data
    except (requests.RequestException, ValueError):
        pass
    finally:
        with _lock:
            # Invalidation detaches the old request: it must never republish a
            # snapshot fetched before inference reported a missing model.
            if _refreshing.get(url) is pending:
                old = _cache.get(url)
                if snapshot is None:
                    snapshot = old[1] if old else {"_unavailable": True}
                if url not in _cache and len(_cache) >= 128:
                    _cache.pop(next(iter(_cache)))
                _cache[url] = (time.monotonic(), snapshot)
                _refreshing.pop(url)
            pending.set()


def model_wait_reason(snapshot, task_type):
    if snapshot.get("_unavailable") and task_type in (
        TaskType.IMAGE_EMBEDDING, TaskType.CLASSIFY_IMAGE_CLIP
    ):
        return f"{WAIT_PREFIX}AI 服务暂不可达，恢复后自动继续"
    models = {m["id"]: m for m in snapshot.get("models", [])}
    for dependency in DEPENDENCIES.get(task_type, ()):
        selection = snapshot.get("tasks", {}).get(dependency, {}).get("selected")
        model = models.get(selection)
        # Older services without the catalog keep their existing API behaviour.
        if not model or model.get("status") == "ready":
            continue
        name = model.get("name", selection)
        status = model.get("status")
        if status == "downloading":
            if model.get("downloadState") == "queued":
                return f"{WAIT_PREFIX}{name} 排队等待下载，完成后自动继续"
            return f"{WAIT_PREFIX}{name} 正在下载，完成后自动继续"
        if status == "failed":
            return f"{WAIT_PREFIX}{name} 下载失败，请到设置 → AI 模型管理重试；成功后自动继续"
        return f"{WAIT_PREFIX}{name} 尚未下载，请到设置 → AI 模型管理下载；完成后自动继续"
    return None


def get_model_wait_reason(api_url, task_type):
    if task_type not in DEPENDENCIES:
        return None
    url = _snapshot_url(api_url)
    while True:
        with _lock:
            cached = _cache.get(url)
            reason = model_wait_reason(cached[1], task_type) if cached else None
            if cached and time.monotonic() - cached[0] < _CACHE_TTL:
                return reason
            # Known-ready (or legacy catalog) batches continue while one
            # caller refreshes. Missing/downloading models still get a fresh
            # check so completed downloads can resume waiting tasks.
            background = cached is not None and reason is None
            pending = _refreshing.get(url)
            if pending is not None and background:
                return reason
            owner = pending is None
            if owner:
                pending = threading.Event()
                _refreshing[url] = pending
        # Never hold the shared lock during network IO or another query's wait.
        if owner:
            if background:
                try:
                    threading.Thread(target=_refresh_snapshot, args=(url, pending),
                                     name="ai-model-refresh", daemon=True).start()
                except RuntimeError:
                    with _lock:
                        if _refreshing.get(url) is pending:
                            _refreshing.pop(url)
                        pending.set()
                return reason
            _refresh_snapshot(url, pending)
        else:
            pending.wait()


def inference_timeout_message(detail=None):
    return f"{INFERENCE_TIMEOUT_PREFIX}（{detail}）" if detail else INFERENCE_TIMEOUT_PREFIX


def inference_timeout_error(error):
    '''Return the retry reason for an inference request that timed out.'''
    if isinstance(error, aiohttp.ClientResponseError):
        return inference_timeout_message("HTTP 504") if error.status == 504 else None
    if isinstance(error, (requests.HTTPError, httpx.HTTPStatusError, APIStatusError)):
        response = error.response
        return inference_timeout_message("HTTP 504") if response is not None and response.status_code == 504 else None
    # requests wraps timeouts while reading the response body as ConnectionError.
    if isinstance(error, requests.ConnectionError) and error.args and isinstance(error.args[0], ReadTimeoutError):
        return inference_timeout_message()
    transport_error = error.__cause__ if isinstance(error, APITimeoutError) else error
    if isinstance(transport_error, (
        aiohttp.ConnectionTimeoutError, requests.ConnectTimeout,
        httpx.ConnectTimeout, httpx.PoolTimeout, httpx.WriteTimeout,
    )):
        return None
    if isinstance(error, (TimeoutError, requests.Timeout, httpx.TimeoutException, APITimeoutError)):
        return inference_timeout_message()
    return None


async def ai_response_error(response):
    """Keep useful service details, while bounding persisted error size."""
    try:
        body = await response.text()
        try:
            detail = json.loads(body).get("detail", body)
        except (ValueError, AttributeError):
            detail = body
    except Exception:
        detail = ""
    suffix = f": {str(detail)[:1000]}" if detail else ""
    if response.status == 504:
        return inference_timeout_message("HTTP 504") + suffix
    if response.status in (502, 503):
        return f"{AI_SERVICE_RETRY_PREFIX}{response.status}），恢复后自动继续{suffix}"
    return f"AI Service error: {response.status}{suffix}"
