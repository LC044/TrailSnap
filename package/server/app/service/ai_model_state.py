"""Check only the models needed by a batch, before reading photo files."""
import json
import threading
import time

import requests

from app.db.models.task import TaskType

WAIT_PREFIX = "等待 AI 模型："
DEPENDENCIES = {
    TaskType.CLASSIFY_IMAGE: ("classification",),
    TaskType.RECOGNIZE_FACE: ("face",),
    TaskType.OCR: ("ocr",),
    TaskType.IMAGE_EMBEDDING: ("embedding",),
    TaskType.RECOGNIZE_TICKET: ("ticket", "ocr"),
    TaskType.VISUAL_DESCRIPTION: ("llm",),
}
_cache = {}
_lock = threading.Lock()


def model_wait_reason(snapshot, task_type):
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
    url = str(api_url).rstrip("/") + "/ai/models"
    # Share a short-lived snapshot across concurrent batches, including failures.
    with _lock:
        cached = _cache.get(url)
        if cached and time.monotonic() - cached[0] < 5:
            snapshot = cached[1]
        else:
            try:
                response = requests.get(url, timeout=5)
                response.raise_for_status()
                snapshot = response.json()
                if not isinstance(snapshot, dict):
                    snapshot = {}
            except (requests.RequestException, ValueError):
                snapshot = {}
            if len(_cache) >= 128:
                _cache.clear()
            _cache[url] = (time.monotonic(), snapshot)
    return model_wait_reason(snapshot, task_type)


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
    return f"AI Service error: {response.status}{suffix}"
