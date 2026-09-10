"""2026-09-10 nightly tests for remaining high-priority backend gaps.

The selected modules come from the current coverage report:
agent tool wrappers, agent summary helpers, task-worker pressure monitoring,
and day-caption prompt/config helpers.
"""
import asyncio
import json
from contextlib import contextmanager
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

pytestmark = [pytest.mark.smoke]


def _ctx(db):
    @contextmanager
    def _cm():
        yield db

    return MagicMock(side_effect=_cm)


def _tool(name, user_id, session_id="session-1"):
    from app.service.agent.tools import get_agent_tools
    for tool in get_agent_tools(user_id, session_id):
        if tool.name == name:
            return tool
    raise AssertionError(f"tool {name} not found")


# ---------------------------------------------------------------------------
# app/service/agent/tools.py -- newly added wrapper surface
# ---------------------------------------------------------------------------


def test_agent_context_and_search_wrappers_delegate_to_safe_helpers():
    from app.service.agent import tools as tools_module

    user_id = str(uuid4())
    db = MagicMock()
    with (
        patch.object(tools_module, "SessionLocal", _ctx(db)),
        patch.object(tools_module, "photo_contexts", return_value=[{"photo_id": "p1"}]) as photo_contexts,
        patch.object(tools_module, "search_ocr_rows", return_value=[{"text": "G1024"}]) as search_ocr_rows,
    ):
        context = json.loads(_tool("get_photo_context", user_id).func(photo_ids=["p1"]))
        ocr = json.loads(_tool("search_ocr", user_id).func(query="G1024", limit=5))

    photo_contexts.assert_called_once_with(db, user_id, ["p1"])
    search_ocr_rows.assert_called_once_with(db, user_id, "G1024", 5)
    assert context == {"photos": [{"photo_id": "p1"}]}
    assert ocr == {"results": [{"text": "G1024"}]}


def test_agent_ticket_and_timeline_wrappers_return_domain_payloads():
    from app.service.agent import tools as tools_module

    user_id = str(uuid4())
    db = MagicMock()
    tickets = [{"type": "train", "departure": "武汉"}]
    timeline = {"days": [{"day": "2026-09-10", "locations": ["杭州"]}]}

    with (
        patch.object(tools_module, "SessionLocal", _ctx(db)),
        patch.object(tools_module, "trip_tickets", return_value=tickets) as trip_tickets_mock,
        patch.object(tools_module, "travel_timeline", return_value=timeline) as timeline_mock,
    ):
        ticket_payload = json.loads(_tool("get_trip_tickets", user_id).func("2026-09-01", "2026-09-10"))
        timeline_payload = json.loads(_tool("get_travel_timeline", user_id).func("2026-09-01", "2026-09-10"))

    trip_tickets_mock.assert_called_once_with(db, user_id, "2026-09-01", "2026-09-10")
    timeline_mock.assert_called_once_with(db, user_id, "2026-09-01", "2026-09-10")
    assert ticket_payload == {"tickets": tickets}
    assert timeline_payload == timeline


def test_discover_trips_wrapper_returns_result_and_date_error():
    from app.service.agent import tools as tools_module

    user_id = str(uuid4())
    db = MagicMock()
    result = {"candidates": [{"title": "杭州两日"}]}

    with (
        patch.object(tools_module, "SessionLocal", _ctx(db)),
        patch.object(tools_module, "discover_travel_periods", return_value=result) as discover,
    ):
        assert json.loads(_tool("discover_trips", user_id).func("2026-09-01", "2026-09-10", 12, 8)) == result
    discover.assert_called_once_with(db, user_id, "2026-09-01", "2026-09-10", 12, 8)

    with (
        patch.object(tools_module, "SessionLocal", _ctx(db)),
        patch.object(tools_module, "discover_travel_periods", side_effect=ValueError("bad date")),
    ):
        error = json.loads(_tool("discover_trips", user_id).func("bad", None))
    assert error == {"error": "日期格式必须为 YYYY-MM-DD"}


def test_album_health_wrapper_returns_report_and_validation_error():
    from app.service.agent import tools as tools_module

    user_id = str(uuid4())
    db = MagicMock()
    report = {"summary": {"missing_time": 2}}

    with (
        patch.object(tools_module, "SessionLocal", _ctx(db)),
        patch.object(tools_module, "album_health_report", return_value=report) as health,
    ):
        assert json.loads(_tool("inspect_album_health", user_id).func("album-1", 4)) == report
    health.assert_called_once_with(db, user_id, "album-1", 4)

    with (
        patch.object(tools_module, "SessionLocal", _ctx(db)),
        patch.object(tools_module, "album_health_report", side_effect=ValueError("album not found")),
    ):
        error = json.loads(_tool("inspect_album_health", user_id).func("missing"))
    assert error == {"error": "album not found"}


def test_view_photos_caps_input_and_normalizes_invalid_size():
    from app.service.agent import tools as tools_module

    user_id = str(uuid4())
    db = MagicMock()
    photo_ids = [f"p{i}" for i in range(20)]
    contexts = [{"photo_id": pid, "thumbnail_url": f"/t/{pid}", "description": None, "quality_score": None}
                for pid in photo_ids[:16]]

    with (
        patch.object(tools_module, "SessionLocal", _ctx(db)),
        patch.object(tools_module, "photo_contexts", return_value=contexts) as photo_contexts,
    ):
        payload = json.loads(_tool("view_photos", user_id).func(photo_ids, size="huge"))

    photo_contexts.assert_called_once_with(db, user_id, photo_ids[:16])
    assert payload["mode"] == "multimodal_gallery"
    assert payload["size"] == "small"
    assert len(payload["photos"]) == 16
    assert payload["photos"][0]["photo_id"] == "p0"


def test_contact_sheet_and_representative_photo_wrappers_delegate():
    from app.service.agent import tools as tools_module

    user_id = str(uuid4())
    db = MagicMock()
    sheet = [{"photo_id": "p1", "index": 1}]
    representatives = [{"photo_id": "p2", "reason": "quality"}]

    with (
        patch.object(tools_module, "SessionLocal", _ctx(db)),
        patch.object(tools_module, "contact_sheet_content", return_value=sheet) as contact_sheet,
        patch.object(tools_module, "select_representatives", return_value=representatives) as select,
    ):
        assert _tool("create_contact_sheet", user_id).func(["p1"]) == sheet
        payload = json.loads(_tool("select_representative_photos", user_id).func(["p1", "p2"], 1))

    contact_sheet.assert_called_once_with(db, user_id, ["p1"])
    select.assert_called_once_with(db, user_id, ["p1", "p2"], 1)
    assert payload == {"selected": representatives, "requested": 1, "returned": 1}


def test_artifact_draft_rejects_unsupported_type_and_creates_draft():
    from app.service.agent import tools as tools_module

    user_id = str(uuid4())
    assert json.loads(_tool("create_artifact_draft", user_id).func("unknown", "t", {}, [])) == {
        "error": "unsupported artifact_type"
    }

    row = SimpleNamespace(
        id=uuid4(), artifact_type="travel_story", title="杭州旅行",
        status="draft", source_photo_ids=["p1"],
    )
    db = MagicMock()
    with (
        patch.object(tools_module, "SessionLocal", _ctx(db)),
        patch.object(tools_module, "create_artifact", return_value=row) as create_artifact,
    ):
        payload = json.loads(_tool("create_artifact_draft", user_id, "session-9").func(
            "travel_story", "杭州旅行", {"summary": "s"}, ["p1", "p2"], ["t1"],
        ))
    create_artifact.assert_called_once_with(
        db, user_id, "session-9", "travel_story", "杭州旅行", {"summary": "s"}, ["p1", "p2"], ["t1"]
    )
    assert payload["artifact"]["id"] == str(row.id)
    assert payload["artifact"]["photo_ids"] == ["p1"]


def test_artifact_html_and_context_wrappers_handle_success_and_value_error():
    from app.service.agent import tools as tools_module

    user_id = str(uuid4())
    db = MagicMock()
    row = SimpleNamespace(
        id=uuid4(), artifact_type="travel_story", title="杭州旅行",
        status="html_ready", source_photo_ids=["p1"],
    )

    with (
        patch.object(tools_module, "SessionLocal", _ctx(db)),
        patch.object(tools_module, "save_artifact_html", return_value=row) as save_html,
        patch.object(tools_module, "artifact_context", return_value={"id": str(row.id)}) as context,
    ):
        saved = json.loads(_tool("save_artifact_html_page", user_id).func("a1", "<html></html>", "editorial", "color", True))
        read = json.loads(_tool("get_artifact_context", user_id).func("a1"))

    save_html.assert_called_once_with(db, user_id, "a1", "<html></html>", "editorial", "color", True)
    context.assert_called_once_with(db, user_id, "a1")
    assert saved["artifact"]["has_html"] is True
    assert read == {"id": str(row.id)}

    with (
        patch.object(tools_module, "SessionLocal", _ctx(db)),
        patch.object(tools_module, "save_artifact_html", side_effect=ValueError("invalid html")),
        patch.object(tools_module, "artifact_context", side_effect=ValueError("not found")),
    ):
        save_error = json.loads(_tool("save_artifact_html_page", user_id).func("a1", "frag"))
        context_error = json.loads(_tool("get_artifact_context", user_id).func("missing"))
    assert save_error == {"error": "invalid html"}
    assert context_error == {"error": "not found"}


def test_propose_album_organization_returns_plan_and_value_error():
    from app.service.agent import tools as tools_module

    user_id = str(uuid4())
    db = MagicMock()
    row = SimpleNamespace(
        id=uuid4(), plan_type="organize_album", title="杭州旅行",
        summary="整理照片", status="proposed", preview={"photo_count": 2},
    )

    with (
        patch.object(tools_module, "SessionLocal", _ctx(db)),
        patch.object(tools_module, "propose_album_plan", return_value=row) as propose,
    ):
        payload = json.loads(_tool("propose_album_organization", user_id, "session-9").func(
            "杭州旅行", ["p1", "p2"], description="desc", cover_photo_id="p1",
            tags=["旅行"], album_id="a1", artifact_id="art1", summary="sum",
        ))
    propose.assert_called_once_with(
        db, user_id, "session-9", "杭州旅行", "desc", ["p1", "p2"], "p1", ["旅行"],
        album_id="a1", artifact_id="art1", summary="sum",
    )
    assert payload["action_plan"]["plan_type"] == "organize_album"

    with (
        patch.object(tools_module, "SessionLocal", _ctx(db)),
        patch.object(tools_module, "propose_album_plan", side_effect=ValueError("cover missing")),
    ):
        error = json.loads(_tool("propose_album_organization", user_id).func("bad", ["p1"], cover_photo_id="missing"))
    assert error == {"error": "cover missing"}


# ---------------------------------------------------------------------------
# app/service/agent/service.py -- summary helper branches
# ---------------------------------------------------------------------------


def test_messages_to_text_includes_user_ai_and_serializes_non_string_content():
    from app.service.agent import service as agent_service

    text = agent_service._messages_to_text([
        HumanMessage(content="你好"),
        AIMessage(content=[{"type": "text", "text": "你好呀"}]),
        SystemMessage(content="ignored"),
    ])
    assert "用户：你好" in text
    assert "助手：" in text
    assert '"text": "你好呀"' in text
    assert "ignored" not in text


def test_get_summary_llm_validates_config_and_builds_chat_model():
    from app.service.agent import service as agent_service

    def config(ai):
        return SimpleNamespace(ai=ai)

    connection = SimpleNamespace(id="conn", enable=True, api_key="sk", api_base="https://api.example.com/v1")
    valid_ai = SimpleNamespace(
        analysis_connection_id="conn", analysis_model_name="qwen-max", connections=[connection]
    )
    missing_ai = SimpleNamespace(analysis_connection_id="", analysis_model_name="", connections=[])
    disabled_ai = SimpleNamespace(
        analysis_connection_id="conn", analysis_model_name="qwen-max",
        connections=[SimpleNamespace(id="conn", enable=False, api_key="sk", api_base="")],
    )

    with patch.object(agent_service, "config_manager") as cm:
        cm.get_user_config.return_value = config(missing_ai)
        assert agent_service._get_summary_llm("user", MagicMock()) is None

        cm.get_user_config.return_value = config(disabled_ai)
        assert agent_service._get_summary_llm("user", MagicMock()) is None

        cm.get_user_config.return_value = config(valid_ai)
        llm = agent_service._get_summary_llm("user", MagicMock())
        assert isinstance(llm, agent_service.ChatOpenAI)

        cm.get_user_config.side_effect = RuntimeError("config unavailable")
        assert agent_service._get_summary_llm("user", MagicMock()) is None


# ---------------------------------------------------------------------------
# app/service/task_worker.py -- pressure monitor loop
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pressure_monitor_updates_ema_then_stops_on_cancel(monkeypatch):
    from app.service import task_worker

    worker = task_worker.TaskWorker()
    worker.running = True

    cpu_values = iter([10.0, 20.0])
    fake_psutil = SimpleNamespace(
        cpu_percent=lambda interval=None: next(cpu_values),
        virtual_memory=lambda: SimpleNamespace(percent=50.0),
    )
    monkeypatch.setitem(sys.modules, "psutil", fake_psutil)

    sleep_calls = 0

    async def cancel_after_second_sample(_delay):
        nonlocal sleep_calls
        sleep_calls += 1
        if sleep_calls == 2:
            raise asyncio.CancelledError

    with patch.object(task_worker.asyncio, "sleep", cancel_after_second_sample):
        await worker._pressure_monitor_loop()

    assert worker.system_pressure == {"cpu": 8.0, "memory": 20.0}
    assert sleep_calls == 2


@pytest.mark.asyncio
async def test_pressure_monitor_swallows_psutil_import_failure(monkeypatch):
    from app.service import task_worker

    worker = task_worker.TaskWorker()
    worker.running = True
    monkeypatch.setitem(sys.modules, "psutil", None)

    await worker._pressure_monitor_loop()
    assert worker.system_pressure == {"cpu": 0.0, "memory": 0.0}


# ---------------------------------------------------------------------------
# app/service/moment/day_caption_service.py -- prompt and connection helpers
# ---------------------------------------------------------------------------


def test_format_materials_explains_dedup_and_missing_descriptions():
    from datetime import date

    from app.service.moment.day_caption_service import _format_materials_for_prompt

    prompt = _format_materials_for_prompt(
        date(2026, 9, 10),
        {
            "counts": {"image": 3, "image_original": 5, "video": 1},
            "people": ["Alice", "Bob"],
            "locations": ["杭州 · 西湖"],
            "tags": ["旅行"],
            "descriptions": [],
        },
        "poetic",
    )
    assert "期望风格：poetic" in prompt
    assert "3 个不同瞬间（当天共拍 5 张图） / 1 个视频" in prompt
    assert "一起出现的人物：Alice、Bob" in prompt
    assert "主要地点：杭州 · 西湖" in prompt
    assert "避免虚构细节" in prompt


def test_resolve_caption_connection_prefers_requested_mode_and_validates_selection():
    from app.service.moment import day_caption_service as svc

    chat = SimpleNamespace(id="chat", enable=True, api_key="sk-chat", api_base="https://chat")
    analysis = SimpleNamespace(id="analysis", enable=True, api_key="sk-analysis", api_base="https://analysis")
    ai = SimpleNamespace(
        chat_connection_id="chat", chat_model_name="chat-model",
        analysis_connection_id="analysis", analysis_model_name="analysis-model",
        connections=[chat, analysis], moment_day_caption_prompt="caption prompt",
    )

    with patch.object(svc, "config_manager") as cm:
        cm.get_user_config.return_value = SimpleNamespace(ai=ai)
        assert svc._resolve_connection_and_model("user", MagicMock(), None, None, prefer="chat")[0] is chat
        assert svc._resolve_connection_and_model("user", MagicMock(), None, None, prefer="analysis")[0] is analysis

        empty = SimpleNamespace(
            chat_connection_id="", chat_model_name="", analysis_connection_id="",
            analysis_model_name="", connections=[], moment_day_caption_prompt="",
        )
        cm.get_user_config.return_value = SimpleNamespace(ai=empty)
        with pytest.raises(ValueError, match="未配置 AI 模型"):
            svc._resolve_connection_and_model("user", MagicMock(), None, None)

        disabled = SimpleNamespace(
            chat_connection_id="chat", chat_model_name="chat-model",
            analysis_connection_id="", analysis_model_name="",
            connections=[SimpleNamespace(id="chat", enable=False, api_key="sk", api_base="")],
            moment_day_caption_prompt="",
        )
        cm.get_user_config.return_value = SimpleNamespace(ai=disabled)
        with pytest.raises(ValueError, match="已禁用"):
            svc._resolve_connection_and_model("user", MagicMock(), None, None)
