"""2026-09-12 nightly tests for the five highest-priority backend gaps.

Targets selected from the current Cobertura report:
agent session-title generation, task-worker interactive batching, day-caption
cached/error streaming, settings background filtering, and image thumbnail
persistence. All database and LLM dependencies are mocked; thumbnail tests use
pytest's temporary directory only.
"""
import json
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from PIL import Image

pytestmark = [pytest.mark.smoke]


def _ctx(db):
    @contextmanager
    def _cm():
        yield db

    return MagicMock(side_effect=_cm)


# ---------------------------------------------------------------------------
# app/service/agent/service.py -- session title generation
# ---------------------------------------------------------------------------


def test_generate_session_title_task_updates_stripped_title():
    from app.service.agent import service as agent_service

    user_id = str(uuid4())
    db = MagicMock()
    session = SimpleNamespace(id=uuid4())
    connection = SimpleNamespace(
        id="conn-1", enable=True, api_key="key", api_base="http://llm.test/v1"
    )
    settings = SimpleNamespace(
        ai=SimpleNamespace(
            analysis_connection_id="conn-1",
            analysis_model_name="qwen-max",
            connections=[connection],
        )
    )
    llm = MagicMock()
    llm.invoke.return_value = SimpleNamespace(content='  "西湖旅行"  ')

    with (
        patch.object(agent_service, "SessionLocal", _ctx(db)),
        patch.object(agent_service.config_manager, "get_user_config", return_value=settings),
        patch("langchain_openai.ChatOpenAI", return_value=llm) as chat_openai,
        patch("app.crud.agent.get_session", return_value=session),
        patch("app.crud.agent.update_session") as update_session,
    ):
        title = agent_service.generate_session_title_task(user_id, "session-1", "帮我整理西湖照片")

    assert title == "西湖旅行"
    chat_openai.assert_called_once()
    update_session.assert_called_once()
    assert update_session.call_args.args[0] is db
    assert update_session.call_args.args[1] is session


def test_generate_session_title_task_returns_none_without_model_config():
    from app.service.agent import service as agent_service

    user_id = uuid4()
    db = MagicMock()
    settings = SimpleNamespace(
        ai=SimpleNamespace(
            analysis_connection_id="",
            analysis_model_name="",
            connections=[],
        )
    )

    with (
        patch.object(agent_service, "SessionLocal", _ctx(db)),
        patch.object(agent_service.config_manager, "get_user_config", return_value=settings),
        patch.object(agent_service, "ChatOpenAI") as chat_openai,
    ):
        title = agent_service.generate_session_title_task(user_id, "session-1", "hello")

    assert title is None
    chat_openai.assert_not_called()


# ---------------------------------------------------------------------------
# app/service/task_worker.py -- prefetch interactive batches
# ---------------------------------------------------------------------------


def test_fetch_tasks_keeps_interactive_work_in_single_item_batches():
    from app.db.models.task import TaskType
    from app.service import task_worker

    worker = task_worker.TaskWorker.__new__(task_worker.TaskWorker)
    worker.paused_categories = set()
    worker._prefetch_limit = lambda category: 8

    task_a = SimpleNamespace(
        id=uuid4(), type=TaskType.PROCESS_BASIC,
        priority=task_worker.INTERACTIVE_TASK_PRIORITY, owner_id=None,
    )
    task_b = SimpleNamespace(
        id=uuid4(), type=TaskType.PROCESS_BASIC,
        priority=task_worker.INTERACTIVE_TASK_PRIORITY + 1, owner_id=None,
    )

    top_query = MagicMock()
    top_query.filter.return_value = top_query
    top_query.order_by.return_value = top_query
    top_query.first.return_value = (TaskType.PROCESS_BASIC, task_b.priority)

    task_query = MagicMock()
    task_query.filter.return_value = task_query
    task_query.order_by.return_value = task_query
    task_query.limit.return_value = task_query
    task_query.all.return_value = [task_a, task_b]

    db = MagicMock()
    db.query.side_effect = [top_query, task_query]
    strategy = SimpleNamespace(task_category="CPU", resource_key="cpu")

    with (
        patch.object(task_worker, "SessionLocal", return_value=db),
        patch.object(task_worker.TaskStrategyFactory, "get_strategy", return_value=strategy),
    ):
        batches = task_worker.TaskWorker._fetch_tasks_to_queues_sync(
            worker, [TaskType.PROCESS_BASIC], {"CPU": 0}
        )

    assert batches == [
        ("CPU", [{"id": task_a.id, "type": TaskType.PROCESS_BASIC,
                  "priority": task_a.priority, "resource_key": "cpu"}]),
        ("CPU", [{"id": task_b.id, "type": TaskType.PROCESS_BASIC,
                  "priority": task_b.priority, "resource_key": "cpu"}]),
    ]
    db.close.assert_called_once()


# ---------------------------------------------------------------------------
# app/service/moment/day_caption_service.py -- sync cache and stream errors
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_caption_sync_returns_cached_caption_without_llm():
    from app.service.moment import day_caption_service as svc

    db = MagicMock()
    user_id = uuid4()

    with patch.object(svc, "_prepare_context", return_value=("已有文案", {})):
        result = await svc.generate_caption_sync(
            user_id, db, date(2026, 9, 12), "Asia/Shanghai"
        )

    assert result == {"caption": "已有文案", "cached": True, "source": "existing"}


@pytest.mark.asyncio
async def test_generate_caption_stream_yields_value_error_and_done():
    from app.service.moment import day_caption_service as svc

    def _fail(*args, **kwargs):
        raise ValueError("这一天没有照片，无法生成文案。")

    db = MagicMock()
    user_id = uuid4()

    with patch.object(svc, "_prepare_context", side_effect=_fail):
        chunks = [
            chunk async for chunk in svc.generate_caption_stream(
                user_id, db, date(2026, 9, 12), "Asia/Shanghai"
            )
        ]

    assert len(chunks) == 2
    payload = json.loads(chunks[0].removeprefix("data: ").removesuffix("\n\n"))
    assert payload == {"error": "这一天没有照片，无法生成文案。"}
    assert chunks[1] == "data: [DONE]\n\n"


# ---------------------------------------------------------------------------
# app/api/settings.py -- background filter task
# ---------------------------------------------------------------------------


def test_apply_filter_task_bg_skips_when_filter_disabled_and_no_exclusions():
    from app.api import settings as settings_api

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(settings={})
    merged = SimpleNamespace(filter=SimpleNamespace(enable=False, exclude_folders=[]))

    with (
        patch.object(settings_api, "SessionLocal", return_value=db),
        patch.object(settings_api.config_manager, "merge_user_settings", return_value=merged),
    ):
        result = settings_api.apply_filter_task_bg(str(uuid4()))

    assert result is None
    db.commit.assert_not_called()
    db.close.assert_called_once()


def test_apply_filter_task_bg_rolls_back_and_closes_on_error():
    from app.api import settings as settings_api

    db = MagicMock()

    with (
        patch.object(settings_api, "SessionLocal", return_value=db),
        patch.object(
            settings_api.config_manager,
            "merge_user_settings",
            side_effect=RuntimeError("config unavailable"),
        ),
    ):
        settings_api.apply_filter_task_bg(str(uuid4()))

    db.rollback.assert_called_once()
    db.close.assert_called_once()


# ---------------------------------------------------------------------------
# app/service/storage.py -- thumbnail generation
# ---------------------------------------------------------------------------


def test_generate_thumbnail_saves_preview_and_thumb_webp(tmp_path, monkeypatch):
    from app.service import storage

    user_id = uuid4()
    file_id = uuid4()
    monkeypatch.setattr(storage, "_get_storage_root", lambda uid, db=None: str(tmp_path))
    source = tmp_path / "source.png"
    Image.new("RGB", (128, 96), (24, 120, 180)).save(source)
    config = SimpleNamespace(
        preview_size=64, preview_quality=85,
        thumbnail_size=32, thumbnail_quality=80,
    )

    preview_path = storage.generate_thumbnail(
        user_id, str(source), file_id, config=config
    )

    compact = str(file_id).replace("-", "")
    base = tmp_path / "thumbnails" / compact[:2] / compact[2:4]
    assert Path(preview_path) == base / f"{compact}.webp"
    assert (base / f"{compact}-thumb.webp").is_file()
    with Image.open(preview_path) as preview:
        assert max(preview.size) <= 64
    with Image.open(base / f"{compact}-thumb.webp") as thumb:
        assert max(thumb.size) <= 32


def test_generate_thumbnail_returns_none_for_unsupported_extension(tmp_path, monkeypatch):
    from app.service import storage

    monkeypatch.setattr(storage, "_get_storage_root", lambda uid, db=None: str(tmp_path))
    config = SimpleNamespace(
        preview_size=64, preview_quality=85,
        thumbnail_size=32, thumbnail_quality=80,
    )

    result = storage.generate_thumbnail(
        uuid4(), str(tmp_path / "document.txt"), uuid4(),
        image_obj=Image.new("RGB", (16, 16)), config=config,
    )

    assert result is None
    assert not (tmp_path / "thumbnails").exists()






