"""Nightly watch 2026-10-29 · 覆盖盲区补测（app/service/agent/service.py）。

被测模块：app/service/agent/service.py 的 Agent 装配、上下文压缩与流式对话。
覆盖点（相对 2026-10-29-r2 的覆盖率基线，此前完全未触达）：
- get_agent_executor：连接不存在 / 连接被禁用 / 未配置 API Key / 模型不在可用列表 /
  思考等级不被支持 五个 ValueError 分支，以及 search 模式走 PhotoSearchExecutor。
- compress_history_if_needed：带 context_window 且未超预算时原样返回；
  摘要 LLM 缺失 / 摘要为空 / 压缩过程抛异常时回退到滑动窗口。
- chat_with_agent：工具消息里带 error 的 search_library_photos 结果、
  没有 search_result 的工具消息、记忆抽取任务失败时的降级。
- stream_chat_with_agent：字符串正文、additional_kwargs 摘要、list 正文里的
  text / reasoning 块、tool_end 事件、search_library_photos 的错误与结果引用、
  artifact 与 action_plan 引用事件。

所有外部依赖（LLM、DB、agent 执行器）都被 mock，不发起真实网络请求。
"""

import json
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

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


def _connection(cid="conn-1", enable=True, api_key="sk-test", models=None):
    return SimpleNamespace(id=cid, enable=enable, api_key=api_key,
                           api_base=None, models=models or [])


# ---------------------------------------------------------------------------
# get_agent_executor
# ---------------------------------------------------------------------------


def test_get_agent_executor_requires_connection_and_model():
    with patch.object(agent_service.config_manager, "get_user_config", return_value=_config(_ai_settings())):
        with pytest.raises(ValueError, match="未配置智能分析模型"):
            agent_service.get_agent_executor("u", SESSION_ID, MagicMock())


def test_get_agent_executor_rejects_unknown_connection():
    ai = _ai_settings(chat_connection_id="missing", chat_model_name="m1")
    with patch.object(agent_service.config_manager, "get_user_config", return_value=_config(ai)):
        with pytest.raises(ValueError, match="未找到指定的 AI 连接配置"):
            agent_service.get_agent_executor("u", SESSION_ID, MagicMock())


def test_get_agent_executor_rejects_disabled_connection():
    ai = _ai_settings(chat_connection_id="c1", chat_model_name="m1",
                      connections=[_connection("c1", enable=False)])
    with patch.object(agent_service.config_manager, "get_user_config", return_value=_config(ai)):
        with pytest.raises(ValueError, match="已禁用"):
            agent_service.get_agent_executor("u", SESSION_ID, MagicMock())


def test_get_agent_executor_rejects_missing_api_key():
    ai = _ai_settings(chat_connection_id="c1", chat_model_name="m1",
                      connections=[_connection("c1", api_key="")])
    with patch.object(agent_service.config_manager, "get_user_config", return_value=_config(ai)):
        with pytest.raises(ValueError, match="未配置 API Key"):
            agent_service.get_agent_executor("u", SESSION_ID, MagicMock())


def test_get_agent_executor_rejects_model_outside_connection_list():
    model = SimpleNamespace(model_name="m1", reasoning_levels=["none", "high"])
    ai = _ai_settings(chat_connection_id="c1", chat_model_name="other",
                      connections=[_connection("c1", models=[model])])
    with patch.object(agent_service.config_manager, "get_user_config", return_value=_config(ai)):
        with pytest.raises(ValueError, match="不在连接"):
            agent_service.get_agent_executor("u", SESSION_ID, MagicMock())


def test_get_agent_executor_rejects_unsupported_reasoning_level():
    model = SimpleNamespace(model_name="m1", reasoning_levels=["none"])
    ai = _ai_settings(chat_connection_id="c1", chat_model_name="m1",
                      connections=[_connection("c1", models=[model])])
    with patch.object(agent_service.config_manager, "get_user_config", return_value=_config(ai)):
        with pytest.raises(ValueError, match="不支持思考等级"):
            agent_service.get_agent_executor("u", SESSION_ID, MagicMock(), reasoning_effort="ultra")


def test_get_agent_executor_uses_search_executor_in_search_mode():
    model = SimpleNamespace(model_name="m1", reasoning_levels=["none"])
    ai = _ai_settings(chat_connection_id="c1", chat_model_name="m1",
                      connections=[_connection("c1", models=[model])])
    executor = object()
    with patch.object(agent_service.config_manager, "get_user_config", return_value=_config(ai)), \
         patch.object(agent_service, "FixedChatOpenAI"), \
         patch.object(agent_service, "get_session_history", return_value=[]), \
         patch("app.service.agent.photo_search.classify_photo_intent", return_value="find"), \
         patch("app.service.agent.search_planner.PhotoSearchExecutor", return_value=executor) as planner:
        result, instructions = agent_service.get_agent_executor(
            "u", SESSION_ID, MagicMock(), mode="search")
    assert result is executor
    planner.assert_called_once()
    assert isinstance(instructions, str)


# ---------------------------------------------------------------------------
# compress_history_if_needed
# ---------------------------------------------------------------------------


def test_compress_history_returns_unchanged_within_context_window():
    messages = [SystemMessage(content="s"), HumanMessage(content="hi")]
    assert agent_service.compress_history_if_needed(
        messages, "u", SESSION_ID, MagicMock(), context_window=100000) == messages


def test_compress_history_falls_back_when_summary_llm_missing():
    messages = [SystemMessage(content="s")] + [HumanMessage(content="x" * 100) for _ in range(40)]
    with patch.object(agent_service, "_get_summary_llm", return_value=None), \
         patch.object(agent_service, "trim_history_messages", return_value=["trimmed"]) as trim:
        out = agent_service.compress_history_if_needed(
            messages, "u", SESSION_ID, MagicMock(), context_window=100)
    assert out == ["trimmed"]
    trim.assert_called_once()


def test_compress_history_falls_back_when_summary_is_empty():
    messages = [SystemMessage(content="s")] + [HumanMessage(content="x" * 100) for _ in range(40)]
    llm = SimpleNamespace(invoke=MagicMock(return_value=SimpleNamespace(content="   ")))
    with patch.object(agent_service, "_get_summary_llm", return_value=llm), \
         patch.object(agent_service, "trim_history_messages", return_value=["trimmed"]):
        out = agent_service.compress_history_if_needed(
            messages, "u", SESSION_ID, MagicMock(), context_window=100)
    assert out == ["trimmed"]


def test_compress_history_falls_back_on_exception():
    messages = [SystemMessage(content="s")] + [HumanMessage(content="x" * 100) for _ in range(40)]
    llm = SimpleNamespace(invoke=MagicMock(side_effect=RuntimeError("boom")))
    with patch.object(agent_service, "_get_summary_llm", return_value=llm), \
         patch.object(agent_service, "trim_history_messages", return_value=["trimmed"]):
        out = agent_service.compress_history_if_needed(
            messages, "u", SESSION_ID, MagicMock(), context_window=100)
    assert out == ["trimmed"]


# ---------------------------------------------------------------------------
# chat_with_agent
# ---------------------------------------------------------------------------


def _agent_response(messages):
    return {"messages": messages}


def test_chat_with_agent_reports_search_tool_error():
    tool_msg = AIMessage(content=json.dumps({"error": "查询失败"}), name="search_library_photos")
    tool_msg.type = "tool"
    final = AIMessage(content="本来的一句话")
    agent = MagicMock()
    agent.invoke.return_value = _agent_response([final, tool_msg])

    with patch.object(agent_service, "get_agent_executor", return_value=(agent, "sys")), \
         patch.object(agent_service, "get_session_history", return_value=[]), \
         patch.object(agent_service, "compress_history_if_needed", side_effect=lambda m, *a, **k: m), \
         patch.object(agent_service, "create_message"), \
         patch.object(agent_service, "config_manager") as cm, \
         patch.object(agent_service, "_model_context_window", return_value=1000):
        cm.get_user_config.return_value = _config(_ai_settings())
        out = agent_service.chat_with_agent("u", SESSION_ID, "找照片", MagicMock())
    assert "查询失败" in out


def test_chat_with_agent_collects_search_results():
    tool_msg = AIMessage(content=json.dumps({"search_result": {"id": "s1", "total": 3}}),
                          name="search_library_photos")
    tool_msg.type = "tool"
    final = AIMessage(content="找到了")
    agent = MagicMock()
    agent.invoke.return_value = _agent_response([tool_msg, final])

    with patch.object(agent_service, "get_agent_executor", return_value=(agent, "sys")), \
         patch.object(agent_service, "get_session_history", return_value=[]), \
         patch.object(agent_service, "compress_history_if_needed", side_effect=lambda m, *a, **k: m), \
         patch.object(agent_service, "create_message") as create_message, \
         patch.object(agent_service, "config_manager") as cm, \
         patch.object(agent_service, "_model_context_window", return_value=1000):
        cm.get_user_config.return_value = _config(_ai_settings())
        out = agent_service.chat_with_agent("u", SESSION_ID, "找照片", MagicMock())
    assert out == "找到了"
    ext = create_message.call_args.args[1].content_ext
    assert ext["search_results"] == [{"id": "s1", "total": 3}]


def test_chat_with_agent_survives_memory_extraction_failure():
    agent = MagicMock()
    agent.invoke.return_value = _agent_response([AIMessage(content="ok")])

    with patch.object(agent_service, "get_agent_executor", return_value=(agent, "sys")), \
         patch.object(agent_service, "get_session_history", return_value=[]), \
         patch.object(agent_service, "compress_history_if_needed", side_effect=lambda m, *a, **k: m), \
         patch.object(agent_service, "create_message"), \
         patch.object(agent_service, "config_manager") as cm, \
         patch.object(agent_service, "_model_context_window", return_value=1000), \
         patch("app.service.agent.memory.extract_and_store_memory_task", side_effect=RuntimeError("boom")):
        cm.get_user_config.return_value = _config(_ai_settings())
        out = agent_service.chat_with_agent("u", SESSION_ID, "你好", MagicMock())
    assert out == "ok"


# ---------------------------------------------------------------------------
# stream_chat_with_agent
# ---------------------------------------------------------------------------


def _chunk(content, *, chunk_type="AIMessageChunk", extra=None, tool_calls=None):
    return SimpleNamespace(type=chunk_type, content=content,
                           additional_kwargs=extra or {}, tool_calls=tool_calls or [],
                           name=getattr(extra, "name", None) if extra else None,
                           tool_call_id=getattr(extra, "tool_call_id", None) if extra else None,
                           status=getattr(extra, "status", "") if extra else "")


class _FakeAgent:
    def __init__(self, chunks):
        self._chunks = chunks

    async def astream(self, payload, stream_mode=None, config=None):
        for chunk, metadata in self._chunks:
            yield chunk, metadata


async def _collect(stream):
    return [item async for item in stream]


@contextmanager
def _stream_env(agent):
    """统一 patch 掉流式对话用到的外部依赖。"""
    with patch.object(agent_service, "get_agent_executor", return_value=(agent, "sys")), \
         patch.object(agent_service, "get_session_history", return_value=[]), \
         patch.object(agent_service, "compress_history_if_needed", side_effect=lambda m, *a, **k: m), \
         patch.object(agent_service, "create_message"), \
         patch.object(agent_service, "generate_session_title_task", return_value="标题"), \
         patch.object(agent_service, "config_manager") as cm, \
         patch.object(agent_service, "_model_context_window", return_value=1000):
        cm.get_user_config.return_value = _config(_ai_settings())
        yield cm


@pytest.mark.asyncio
async def test_stream_emits_string_content_and_summary_reasoning():
    agent = _FakeAgent([
        (_chunk("你好"), {"langgraph_node": "agent"}),
        (_chunk("", extra={"summary": [{"text": "想一想"}]}), {"langgraph_node": "model"}),
    ])
    with _stream_env(agent):
        events = await _collect(agent_service.stream_chat_with_agent("u", SESSION_ID, "hi", MagicMock()))
    payloads = [json.loads(item[len("data: "):]) for item in events if item.startswith("data: {")]
    assert any(p.get("content") == "你好" for p in payloads)
    assert any(p.get("reasoning") == "想一想" for p in payloads)
    assert events[-1].strip() == "data: [DONE]"


@pytest.mark.asyncio
async def test_stream_emits_list_content_text_and_reasoning_blocks():
    agent = _FakeAgent([
        (_chunk([{"type": "text", "text": "正文"}], chunk_type="AIMessageChunk"),
         {"langgraph_node": "agent"}),
        (_chunk([{"type": "reasoning", "summary": [{"text": "推理"}]}], chunk_type="AIMessageChunk"),
         {"langgraph_node": "agent"}),
    ])
    with _stream_env(agent):
        events = await _collect(agent_service.stream_chat_with_agent("u", SESSION_ID, "hi", MagicMock()))
    payloads = [json.loads(item[len("data: "):]) for item in events if item.startswith("data: {")]
    assert any(p.get("content") == "正文" for p in payloads)
    assert any(p.get("reasoning") == "推理" for p in payloads)


@pytest.mark.asyncio
async def test_stream_emits_tool_end_and_search_result_reference():
    tool_chunk = SimpleNamespace(type="tool", content=json.dumps({"search_result": {"id": "s1", "total": 2}}),
                                 additional_kwargs={}, tool_calls=[], name="search_library_photos",
                                 tool_call_id="tc-1", status="success")
    agent = _FakeAgent([(tool_chunk, {"langgraph_node": "tools"})])
    with _stream_env(agent):
        events = await _collect(agent_service.stream_chat_with_agent("u", SESSION_ID, "hi", MagicMock()))
    payloads = [json.loads(item[len("data: "):]) for item in events if item.startswith("data: {")]
    assert any(p.get("type") == "tool_end" and p.get("tool_name") == "search_library_photos" for p in payloads)
    assert any(p.get("type") == "search_result" and p["search_result"]["id"] == "s1" for p in payloads)


@pytest.mark.asyncio
async def test_stream_emits_search_tool_error_as_content():
    tool_chunk = SimpleNamespace(type="tool", content=json.dumps({"error": "索引坏了"}),
                                 additional_kwargs={}, tool_calls=[], name="search_library_photos",
                                 tool_call_id="tc-1", status="success")
    agent = _FakeAgent([(tool_chunk, {"langgraph_node": "tools"})])
    with _stream_env(agent):
        events = await _collect(agent_service.stream_chat_with_agent("u", SESSION_ID, "hi", MagicMock()))
    payloads = [json.loads(item[len("data: "):]) for item in events if item.startswith("data: {")]
    assert any("索引坏了" in (p.get("content") or "") for p in payloads)
    assert any(p.get("type") == "tool_end" and p.get("status") == "error" for p in payloads)


@pytest.mark.asyncio
async def test_stream_emits_artifact_and_action_plan_references():
    artifact_chunk = SimpleNamespace(type="tool", content=json.dumps({"artifact": {"id": "a1"}}),
                                     additional_kwargs={}, tool_calls=[], name="create_artifact_draft",
                                     tool_call_id="tc-2", status="success")
    plan_chunk = SimpleNamespace(type="tool", content=json.dumps({"action_plan": {"id": "p1"}}),
                                 additional_kwargs={}, tool_calls=[], name="propose_album_repairs",
                                 tool_call_id="tc-3", status="success")
    agent = _FakeAgent([(artifact_chunk, {"langgraph_node": "tools"}),
                        (plan_chunk, {"langgraph_node": "tools"})])
    with _stream_env(agent):
        events = await _collect(agent_service.stream_chat_with_agent("u", SESSION_ID, "hi", MagicMock()))
    payloads = [json.loads(item[len("data: "):]) for item in events if item.startswith("data: {")]
    assert any(p.get("type") == "artifact" and p["artifact"]["id"] == "a1" for p in payloads)
    assert any(p.get("type") == "action_plan" and p["action_plan"]["id"] == "p1" for p in payloads)
