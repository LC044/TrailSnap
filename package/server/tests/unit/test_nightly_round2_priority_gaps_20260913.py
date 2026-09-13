"""2026-09-13 round-2 nightly tests for five current coverage gaps.

Targets selected from the latest Cobertura scan:

* ``app.service.agent.service`` -- streaming text/reasoning, tool references,
  abort/error/cancellation persistence paths.
* ``app.service.moment.day_caption_service`` -- cached, successful, and invalid
  streaming caption generation.
* ``app.service.jobs.proactive_memory`` -- LLM availability and greeting paths.
* ``app.api.photo`` -- recycle-bin restore-all and permanent-delete handlers.
* ``app.api.toolbox`` -- legacy similar-task UUID and cluster cleanup paths.
"""
import asyncio
import json
from contextlib import contextmanager
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from langchain_core.messages import SystemMessage


pytestmark = [pytest.mark.smoke]


def _ctx(db):
    @contextmanager
    def _cm():
        yield db

    return MagicMock(side_effect=_cm)


def _sse(events):
    payload = []
    for event in events:
        assert event.startswith("data: ")
        body = event[len("data: "):].strip()
        payload.append(body if body == "[DONE]" else json.loads(body))
    return payload


def _agent_chunk(content="", additional_kwargs=None, tool_calls=None, type_="AIMessageChunk"):
    return SimpleNamespace(
        type=type_,
        content=content,
        additional_kwargs=additional_kwargs or {},
        tool_calls=tool_calls or [],
    )


def _agent_with(chunks):
    async def astream(*_args, **_kwargs):
        for chunk, metadata in chunks:
            yield chunk, metadata

    return SimpleNamespace(astream=astream)


# ---------------------------------------------------------------------------
# app/service/agent/service.py -- streaming chat paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_stream_emits_title_content_and_persists_assistant():
    from app.service.agent import service as agent_service

    user_id, session_id, db = str(uuid4()), str(uuid4()), MagicMock()
    agent = _agent_with([(
        _agent_chunk(content="你好"),
        {"langgraph_node": "model"},
    )])
    config = SimpleNamespace(ai=SimpleNamespace(connections=[]))

    with (
        patch.object(agent_service, "get_agent_executor", return_value=(agent, "系统提示")),
        patch.object(agent_service, "get_session_history", return_value=[]),
        patch.object(agent_service, "create_message") as create_message,
        patch.object(agent_service, "generate_session_title_task", return_value="新会话"),
        patch.object(agent_service.config_manager, "get_user_config", return_value=config),
        patch.object(agent_service, "_model_context_window", return_value=128000),
        patch.object(agent_service, "compress_history_if_needed", side_effect=lambda messages, *_args, **_kwargs: messages),
        patch("app.service.agent.memory.extract_and_store_memory_task") as extract_memory,
    ):
        events = [event async for event in agent_service.stream_chat_with_agent(
            user_id, session_id, "整理照片", db,
        )]
        await asyncio.sleep(0.1)

    payload = _sse(events)
    assert payload == [
        {"content": "你好", "session_id": session_id},
        {"title": "新会话", "session_id": session_id},
        "[DONE]",
    ]
    assert create_message.call_count == 2
    assistant = create_message.call_args_list[1].args[1]
    assert assistant.role == "assistant"
    assert assistant.content == "你好"
    assert assistant.reasoning is None
    assert assistant.tool_calls is None
    assert assistant.content_ext is None
    extract_memory.assert_called_once_with(user_id, "整理照片", "你好", [])
    assert session_id not in agent_service._aborted_sessions


@pytest.mark.asyncio
async def test_agent_stream_records_tool_calls_artifacts_and_action_plans():
    from app.service.agent import service as agent_service

    user_id, session_id, db = str(uuid4()), str(uuid4()), MagicMock()
    artifact = {"id": str(uuid4()), "title": "西湖故事"}
    action_plan = {"plan_id": str(uuid4()), "changes": []}
    chunks = [
        (
            _agent_chunk(tool_calls=[{
                "id": "call-artifact", "name": "create_artifact_draft", "args": {"title": "西湖故事"}
            }]),
            {"langgraph_node": "agent"},
        ),
        (
            SimpleNamespace(
                type="ToolMessage", content=json.dumps({"artifact": artifact}),
                additional_kwargs={}, tool_calls=[], name="create_artifact_draft",
                tool_call_id="call-artifact", status="",
            ),
            {"langgraph_node": "tools"},
        ),
        (
            _agent_chunk(tool_calls=[{
                "id": "call-plan", "name": "propose_album_organization", "args": {"album": "西湖"}
            }]),
            {"langgraph_node": "agent"},
        ),
        (
            SimpleNamespace(
                type="ToolMessage", content=json.dumps({"action_plan": action_plan}),
                additional_kwargs={}, tool_calls=[], name="propose_album_organization",
                tool_call_id="call-plan", status="",
            ),
            {"langgraph_node": "tools"},
        ),
    ]
    agent = _agent_with(chunks)
    config = SimpleNamespace(ai=SimpleNamespace(connections=[]))

    with (
        patch.object(agent_service, "get_agent_executor", return_value=(agent, "系统提示")),
        patch.object(agent_service, "get_session_history", return_value=[SystemMessage(content="既有提示")]),
        patch.object(agent_service, "create_message") as create_message,
        patch.object(agent_service.config_manager, "get_user_config", return_value=config),
        patch.object(agent_service, "_model_context_window", return_value=128000),
        patch.object(agent_service, "compress_history_if_needed", side_effect=lambda messages, *_args, **_kwargs: messages),
    ):
        events = [event async for event in agent_service.stream_chat_with_agent(
            user_id, session_id, "生成作品", db,
        )]
        await asyncio.sleep(0.1)

    payload = _sse(events)
    assert [item.get("type") for item in payload if isinstance(item, dict)] == [
        "tool_start", "tool_end", "artifact", "tool_start", "tool_end", "action_plan",
    ]
    assistant = create_message.call_args_list[-1].args[1]
    assert assistant.content_ext == {"artifacts": [artifact], "action_plans": [action_plan]}
    assert [(call["tool_name"], call["tool_status"]) for call in assistant.tool_calls] == [
        ("create_artifact_draft", "success"), ("propose_album_organization", "success"),
    ]
    assert json.loads(assistant.tool_calls[0]["tool_return"]) == {"artifact": artifact}


@pytest.mark.asyncio
async def test_agent_stream_manual_abort_keeps_first_chunk_and_skips_memory():
    from app.service.agent import service as agent_service

    user_id, session_id, db = str(uuid4()), str(uuid4()), MagicMock()

    async def astream(*_args, **_kwargs):
        yield _agent_chunk(content="第一段"), {"langgraph_node": "model"}
        agent_service._aborted_sessions[session_id] = True
        yield _agent_chunk(content="不应输出"), {"langgraph_node": "model"}

    agent = SimpleNamespace(astream=astream)
    config = SimpleNamespace(ai=SimpleNamespace(connections=[]))
    with (
        patch.object(agent_service, "get_agent_executor", return_value=(agent, "系统提示")),
        patch.object(agent_service, "get_session_history", return_value=[SystemMessage(content="旧提示")]),
        patch.object(agent_service, "create_message") as create_message,
        patch.object(agent_service.config_manager, "get_user_config", return_value=config),
        patch.object(agent_service, "_model_context_window", return_value=128000),
        patch.object(agent_service, "compress_history_if_needed", side_effect=lambda messages, *_args, **_kwargs: messages),
        patch("app.service.agent.memory.extract_and_store_memory_task") as extract_memory,
    ):
        events = [event async for event in agent_service.stream_chat_with_agent(
            user_id, session_id, "停止输出", db,
        )]
        await asyncio.sleep(0.1)

    assert _sse(events) == [
        {"content": "第一段", "session_id": session_id}, "[DONE]",
    ]
    assistant = create_message.call_args_list[-1].args[1]
    assert assistant.content == "第一段"
    extract_memory.assert_not_called()
    assert session_id not in agent_service._aborted_sessions


@pytest.mark.asyncio
async def test_agent_stream_error_yields_friendly_sse_and_saves_partial_reply():
    from app.service.agent import service as agent_service

    user_id, session_id, db = str(uuid4()), str(uuid4()), MagicMock()
    config = SimpleNamespace(ai=SimpleNamespace(connections=[]))

    with (
        patch.object(agent_service, "get_agent_executor", side_effect=ValueError("模型不可用")),
        patch.object(agent_service, "create_message") as create_message,
        patch.object(agent_service, "SessionLocal", _ctx(db)),
    ):
        events = [event async for event in agent_service.stream_chat_with_agent(
            user_id, session_id, "你好", db,
        )]

    payload = _sse(events)
    assert len(payload) == 2
    assert payload[0]["session_id"] == session_id
    assert "模型不可用" in payload[0]["content"]
    assert payload[1] == "[DONE]"
    saved = create_message.call_args.args[1]
    assert saved.role == "assistant"
    assert "模型不可用" in saved.content
    assert session_id not in agent_service._aborted_sessions


@pytest.mark.asyncio
async def test_agent_stream_cancelled_error_is_re_raised_without_saving_empty_reply():
    from app.service.agent import service as agent_service

    user_id, session_id, db = str(uuid4()), str(uuid4()), MagicMock()

    with (
        patch.object(agent_service, "get_agent_executor", side_effect=asyncio.CancelledError()),
        patch.object(agent_service, "create_message") as create_message,
        patch.object(agent_service, "SessionLocal", _ctx(db)),
    ):
        with pytest.raises(asyncio.CancelledError):
            async for _event in agent_service.stream_chat_with_agent(user_id, session_id, "你好", db):
                pass

    create_message.assert_not_called()
    assert session_id not in agent_service._aborted_sessions


# ---------------------------------------------------------------------------
# app/service/moment/day_caption_service.py -- caption SSE stream
# ---------------------------------------------------------------------------


async def _collect_caption(coro):
    return [event async for event in coro]


@pytest.mark.asyncio
async def test_caption_stream_returns_cached_caption_without_llm():
    from app.service.moment import day_caption_service as caption_service

    user_id, db = uuid4(), MagicMock()
    lock = asyncio.Lock()
    materials = {"_model_name": "caption-model"}

    with (
        patch.object(caption_service, "_get_user_lock", return_value=lock),
        patch.object(caption_service, "_prepare_context", return_value=("旧文案", materials)),
        patch.object(caption_service, "_build_llm") as build_llm,
    ):
        events = await _collect_caption(caption_service.generate_caption_stream(
            user_id, db, date(2026, 9, 13), "Asia/Shanghai",
        ))

    assert _sse(events) == [
        {"content": "旧文案", "cached": True}, "[DONE]",
    ]
    build_llm.assert_not_called()


@pytest.mark.asyncio
async def test_caption_stream_emits_text_reasoning_and_persists_caption():
    from app.service.moment import day_caption_service as caption_service

    user_id, db = uuid4(), MagicMock()
    lock = asyncio.Lock()
    materials = {
        "_connection": SimpleNamespace(api_key="k"), "_model_name": "caption-model",
        "_system_prompt": "system", "_user_prompt": "user", "_photo_count": 2,
    }

    async def astream(_messages):
        yield SimpleNamespace(content="<think>隐藏</think>西湖", additional_kwargs={})
        yield SimpleNamespace(content="", additional_kwargs={"summary": [{"text": "构思中"}]})
        yield SimpleNamespace(content=[
            {"type": "text", "text": "夜色"},
            {"type": "reasoning", "summary": [{"text": "分镜"}]},
        ], additional_kwargs={})

    llm = SimpleNamespace(astream=astream)
    saved = SimpleNamespace(caption="西湖夜色", source="ai", updated_at=datetime(2026, 9, 13, 12, 0))

    with (
        patch.object(caption_service, "_get_user_lock", return_value=lock),
        patch.object(caption_service, "_prepare_context", return_value=(None, materials)),
        patch.object(caption_service, "_build_llm", return_value=llm),
        patch.object(caption_service.moment_crud, "upsert_caption", return_value=saved) as upsert,
    ):
        events = await _collect_caption(caption_service.generate_caption_stream(
            user_id, db, date(2026, 9, 13), "Asia/Shanghai", style="温暖",
        ))

    payload = _sse(events)
    assert payload == [
        {"content": "西湖"},
        {"reasoning": "构思中"},
        {"content": "夜色"},
        {"reasoning": "分镜"},
        {"done": True, "caption": "西湖夜色", "source": "ai", "updated_at": "2026-09-13T12:00:00"},
        "[DONE]",
    ]
    assert upsert.call_args.args[5] == "西湖夜色"
    assert upsert.call_args.args[7] == "caption-model"
    assert upsert.call_args.args[8] == 2


@pytest.mark.asyncio
async def test_caption_stream_prepare_value_error_returns_error_and_done():
    from app.service.moment import day_caption_service as caption_service

    user_id, db = uuid4(), MagicMock()
    lock = asyncio.Lock()
    with (
        patch.object(caption_service, "_get_user_lock", return_value=lock),
        patch.object(caption_service, "_prepare_context", side_effect=ValueError("没有可用模型")),
        patch.object(caption_service, "_build_llm") as build_llm,
    ):
        events = await _collect_caption(caption_service.generate_caption_stream(
            user_id, db, date(2026, 9, 13), "Asia/Shanghai",
        ))

    assert _sse(events) == [
        {"error": "没有可用模型"}, "[DONE]",
    ]
    build_llm.assert_not_called()


# ---------------------------------------------------------------------------
# app/service/jobs/proactive_memory.py -- LLM availability and greeting
# ---------------------------------------------------------------------------


def test_proactive_has_llm_checks_chat_analysis_and_swallows_config_errors():
    from app.service.jobs import proactive_memory as job

    db = MagicMock()
    complete = SimpleNamespace(ai=SimpleNamespace(
        chat_connection_id="chat", chat_model_name="chat-model",
        analysis_connection_id=None, analysis_model_name=None,
    ))
    incomplete = SimpleNamespace(ai=SimpleNamespace(
        chat_connection_id=None, chat_model_name=None,
        analysis_connection_id="analysis", analysis_model_name=None,
    ))

    with (
        patch.object(job.config_manager, "get_user_config", side_effect=[complete, incomplete, RuntimeError("配置损坏")]),
    ):
        assert job._has_llm(uuid4(), db) is True
        assert job._has_llm(uuid4(), db) is False
        assert job._has_llm(uuid4(), db) is False


def test_proactive_llm_greeting_builds_prompt_strips_quotes_and_falls_back():
    from app.service.jobs import proactive_memory as job

    db, user_id = MagicMock(), uuid4()
    disabled = SimpleNamespace(ai=SimpleNamespace(
        chat_connection_id="chat", chat_model_name="chat-model",
        connections=[SimpleNamespace(id="chat", enable=False, api_key="key", api_base="")],
    ))
    enabled = SimpleNamespace(ai=SimpleNamespace(
        chat_connection_id="chat", chat_model_name="chat-model",
        connections=[SimpleNamespace(id="chat", enable=True, api_key="key", api_base="https://ai.test")],
    ))
    llm = MagicMock()
    llm.invoke.return_value = SimpleNamespace(content='  "温暖的一句问候"  ')

    with patch.object(job.config_manager, "get_user_config", return_value=disabled):
        assert job._llm_greeting(db, user_id, 3, ["西湖"]) is None

    with (
        patch.object(job.config_manager, "get_user_config", return_value=enabled),
        patch("langchain_openai.ChatOpenAI", return_value=llm) as llm_cls,
    ):
        greeting = job._llm_greeting(db, user_id, 3, ["西湖", "夜色"])

    assert greeting == "温暖的一句问候"
    assert llm_cls.call_args.kwargs["model"] == "chat-model"
    prompt = llm.invoke.call_args.args[0][0].content
    assert "3 年前" in prompt
    assert "西湖；夜色" in prompt


# ---------------------------------------------------------------------------
# app/api/photo.py -- recycle-bin restore-all and permanent delete
# ---------------------------------------------------------------------------


def test_restore_all_recycle_bin_handles_empty_and_chunked_batches():
    from app.api import photo as photo_api

    user = SimpleNamespace(id=uuid4())
    db = MagicMock()
    ids = [uuid4() for _ in range(5)]

    with (
        patch.object(photo_api.app.crud.photo, "get_recycle_bin_photo_ids", return_value=[]),
        patch.object(photo_api.app.crud.photo, "restore_photos") as restore,
    ):
        empty = photo_api.restore_all_recycle_bin_photos(db=db, current_user=user)

    assert empty.data == {"restored": 0, "message": "Recycle bin is already empty"}
    restore.assert_not_called()

    with (
        patch.object(photo_api.app.crud.photo, "get_recycle_bin_photo_ids", return_value=ids),
        patch.object(photo_api.app.crud.photo, "DELETE_CHUNK_SIZE", 2),
        patch.object(photo_api.app.crud.photo, "restore_photos", side_effect=lambda _db, chunk, **_kwargs: len(chunk)) as restore,
    ):
        chunked = photo_api.restore_all_recycle_bin_photos(db=db, current_user=user)

    assert chunked.data["restored"] == 5
    assert [len(call.args[1]) for call in restore.call_args_list] == [2, 2, 1]


def test_permanently_delete_recycle_bin_requires_ids_and_delegates_to_bulk_crud():
    from app.api import photo as photo_api
    from fastapi import HTTPException

    user, db = SimpleNamespace(id=uuid4()), MagicMock()

    with pytest.raises(HTTPException) as empty:
        photo_api.permanently_delete_recycle_bin_photos(
            batch_data=SimpleNamespace(photo_ids=[]), db=db, current_user=user,
        )
    assert empty.value.status_code == 400

    photo_ids = [uuid4(), uuid4()]
    with patch.object(photo_api.app.crud.photo, "batch_delete_photos_db", return_value=2) as bulk_delete:
        response = photo_api.permanently_delete_recycle_bin_photos(
            batch_data=SimpleNamespace(photo_ids=photo_ids), db=db, current_user=user,
        )

    assert response.data == {"message": "Successfully permanently deleted 2 photos"}
    assert bulk_delete.call_args.kwargs == {
        "is_delete_file": True, "user_id": user.id,
    }
    assert list(bulk_delete.call_args.args[1]) == photo_ids


# ---------------------------------------------------------------------------
# app/api/toolbox.py -- legacy similar-task cleanup paths
# ---------------------------------------------------------------------------


def test_latest_similar_task_ignores_non_uuid_legacy_cluster_task_id():
    from app.api import toolbox as toolbox_api

    user, db = SimpleNamespace(id=uuid4()), MagicMock()
    latest = SimpleNamespace(task_id="not-a-uuid", created_at=datetime(2026, 9, 13))
    db.query.return_value.join.return_value.join.return_value.filter.return_value.order_by.return_value.first.return_value = latest

    with patch.object(toolbox_api.crud_task, "get_latest_task_by_type_and_owner", return_value=None):
        response = toolbox_api.get_latest_similar_task(db=db, current_user=user)

    assert response.code == 0
    assert response.data is None


def test_cancel_similar_task_deletes_legacy_clusters_when_task_row_missing():
    from app.api import toolbox as toolbox_api

    user, db = SimpleNamespace(id=uuid4()), MagicMock()
    cluster = SimpleNamespace(cluster_id=uuid4(), task_id=str(uuid4()))
    db.query.return_value.filter.return_value.all.return_value = [cluster]

    with patch.object(toolbox_api.crud_task, "get_task_by_id_and_owner", return_value=None):
        response = toolbox_api.cancel_similar_task(task_id=uuid4(), db=db, current_user=user)

    assert response.data == {"message": "Task deleted"}
    db.delete.assert_called_once_with(cluster)
    db.commit.assert_called_once()
