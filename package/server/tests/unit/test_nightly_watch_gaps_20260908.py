"""Nightly watch gap tests for 2026-09-08.

Covers five modules selected from the fresh coverage scan:

* ``app.core.logger`` -- queue setup and date-based filename switching.
* ``app.service.moment.day_caption_service`` -- sync caption normalization and empty output.
* ``app.service.agent.service`` -- successful agent executor construction and memory injection.
* ``app.service.agent.tools`` -- search summary aggregation and exception fallback.
* ``app.crud.album`` -- album deletion and shared-user creation paths.
"""

import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

import app.core.logger as logger_module
from app.crud import album as album_crud
from app.service.agent import service as agent_service
from app.service.agent.tools import _build_search_summary
from app.service.moment import day_caption_service as caption_service


pytestmark = [pytest.mark.smoke]


# ---------------------------------------------------------------------------
# app.core.logger
# ---------------------------------------------------------------------------


def test_setup_logging_writes_json_and_uses_queue_handler(monkeypatch, tmp_path):
    """setup_logging must install one queue handler and emit one JSON file line."""
    root = logging.getLogger()
    named = ["uvicorn", "uvicorn.access", "uvicorn.error", "fastapi"]
    old_handlers = {name: list(logging.getLogger(name).handlers) for name in named}
    old_root_handlers = list(root.handlers)
    monkeypatch.setattr(logger_module, "LOG_DIR", str(tmp_path))

    try:
        listener = logger_module.setup_logging(filename="nightly-watch")
        logging.getLogger("app").info(
            "watch log",
            extra={"operation": "nightly", "params": {"run": 1}, "result": "ok"},
        )
        listener.stop()

        assert any(isinstance(h, logging.handlers.QueueHandler) for h in root.handlers)
        log_files = list(tmp_path.glob("nightly-watch-*.log"))
        assert len(log_files) == 1
        import json

        payload = json.loads(log_files[0].read_text(encoding="utf-8").splitlines()[0])
        assert payload["message"] == "watch log"
        assert payload["operation"] == "nightly"
        assert payload["params"] == {"run": 1}
    finally:
        root.handlers = old_root_handlers
        for name, handlers in old_handlers.items():
            logging.getLogger(name).handlers = handlers


def test_daily_rotating_handler_emit_switches_to_today_file(tmp_path):
    handler = logger_module.DailySizeRotatingFileHandler(
        filename="rollover", log_dir=str(tmp_path), maxBytes=1024, backupCount=2
    )
    try:
        handler.current_date = date.today() - timedelta(days=1)
        record = logging.LogRecord(
            name="app.test", level=logging.INFO, pathname=__file__, lineno=1,
            msg="new day", args=(), exc_info=None,
        )
        handler.emit(record)
        expected = handler._get_filename(date.today())
        assert handler.baseFilename == expected
        assert Path(expected).exists()
        assert Path(expected).read_text(encoding="utf-8").strip() == "new day"
    finally:
        handler.close()


# ---------------------------------------------------------------------------
# app.service.moment.day_caption_service
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_caption_sync_accepts_list_content_and_strips_think():
    user_id, db, day = uuid4(), MagicMock(), date(2026, 9, 8)
    materials = {
        "_connection": SimpleNamespace(api_key="k", api_base=""),
        "_model_name": "caption-model",
        "_system_prompt": "system",
        "_user_prompt": "user",
        "_photo_count": 2,
    }
    llm = MagicMock()
    llm.invoke.return_value = SimpleNamespace(
        content=[{"type": "text", "text": '<think>hidden</think>"西湖夜色"'}]
    )
    saved = SimpleNamespace(caption="西湖夜色", model_name="caption-model")

    with patch.object(caption_service, "_prepare_context", return_value=(None, materials)), \
         patch.object(caption_service, "_build_llm", return_value=llm), \
         patch.object(caption_service.moment_crud, "upsert_caption", return_value=saved) as upsert:
        result = await caption_service.generate_caption_sync(
            user_id, db, day, "Asia/Shanghai", force=True
        )

    assert result == {
        "caption": "西湖夜色", "cached": False,
        "source": "ai", "model_name": "caption-model",
    }
    assert upsert.call_args.args[5] == "西湖夜色"


@pytest.mark.asyncio
async def test_generate_caption_sync_rejects_empty_visible_caption():
    user_id, db, day = uuid4(), MagicMock(), date(2026, 9, 8)
    materials = {
        "_connection": SimpleNamespace(api_key="k", api_base=""),
        "_model_name": "caption-model",
        "_system_prompt": "system",
        "_user_prompt": "user",
    }
    llm = MagicMock()
    llm.invoke.return_value = SimpleNamespace(content="<think>only reasoning</think>")

    with patch.object(caption_service, "_prepare_context", return_value=(None, materials)), \
         patch.object(caption_service, "_build_llm", return_value=llm), \
         patch.object(caption_service.moment_crud, "upsert_caption") as upsert:
        with pytest.raises(RuntimeError, match="LLM 返回为空"):
            await caption_service.generate_caption_sync(
                user_id, db, day, "Asia/Shanghai", force=True
            )

    upsert.assert_not_called()


# ---------------------------------------------------------------------------
# app.service.agent.service
# ---------------------------------------------------------------------------


def test_get_agent_executor_success_injects_tools_and_memory():
    user_id, session_id, db = str(uuid4()), str(uuid4()), MagicMock()
    connection = SimpleNamespace(
        id="conn-1", enable=True, api_key="key", api_base="https://ai.example/v1"
    )
    config = SimpleNamespace(
        ai=SimpleNamespace(
            analysis_connection_id="conn-1",
            analysis_model_name="watch-model",
            connections=[connection],
        )
    )
    fake_llm, fake_agent = MagicMock(), MagicMock()

    with patch.object(agent_service.config_manager, "get_user_config", return_value=config), \
         patch.object(agent_service, "FixedChatOpenAI", return_value=fake_llm) as llm_call, \
         patch.object(agent_service, "get_agent_tools", return_value=["tool"]) as tools_call, \
         patch.object(agent_service, "create_agent", return_value=fake_agent) as create_call, \
         patch("app.service.agent.memory.build_memory_prompt", return_value="长期记忆：西湖") as memory_call:
        agent, prompt = agent_service.get_agent_executor(
            user_id, session_id, db, user_input="杭州的一天"
        )

    assert agent is fake_agent
    assert "长期记忆：西湖" in prompt
    assert date.today().strftime("%Y-%m-%d") in prompt
    assert tools_call.call_args.args == (user_id,)
    assert tools_call.call_args.kwargs == {"session_id": session_id}
    assert create_call.call_args.args == (fake_llm, ["tool"])
    assert llm_call.call_args.kwargs["model"] == "watch-model"
    assert llm_call.call_args.kwargs["api_key"] == "key"
    assert llm_call.call_args.kwargs["base_url"] == "https://ai.example/v1"
    memory_call.assert_called_once_with(db, user_id, user_input="杭州的一天")


# ---------------------------------------------------------------------------
# app.service.agent.tools
# ---------------------------------------------------------------------------


def test_build_search_summary_returns_empty_when_projection_fails():
    db, filtered_query = MagicMock(), MagicMock()
    filtered_query.with_entities.side_effect = RuntimeError("projection failed")

    assert _build_search_summary(db, filtered_query, None) == {}


def test_build_search_summary_aggregates_dates_locations_and_tags():
    db, filtered_query = MagicMock(), MagicMock()
    date_query = MagicMock()
    date_query.filter.return_value.first.return_value = (
        datetime(2026, 9, 1), datetime(2026, 9, 8)
    )
    city_query = MagicMock()
    city_query.filter.return_value.group_by.return_value.order_by.return_value.limit.return_value.all.return_value = [
        ("杭州", 12), ("上海", 5)
    ]
    tag_query = MagicMock()
    tag_query.join.return_value.filter.return_value.group_by.return_value.order_by.return_value.limit.return_value.all.return_value = [
        ("旅行", 9), ("夜景", 4)
    ]
    # The function also creates nested id subqueries through db.query(...).
    db.query.side_effect = [date_query, MagicMock(), city_query, MagicMock(), tag_query, MagicMock()]

    summary = _build_search_summary(db, filtered_query, None)

    assert summary["date_range"] == ["2026-09-01", "2026-09-08"]
    assert summary["top_locations"] == {"杭州": 12, "上海": 5}
    assert summary["top_tags"] == {"旅行": 9, "夜景": 4}


# ---------------------------------------------------------------------------
# app.crud.album
# ---------------------------------------------------------------------------


def test_delete_album_deletes_existing_album_and_commits():
    db, album = MagicMock(), SimpleNamespace(id=uuid4())

    with patch.object(album_crud, "get_album", return_value=album) as get_album:
        result = album_crud.delete_album(db, album.id)

    assert result is not None
    get_album.assert_called_once_with(db, album.id)
    db.delete.assert_called_once_with(album)
    db.commit.assert_called_once()


def test_delete_album_returns_none_when_album_missing():
    db = MagicMock()

    with patch.object(album_crud, "get_album", return_value=None):
        result = album_crud.delete_album(db, uuid4())

    assert result is None
    db.delete.assert_not_called()
    db.commit.assert_not_called()


def test_create_album_resolves_shared_users_from_database():
    db, owner, shared = MagicMock(), uuid4(), uuid4()
    payload = SimpleNamespace(
        name="共享相册", description="desc", type="normal", condition=None,
        threshold=None, shared_users=[shared],
    )
    def fake_album(**kwargs):
        return SimpleNamespace(**kwargs)
    db.query.return_value.filter.return_value.all.return_value = [shared]

    with patch.object(album_crud, "Album", side_effect=fake_album):
        result = album_crud.create_album(db, payload, query_embedding=None, user_id=owner)

    assert result is not None
    assert result.shared_users == [shared]
    assert result.owner_id == owner
    db.query.return_value.filter.return_value.all.assert_called_once()
    db.add.assert_called_once_with(result)
    db.commit.assert_called_once()
    db.refresh.assert_called_once_with(result)
