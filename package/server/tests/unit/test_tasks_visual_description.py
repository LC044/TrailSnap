"""Unit tests for ``app/service/tasks/visual_description.py``.

The visual description strategy has two surfaces that don't require a real
language model:

* ``encode_image`` -- resizes an image to a target long-edge size and
  base64-encodes a JPEG.
* ``create_client`` -- validates the user's LLM settings before touching
  the network and raises ``ValueError`` for each missing / disabled piece.

Coverage:

* ``encode_image`` shrinks oversized images and emits a non-empty base64
  string.
* ``encode_image`` converts RGBA / palette PNGs to RGB before encoding.
* ``create_client`` raises when the analysis connection is not configured.
* ``create_client`` raises when the configured connection is disabled.
* ``create_client`` raises when the connection is missing an API key.
"""

import base64
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image


pytestmark = [pytest.mark.smoke, pytest.mark.module_classification]


def test_encode_image_shrinks_oversized_image(tmp_path):
    """An oversized RGBA PNG is downscaled to fit the ``max_size`` bound."""
    from app.service.tasks import visual_description as vd_mod

    src = tmp_path / "big.png"
    # 2000x1500 RGBA PNG (decorative; no need to look like a photo).
    img = Image.new("RGBA", (2000, 1500), (255, 0, 0, 128))
    img.save(src, format="PNG")

    encoded = vd_mod.encode_image(str(src), max_size=672)
    raw = base64.b64decode(encoded)
    out = Image.open(__import__("io").BytesIO(raw))
    assert out.format == "JPEG"
    # Long edge is now within the bound (with a tolerance of one pixel).
    assert max(out.size) <= 672


def test_encode_image_handles_palette_mode(tmp_path):
    """Palette PNGs are flattened to RGB before encoding."""
    from app.service.tasks import visual_description as vd_mod

    src = tmp_path / "pal.png"
    palette_img = Image.new("P", (64, 64))
    palette_img.save(src, format="PNG")

    encoded = vd_mod.encode_image(str(src), max_size=672)
    raw = base64.b64decode(encoded)
    out = Image.open(__import__("io").BytesIO(raw))
    assert out.mode == "RGB"


def test_create_client_raises_when_connection_id_missing():
    """Without an ``analysis_connection_id`` the strategy refuses to build a client."""
    from app.service.tasks import visual_description as vd_mod

    strategy = vd_mod.VisualDescriptionStrategy()

    settings = MagicMock()
    settings.analysis_connection_id = None
    settings.analysis_model_name = "some-model"

    with pytest.raises(ValueError, match="Visual Model not configured"):
        strategy.create_client(settings)


def test_create_client_raises_when_connection_disabled():
    from app.service.tasks import visual_description as vd_mod

    strategy = vd_mod.VisualDescriptionStrategy()

    connection = MagicMock()
    connection.id = "conn-1"
    connection.enable = False
    connection.api_key = "secret"

    settings = MagicMock()
    settings.analysis_connection_id = "conn-1"
    settings.analysis_model_name = "m"
    settings.connections = [connection]

    with pytest.raises(ValueError, match="disabled"):
        strategy.create_client(settings)


def test_create_client_raises_when_connection_missing_api_key():
    from app.service.tasks import visual_description as vd_mod

    strategy = vd_mod.VisualDescriptionStrategy()

    connection = MagicMock()
    connection.id = "conn-1"
    connection.enable = True
    connection.api_key = ""

    settings = MagicMock()
    settings.analysis_connection_id = "conn-1"
    settings.analysis_model_name = "m"
    settings.connections = [connection]

    with pytest.raises(ValueError, match="api_key"):
        strategy.create_client(settings)


def test_create_client_raises_when_connection_not_found():
    """A connection id that doesn``t match any entry in ``connections`` is rejected."""
    from app.service.tasks import visual_description as vd_mod

    strategy = vd_mod.VisualDescriptionStrategy()

    settings = MagicMock()
    settings.analysis_connection_id = "missing-id"
    settings.analysis_model_name = "m"
    settings.connections = []

    with pytest.raises(ValueError, match="not found"):
        strategy.create_client(settings)


def test_create_client_uses_visual_timeout_without_nested_retries():
    """Slow local inference gets five minutes; task retries stay worker-owned."""
    from app.service.tasks import visual_description as vd_mod

    strategy = vd_mod.VisualDescriptionStrategy()
    connection = MagicMock(
        id="conn-1",
        enable=True,
        api_key="secret",
        api_base="http://ai:8001/v1",
    )
    settings = MagicMock(
        analysis_connection_id="conn-1",
        analysis_model_name="vision-model",
        connections=[connection],
    )

    with patch("langchain_openai.ChatOpenAI") as chat_openai:
        strategy.create_client(settings)

    kwargs = chat_openai.call_args.kwargs
    assert kwargs["timeout"] == 300
    assert kwargs["max_retries"] == 0
    assert strategy.timeout == 360


def test_parse_visual_result_accepts_json_wrapped_in_prose():
    """A valid object can be recovered without another model request."""
    from app.service.tasks import visual_description as vd_mod

    result = vd_mod.parse_visual_result(
        '结果如下：\n{"description":"照片", "tags":[], "memory_score":60, '
        '"beauty_score":70, "reason":"清晰", "narrative":"值得留存"}\n完成'
    )

    assert result["description"] == "照片"
    assert result["beauty_score"] == 70


def test_parse_visual_result_rejects_missing_or_invalid_fields():
    """Syntactically valid JSON still has to satisfy the storage schema."""
    from app.service.tasks import visual_description as vd_mod

    with pytest.raises(vd_mod.VisualDescriptionFormatError, match="缺少字段"):
        vd_mod.parse_visual_result('{"description": "照片"}')

    with pytest.raises(vd_mod.VisualDescriptionFormatError, match="0~100"):
        vd_mod.parse_visual_result(
            '{"description":"照片", "tags":[], "memory_score":101, '
            '"beauty_score":70, "reason":"清晰", "narrative":"值得留存"}'
        )


@pytest.mark.asyncio
async def test_multi_image_request_saves_results_by_number_and_isolates_missing_outputs(monkeypatch):
    from app.core.config_manager import AISettings
    from app.db.models.task import TaskType
    from app.service.tasks import visual_description as vd_mod

    strategy = vd_mod.VisualDescriptionStrategy()
    tasks = [
        SimpleNamespace(id=i, owner_id="owner", payload={"photo_id": f"photo-{i}"})
        for i in range(1, 4)
    ]
    settings = AISettings(analysis_connection_id="external", analysis_images_per_request=4)
    sample = {"description": "第一张", "tags": [], "memory_score": 50,
              "beauty_score": 60, "reason": "清晰", "narrative": "记忆"}
    response = SimpleNamespace(content=json.dumps({
        "3": {**sample, "description": "第三张"}, "1": sample,
    }))
    client = SimpleNamespace(ainvoke=AsyncMock(return_value=response))
    saved = {}

    def save(_db, photo_id, result, _payload):
        saved[photo_id] = result["description"]
        return {"status": "completed"}

    monkeypatch.setattr(vd_mod.config_manager, "get_user_config", lambda *_: SimpleNamespace(ai=settings))
    monkeypatch.setattr(strategy, "create_client", lambda _: client)
    monkeypatch.setattr(strategy, "_task_photo", lambda task, _: (
        SimpleNamespace(id=task.payload["photo_id"], image_type="normal"), None
    ))
    monkeypatch.setattr(strategy, "_image_content", lambda photo, _, **kwargs: [
        {"type": "text", "text": photo.id},
        {"type": "image_url", "image_url": {"url": photo.id}},
    ])
    monkeypatch.setattr(strategy, "_save_result", save)

    results = await strategy.process_batch(None, tasks, MagicMock())

    client.ainvoke.assert_awaited_once()
    parts = client.ainvoke.await_args.args[0][1]["content"]
    assert [part["image_url"]["url"] for part in parts if part["type"] == "image_url"] == [
        "photo-1", "photo-2", "photo-3",
    ]
    assert saved == {"photo-1": "第一张", "photo-3": "第三张"}
    assert results[1]["retry_as_single"] is True
    assert [(result["task_id"], result["task_type"], result["status"]) for result in results] == [
        (1, TaskType.VISUAL_DESCRIPTION, "completed"),
        (2, TaskType.VISUAL_DESCRIPTION, "failed"),
        (3, TaskType.VISUAL_DESCRIPTION, "completed"),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("connection", ["builtin", "external"])
async def test_visual_request_timeout_does_not_trigger_format_fallback(monkeypatch, connection):
    import httpx
    from openai import APITimeoutError

    from app.core.config_manager import AISettings
    from app.db.models.task import TaskType
    from app.service.ai_model_state import INFERENCE_TIMEOUT_PREFIX
    from app.service.tasks import visual_description as vd_mod

    strategy = vd_mod.VisualDescriptionStrategy()
    settings = AISettings(analysis_connection_id=connection, analysis_images_per_request=2)
    error = APITimeoutError(httpx.Request("POST", "http://ai/v1/chat/completions"))
    error.__cause__ = httpx.ReadTimeout("read timed out")
    client = SimpleNamespace(ainvoke=AsyncMock(side_effect=error))
    monkeypatch.setattr(strategy, "create_client", lambda _: client)
    monkeypatch.setattr(strategy, "_image_content", lambda *_, **__: [{"type": "text", "text": "photo"}])
    db = MagicMock()
    if connection == "builtin":
        photo = SimpleNamespace(id="photo", owner_id="owner", image_type="normal")
        results = [await strategy.process_single_photo(None, photo, db, settings)]
    else:
        tasks = [
            SimpleNamespace(id=i, type=TaskType.VISUAL_DESCRIPTION, owner_id="owner",
                            payload={"photo_id": f"photo-{i}"})
            for i in range(2)
        ]
        monkeypatch.setattr(vd_mod.config_manager, "get_user_config", lambda *_: SimpleNamespace(ai=settings))
        monkeypatch.setattr(strategy, "_task_photo", lambda task, _: (
            SimpleNamespace(id=task.payload["photo_id"], image_type="normal"), None
        ))
        results = await strategy.process_batch(None, tasks, db)

    client.ainvoke.assert_awaited_once()
    assert len(results) == (1 if connection == "builtin" else 2)
    assert all(result["status"] == "failed" and result["error"] == INFERENCE_TIMEOUT_PREFIX
               and not result.get("retry_as_single") for result in results)


def test_batch_prompt_keeps_analysis_criteria_in_the_shared_prefix():
    from os.path import commonprefix

    from app.service.tasks.visual_description import _batch_prompt

    criteria = '按照片清晰度和记录价值评分。'
    prompt = f'{criteria}\n请严格只输出 JSON，格式如下：\n{{"description":"单张示例"}}'
    short = _batch_prompt(prompt, ['1', '2'])
    full = _batch_prompt(prompt, ['1', '2', '3', '4'])

    assert commonprefix([short, full]).endswith('本次共有 ')
    assert criteria in commonprefix([short, full])
    assert '单张示例' not in short
    for result, count in [(short, 2), (full, 4)]:
        assert f'本次共有 {count} 张照片' in result
        assert list(json.loads(result.split('输出结构示例：\n')[1])) == [str(i) for i in range(1, count + 1)]


def test_external_visual_dispatch_groups_by_owner_and_priority(monkeypatch):
    from datetime import datetime

    from app.core.config_manager import AISettings, config_manager
    from app.db.models.task import INTERACTIVE_TASK_PRIORITY, TaskType
    from app.service import task_worker
    from app.service.tasks.visual_description import VISUAL_SINGLE_REQUEST_KEY

    task_type = TaskType.VISUAL_DESCRIPTION
    urgent = INTERACTIVE_TASK_PRIORITY
    tasks = [
        SimpleNamespace(id=i, owner_id=owner, type=task_type, priority=priority,
                        payload={"photo_id": i} if i != 7 else {})
        for i, owner, priority in [
            (1, "a", urgent), (2, "a", urgent), (3, "a", 1), (4, "a", 1),
            (5, "b", 1), (6, "builtin", 1), (7, "a", 1),
        ]
    ]
    tasks.extend(
        SimpleNamespace(id=i, owner_id="a", type=task_type, priority=1,
                        payload={"photo_id": i, VISUAL_SINGLE_REQUEST_KEY: True})
        for i in (8, 9)
    )
    db = MagicMock()
    importing = MagicMock()
    importing.filter.return_value.first.return_value = None
    heads = MagicMock()
    heads.filter.return_value = heads
    heads.order_by.return_value = heads
    heads.first.return_value = (task_type, urgent, datetime.now())
    photos = MagicMock()
    photos.filter.return_value = photos
    photos.order_by.return_value.limit.return_value.all.return_value = tasks
    db.query.side_effect = [importing, heads, photos]
    monkeypatch.setattr(task_worker, "SessionLocal", lambda: db)
    monkeypatch.setattr(task_worker, "is_ci", lambda: False)
    monkeypatch.setattr(config_manager, "get_user_config", lambda owner, _: SimpleNamespace(
        ai=AISettings(
            analysis_connection_id="builtin" if owner == "builtin" else "external",
            analysis_concurrency=16, analysis_images_per_request=2,
        )
    ))

    batches = task_worker.TaskWorker()._fetch_tasks_to_queues_sync([task_type], {})

    assert [[task["id"] for task in batch] for _, batch in batches] == [[1, 2], [3, 4], [5], [7], [8], [9], [6]]
    assert batches[0][1][0]["request_concurrency"] == 16
    assert batches[0][1][0]["resource_key"] != batches[2][1][0]["resource_key"]
    assert batches[-1][1][0]["resource_key"] == "local_llm"


def test_missing_batch_result_requeues_only_the_failed_photo(monkeypatch):
    from app.db.models.task import TaskStatus, TaskType
    from app.service import ai_model_state, task_worker
    from app.service.tasks.visual_description import VISUAL_SINGLE_REQUEST_KEY

    task_type = TaskType.VISUAL_DESCRIPTION
    tasks = [SimpleNamespace(id=i, type=task_type, payload={"photo_id": i},
                             priority=1, status=TaskStatus.PENDING) for i in (1, 2)]
    results = [
        {"task_id": 1, "status": TaskStatus.COMPLETED},
        {"task_id": 2, "status": TaskStatus.FAILED, "error": "missing photo", "retry_as_single": True},
    ]
    strategy = SimpleNamespace(task_category="AI", resource_key="visual_llm",
                               timeout=30, process_batch=AsyncMock(return_value=results))
    worker = task_worker.TaskWorker()
    monkeypatch.setattr(worker, "_publish_task_row", lambda _: None)
    monkeypatch.setattr(task_worker, "SessionLocal", MagicMock())
    monkeypatch.setattr(ai_model_state, "DEPENDENCIES", {})
    monkeypatch.setattr(task_worker.crud_task, "get_tasks_by_ids", lambda *_: tasks)
    monkeypatch.setattr(task_worker.TaskStrategyFactory, "get_strategy", lambda _: strategy)

    terminal_results, _ = worker._execute_batch_sync([{"id": task.id, "type": task_type} for task in tasks])

    assert terminal_results == [results[0]]
    assert tasks[0].payload == {"photo_id": 1}
    assert tasks[1].status == TaskStatus.PENDING
    assert tasks[1].payload == {"photo_id": 2, VISUAL_SINGLE_REQUEST_KEY: True}


@pytest.mark.parametrize("concurrency", [2, 4, 8, 16])
@pytest.mark.asyncio
async def test_external_visual_admission_uses_configured_request_concurrency(monkeypatch, concurrency):
    import asyncio
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event, Lock

    from app.db.models.task import TaskType
    from app.service.task_worker import TaskWorker

    loop = asyncio.get_running_loop()
    worker = TaskWorker()
    worker.running = True
    reached_limit = asyncio.Event()
    release = Event()
    lock = Lock()
    active = peak = 0

    def execute(_batch):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
            if active == concurrency:
                loop.call_soon_threadsafe(reached_limit.set)
        release.wait(timeout=5)
        with lock:
            active -= 1
        return [], None

    monkeypatch.setattr(worker, "_execute_batch_sync", execute)
    for i in range(concurrency + 1):
        await worker.queue_manager.put_batch("AI", [{
            "id": i, "type": TaskType.VISUAL_DESCRIPTION, "priority": 1,
            "resource_key": "external_visual:owner", "request_concurrency": concurrency,
        }])

    with ThreadPoolExecutor(max_workers=17) as worker.batch_pool:
        consumer = asyncio.create_task(worker.consumer_loop("AI"))
        try:
            await asyncio.wait_for(reached_limit.wait(), timeout=5)
            assert worker._resource_limiter("external_visual:owner").in_use == concurrency
        finally:
            release.set()
            await asyncio.wait_for(worker.queue_manager.queues["AI"].join(), timeout=5)
            consumer.cancel()
            await consumer
    assert peak == concurrency
