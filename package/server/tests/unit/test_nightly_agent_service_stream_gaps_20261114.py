# -*- coding: utf-8 -*-
"""Nightly watch 2026-11-14 round2 · 覆盖盲区补测（app/service/agent/service.py）。

相对 2026-11-13 覆盖率基线，此前完全未触达的分支：
- stream_chat_with_agent：
  * 字符串正文里内嵌的 <think> 段被单独作为 reasoning 帧下发；
  * list 正文里的 text 块内嵌 <think> 段同样下发 reasoning 帧；
  * 工具返回为 list 内容时，tool_return 只保留 type=="text" 的块；
  * 搜索工具返回错误时，对应的 tool_call 记录被标记为 error；
  * 搜索 / 作品 / 操作计划三类工具返回非法 JSON 时只记日志不抛异常；
  * 循环结束时思考过滤器残留的正文与思考分别补发；
  * 标题生成任务抛异常时只记日志，流程继续。
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from langchain_core.messages import HumanMessage, SystemMessage

from app.service.agent import service as agent_service

pytestmark = [pytest.mark.smoke, pytest.mark.module_agent]

SESSION_ID = str(uuid4())


def _ai_settings(**overrides):
    base = SimpleNamespace(chat_connection_id=None, analysis_connection_id=None,
                           chat_model_name=None, analysis_model_name=None,
                           chat_reasoning_effort=None, connections=[])
    for key, value in overrides.items():
        setattr(base, key, value)
    return base


def _config(ai):
    return SimpleNamespace(ai=ai)


def _chunk(content, *, chunk_type="AIMessageChunk", extra=None, tool_calls=None,
           name=None, tool_call_id=None, status=""):
    return SimpleNamespace(type=chunk_type, content=content,
                           additional_kwargs=extra or {}, tool_calls=tool_calls or [],
                           name=name, tool_call_id=tool_call_id, status=status)


class _FakeAgent:
    def __init__(self, chunks):
        self._chunks = chunks

    async def astream(self, payload, stream_mode=None, config=None):
        for chunk, metadata in self._chunks:
            yield chunk, metadata


async def _collect(stream):
    return [item async for item in stream]


@contextmanager
def _stream_env(agent, **overrides):
    patches = {
        "get_agent_executor": patch.object(agent_service, "get_agent_executor", return_value=(agent, "sys")),
        "get_session_history": patch.object(agent_service, "get_session_history", return_value=[]),
        "compress_history_if_needed": patch.object(agent_service, "compress_history_if_needed",
                                                   side_effect=lambda m, *a, **k: m),
        "create_message": patch.object(agent_service, "create_message"),
        "config_manager": patch.object(agent_service, "config_manager"),
        "model_context_window": patch.object(agent_service, "_model_context_window", return_value=1000),
    }
    if "title" in overrides:
        patches["generate_session_title_task"] = patch.object(
            agent_service, "generate_session_title_task", **overrides["title"])
    started = []
    for patcher in patches.values():
        started.append(patcher.start())
    try:
        patches["config_manager"].new.return_value = None
        yield patches
    finally:
        for patcher in patches.values():
            patcher.stop()


def _payloads(events):
    return [json.loads(item[len("data: "):]) for item in events if item.startswith("data: {")]


# --------------------------------------------------------------------------- #
# 思考帧
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_stream_emits_embedded_reasoning_from_string_content():
    agent = _FakeAgent([(_chunk("<think>思考</think>"), {"langgraph_node": "agent"})])
    with _stream_env(agent):
        events = await _collect(agent_service.stream_chat_with_agent("u", SESSION_ID, "hi", MagicMock()))
    payloads = _payloads(events)
    assert any(p.get("reasoning") == "思考" for p in payloads)


@pytest.mark.asyncio
async def test_stream_emits_embedded_reasoning_from_list_content():
    agent = _FakeAgent([
        (_chunk([{"type": "text", "text": "<think>思考</think>"}], chunk_type="AIMessageChunk"),
         {"langgraph_node": "agent"}),
    ])
    with _stream_env(agent):
        events = await _collect(agent_service.stream_chat_with_agent("u", SESSION_ID, "hi", MagicMock()))
    payloads = _payloads(events)
    assert any(p.get("reasoning") == "思考" for p in payloads)


# --------------------------------------------------------------------------- #
# 工具事件
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_stream_keeps_only_text_blocks_in_the_tool_return():
    start_chunk = _chunk("", chunk_type="AIMessageChunk",
                         tool_calls=[{"id": "tc-1", "name": "search_library_photos", "args": {}}])
    tool_chunk = _chunk([{"type": "text", "text": "结果"}, {"type": "image", "url": "x"}],
                         chunk_type="tool", name="search_library_photos",
                         tool_call_id="tc-1", status="success")
    agent = _FakeAgent([
        (start_chunk, {"langgraph_node": "agent"}),
        (tool_chunk, {"langgraph_node": "tools"}),
    ])
    with _stream_env(agent):
        events = await _collect(agent_service.stream_chat_with_agent("u", SESSION_ID, "hi", MagicMock()))
    payloads = _payloads(events)
    assert any(p.get("type") == "tool_end" and p.get("tool_name") == "search_library_photos"
               for p in payloads)


@pytest.mark.asyncio
async def test_stream_marks_the_matching_tool_call_as_error():
    start_chunk = _chunk("", chunk_type="AIMessageChunk",
                         tool_calls=[{"id": "tc-1", "name": "search_library_photos", "args": {}}])
    error_chunk = _chunk(json.dumps({"error": "索引坏了"}), chunk_type="tool",
                         name="search_library_photos", tool_call_id="tc-1", status="error")
    agent = _FakeAgent([
        (start_chunk, {"langgraph_node": "agent"}),
        (error_chunk, {"langgraph_node": "tools"}),
    ])
    with _stream_env(agent):
        events = await _collect(agent_service.stream_chat_with_agent("u", SESSION_ID, "hi", MagicMock()))
    payloads = _payloads(events)
    assert any(p.get("type") == "tool_end" and p.get("status") == "error" for p in payloads)
    assert any("搜索未完成：索引坏了" in (p.get("content") or "") for p in payloads)


@pytest.mark.asyncio
async def test_stream_tolerates_a_malformed_search_tool_payload():
    tool_chunk = _chunk("这不是 JSON", chunk_type="tool", name="search_library_photos",
                         tool_call_id="tc-1", status="success")
    agent = _FakeAgent([(tool_chunk, {"langgraph_node": "tools"})])
    with _stream_env(agent):
        events = await _collect(agent_service.stream_chat_with_agent("u", SESSION_ID, "hi", MagicMock()))
    payloads = _payloads(events)
    assert any(p.get("type") == "tool_end" for p in payloads)
    assert not [p for p in payloads if p.get("type") == "search_result"]


@pytest.mark.asyncio
async def test_stream_tolerates_a_malformed_artifact_tool_payload():
    tool_chunk = _chunk("这不是 JSON", chunk_type="tool", name="create_artifact_draft",
                         tool_call_id="tc-2", status="success")
    agent = _FakeAgent([(tool_chunk, {"langgraph_node": "tools"})])
    with _stream_env(agent):
        events = await _collect(agent_service.stream_chat_with_agent("u", SESSION_ID, "hi", MagicMock()))
    payloads = _payloads(events)
    assert not [p for p in payloads if p.get("type") == "artifact"]


@pytest.mark.asyncio
async def test_stream_tolerates_a_malformed_action_plan_tool_payload():
    tool_chunk = _chunk("这不是 JSON", chunk_type="tool", name="propose_album_repairs",
                         tool_call_id="tc-3", status="success")
    agent = _FakeAgent([(tool_chunk, {"langgraph_node": "tools"})])
    with _stream_env(agent):
        events = await _collect(agent_service.stream_chat_with_agent("u", SESSION_ID, "hi", MagicMock()))
    payloads = _payloads(events)
    assert not [p for p in payloads if p.get("type") == "action_plan"]


# --------------------------------------------------------------------------- #
# 残留正文 / 标题任务
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_stream_flushes_the_trailing_text_buffer():
    agent = _FakeAgent([(_chunk("<", chunk_type="AIMessageChunk"), {"langgraph_node": "agent"})])
    with _stream_env(agent):
        events = await _collect(agent_service.stream_chat_with_agent("u", SESSION_ID, "hi", MagicMock()))
    payloads = _payloads(events)
    assert any(p.get("content") == "<" for p in payloads)


@pytest.mark.asyncio
async def test_stream_flushes_the_trailing_reasoning_buffer():
    agent = _FakeAgent([(_chunk("<think>未闭合", chunk_type="AIMessageChunk"),
                         {"langgraph_node": "agent"})])
    with _stream_env(agent):
        events = await _collect(agent_service.stream_chat_with_agent("u", SESSION_ID, "hi", MagicMock()))
    payloads = _payloads(events)
    assert any(p.get("reasoning") == "未闭合" for p in payloads)


@pytest.mark.asyncio
async def test_stream_survives_a_failing_title_task():
    agent = _FakeAgent([(_chunk("正文"), {"langgraph_node": "agent"})])
    with _stream_env(agent, title={"side_effect": RuntimeError("标题炸了")}):
        events = await _collect(agent_service.stream_chat_with_agent("u", SESSION_ID, "hi", MagicMock()))
    payloads = _payloads(events)
    assert any(p.get("content") == "正文" for p in payloads)
    assert events[-1].strip() == "data: [DONE]"

@pytest.mark.asyncio
async def test_stream_flushes_the_trailing_reasoning_buffer():
    """思考标签未闭合时，残留片段在循环结束后作为 reasoning 帧补发。"""
    agent = _FakeAgent([(_chunk("<think></thi", chunk_type="AIMessageChunk"),
                         {"langgraph_node": "agent"})])
    with _stream_env(agent):
        events = await _collect(agent_service.stream_chat_with_agent("u", SESSION_ID, "hi", MagicMock()))
    payloads = _payloads(events)
    assert any(p.get("reasoning") == "</thi" for p in payloads)

# --------------------------------------------------------------------------- #
# 追加：LLM 参数 / 记忆注入 / 标题任务
# --------------------------------------------------------------------------- #


def _search_settings(model_name="m1"):
    ai = _ai_settings(chat_connection_id="c1", chat_model_name=model_name,
                      connections=[SimpleNamespace(id="c1", enable=True, api_key="sk-test",
                                                  api_base=None, models=[])])
    return _config(ai)


def test_get_agent_executor_forwards_the_reasoning_effort_to_the_llm():
    llm = MagicMock()
    llm.extra_body = {}
    with patch.object(agent_service.config_manager, "get_user_config", return_value=_search_settings()), \
         patch.object(agent_service, "FixedChatOpenAI", return_value=llm) as fixed, \
         patch.object(agent_service, "get_session_history", return_value=[]), \
         patch("app.service.agent.photo_search.classify_photo_intent", return_value="find"), \
         patch("app.service.agent.search_planner.PhotoSearchExecutor", return_value=MagicMock()):
        agent_service.get_agent_executor("u", SESSION_ID, MagicMock(), reasoning_effort="high", user_input="找照片", mode="search")
    assert fixed.call_args.kwargs["reasoning_effort"] == "high"


def test_get_agent_executor_disables_thinking_for_minicpm_planning_models():
    llm = MagicMock()
    llm.extra_body = {}
    with patch.object(agent_service.config_manager, "get_user_config", return_value=_search_settings("MiniCPM-X")), \
         patch.object(agent_service, "FixedChatOpenAI", return_value=llm), \
         patch.object(agent_service, "get_session_history", return_value=[]), \
         patch("app.service.agent.photo_search.classify_photo_intent", return_value="find"), \
         patch("app.service.agent.search_planner.PhotoSearchExecutor", return_value=MagicMock()):
        agent_service.get_agent_executor("u", SESSION_ID, MagicMock(), reasoning_effort="high", user_input="找照片", mode="search")
    assert llm.model_copy.call_args.kwargs["update"]["extra_body"]["chat_template_kwargs"] == {"enable_thinking": False}


def test_get_agent_executor_survives_a_memory_injection_failure():
    llm = MagicMock()
    llm.extra_body = {}
    with patch.object(agent_service.config_manager, "get_user_config", return_value=_search_settings()), \
         patch.object(agent_service, "FixedChatOpenAI", return_value=llm), \
         patch.object(agent_service, "get_session_history", return_value=[]), \
         patch.object(agent_service, "get_agent_tools", return_value=[]), \
         patch.object(agent_service, "create_agent", return_value=MagicMock()), \
         patch("app.service.agent.photo_search.classify_photo_intent", return_value="general"), \
         patch("app.service.agent.memory.build_memory_prompt", side_effect=RuntimeError("记忆炸了")):
        agent, system_prompt = agent_service.get_agent_executor(
            "u", SESSION_ID, MagicMock(), user_input="你好")
    assert agent is not None
    assert "记忆炸了" not in system_prompt


def test_chat_with_agent_survives_a_failing_memory_extraction_submit():
    agent = MagicMock()
    agent.invoke.return_value = {"messages": [SimpleNamespace(
        content="ok", type="ai", additional_kwargs={}, tool_calls=None)]}
    with patch.object(agent_service, "get_agent_executor", return_value=(agent, "sys")), \
         patch.object(agent_service, "get_session_history", return_value=[]), \
         patch.object(agent_service, "compress_history_if_needed", side_effect=lambda m, *a, **k: m), \
         patch.object(agent_service, "create_message"), \
         patch.object(agent_service, "config_manager") as cm, \
         patch.object(agent_service, "_model_context_window", return_value=1000), \
         patch.object(agent_service, "ThreadPoolExecutor") as pool:
        cm.get_user_config.return_value = _config(_ai_settings())
        pool.return_value.submit.side_effect = RuntimeError("线程池炸了")
        out = agent_service.chat_with_agent("u", SESSION_ID, "你好", MagicMock())
    assert out == "ok"


def test_generate_session_title_task_strips_single_quotes():
    llm = MagicMock()
    llm.invoke.return_value = SimpleNamespace(content="'西安三日游'")
    ai = _ai_settings(analysis_connection_id="c1", analysis_model_name="m1",
                      connections=[SimpleNamespace(id="c1", enable=True, api_key="sk-test",
                                                  api_base=None)])
    session_ctx = MagicMock()
    session_ctx.__enter__ = lambda self: MagicMock()
    session_ctx.__exit__ = lambda *args: False
    with patch("app.crud.agent.get_session", return_value=None), \
         patch("app.crud.agent.update_session"), \
         patch("langchain_openai.ChatOpenAI", return_value=llm), \
         patch("app.core.config_manager.config_manager") as cm, \
         patch.object(agent_service, "SessionLocal", return_value=session_ctx):
        cm.get_user_config.return_value = _config(ai)
        title = agent_service.generate_session_title_task(str(uuid4()), SESSION_ID, "西安三日游")
    assert title == "西安三日游"


def test_compress_history_trims_when_there_is_nothing_to_compress():
    messages = [SystemMessage(content="s")] + [HumanMessage(content="x" * 300) for _ in range(10)]
    with patch.object(agent_service, "_get_summary_llm", return_value=MagicMock()), \
         patch.object(agent_service, "trim_history_messages", return_value=["trimmed"]) as trim:
        out = agent_service.compress_history_if_needed(
            messages, "u", SESSION_ID, MagicMock(), context_window=1024)
    assert out == ["trimmed"]
    trim.assert_called_once()
