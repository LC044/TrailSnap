"""2026-09-09 nightly tests for remaining backend low-coverage helpers."""
import asyncio
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

pytestmark = [pytest.mark.smoke]


def test_abort_chat_session_marks_session():
    from app.service.agent import service as agent_service

    session_id = str(uuid4())
    agent_service._aborted_sessions.pop(session_id, None)
    agent_service.abort_chat_session(session_id)
    assert agent_service._aborted_sessions[session_id] is True


def test_model_context_window_prefers_explicit_model_and_falls_back():
    from app.service.agent.service import _model_context_window

    model = SimpleNamespace(model_name="qwen-max", context_window=262144)
    connection = SimpleNamespace(id="conn-1", models=[model])
    settings = SimpleNamespace(
        analysis_connection_id="conn-default",
        analysis_model_name="analysis-model",
        connections=[connection],
    )
    assert _model_context_window(settings, connection_id="conn-1", model_name="qwen-max") == 262144

    settings_without_models = SimpleNamespace(
        analysis_connection_id="missing",
        analysis_model_name="missing-model",
        connections=[],
    )
    assert _model_context_window(settings_without_models) == 128000


def test_agent_skill_tools_list_and_report_load_errors():
    from app.service.agent.tools import get_agent_tools

    tools = {tool.name: tool for tool in get_agent_tools(str(uuid4()))}
    listed = json.loads(tools["list_skills"].func())
    assert isinstance(listed["skills"], list)

    error = json.loads(tools["load_skill"].func("definitely-not-a-skill"))
    assert "error" in error


@pytest.mark.asyncio
async def test_task_queue_manager_priority_order_and_unknown_category():
    from app.service.task_worker import TaskQueueManager

    manager = TaskQueueManager()
    await manager.put_batch("CPU", [{"id": "low"}], priority=1)
    await manager.put_batch("CPU", [{"id": "high"}], priority=10)
    await manager.put_batch("MISSING", [{"id": "ignored"}], priority=10)

    assert manager.item_count("CPU") == 2
    assert manager.qsize("MISSING") == 0
    assert manager.get_lowest_priority("CPU") == 1
    assert await manager.get_batch("CPU") == [{"id": "high"}]
    assert await manager.get_batch("CPU") == [{"id": "low"}]
    assert await manager.get_batch("MISSING") == []
    manager.task_done("CPU")


def test_day_caption_timezone_and_bounds_helpers_are_defensive():
    from app.service.moment.day_caption_service import _resolve_tz, day_bounds_utc
    from datetime import date

    assert _resolve_tz("") is not None
    assert _resolve_tz("Asia/Shanghai") is not None
    assert _resolve_tz("not/a-zone") is not None

    start, end = day_bounds_utc(date(2026, 9, 9), "ignored-for-compat")
    assert (start.hour, start.minute, start.second) == (0, 0, 0)
    assert (end - start).total_seconds() == 86400
