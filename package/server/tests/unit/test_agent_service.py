"""Unit tests for ``app/service/agent/service.py`` helpers.

Covers the low-level helpers that the agent REST router (and chat
loop) rely on, without touching LangChain / Postgres. The DB session
is a ``MagicMock`` and LangChain ``trim_messages`` is patched so we
can verify the pure-Python behaviour deterministically.

Scenarios:
* ``abort_chat_session`` writes into the module-level aborted set
* ``get_session_history`` maps ``user`` / ``assistant`` / ``system``
  roles into LangChain ``HumanMessage`` / ``AIMessage`` / ``SystemMessage``
* ``get_session_history`` ignores unknown roles
* ``trim_history_messages`` returns the input when given an empty list
* ``trim_history_messages`` delegates to ``trim_messages`` with the
  sliding-window parameters and falls back to the original list on
  trim failure
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.service.agent import service as agent_service


pytestmark = [pytest.mark.smoke, pytest.mark.module_agent]


# ---------------------------------------------------------------------------
# abort_chat_session
# ---------------------------------------------------------------------------

def test_abort_chat_session_marks_session_aborted():
    session_id = "session-1"

    # ensure the global state starts clean for this id
    agent_service._aborted_sessions.pop(session_id, None)

    agent_service.abort_chat_session(session_id)

    assert agent_service._aborted_sessions[session_id] is True


# ---------------------------------------------------------------------------
# get_session_history
# ---------------------------------------------------------------------------

def _msg(role, content):
    return SimpleNamespace(role=role, content=content)


def test_get_session_history_maps_known_roles_to_langchain_messages():
    db_messages = [
        _msg("system", "sys-prompt"),
        _msg("user", "hi"),
        _msg("assistant", "hello"),
    ]
    db = MagicMock()

    with patch.object(agent_service, "get_messages_by_session", return_value=db_messages):
        history = agent_service.get_session_history(db, "session-1")

    assert len(history) == 3
    assert isinstance(history[0], SystemMessage)
    assert history[0].content == "sys-prompt"
    assert isinstance(history[1], HumanMessage)
    assert history[1].content == "hi"
    assert isinstance(history[2], AIMessage)
    assert history[2].content == "hello"


def test_get_session_history_skips_unknown_roles():
    db_messages = [
        _msg("user", "hi"),
        _msg("tool", "tool-output"),
        _msg("assistant", "hello"),
    ]
    db = MagicMock()

    with patch.object(agent_service, "get_messages_by_session", return_value=db_messages):
        history = agent_service.get_session_history(db, "session-1")

    # the tool-role message must be skipped
    assert [type(m).__name__ for m in history] == ["HumanMessage", "AIMessage"]
    assert history[0].content == "hi"
    assert history[1].content == "hello"


# ---------------------------------------------------------------------------
# trim_history_messages
# ---------------------------------------------------------------------------

def test_trim_history_messages_returns_input_on_empty():
    assert agent_service.trim_history_messages([]) == []


def test_trim_history_messages_delegates_to_trim_messages_with_sliding_window():
    messages = [HumanMessage(content=str(i)) for i in range(5)]

    with patch.object(agent_service, "trim_messages", return_value=messages[:3]) as trim_call:
        trimmed = agent_service.trim_history_messages(messages)

    # ensure sliding-window parameters are passed
    args, kwargs = trim_call.call_args
    assert args[0] is messages
    assert kwargs["max_tokens"] == agent_service.MAX_HISTORY_MESSAGES
    assert kwargs["strategy"] == "last"
    assert kwargs["token_counter"] is len
    assert kwargs["include_system"] is True
    assert kwargs["start_on"] == "human"
    assert trimmed == messages[:3]


def test_trim_history_messages_falls_back_when_trim_returns_empty():
    messages = [HumanMessage(content="hi"), AIMessage(content="hello")]

    with patch.object(agent_service, "trim_messages", return_value=[]):
        trimmed = agent_service.trim_history_messages(messages)

    # fallback to original history
    assert trimmed is messages


def test_trim_history_messages_falls_back_when_trim_raises():
    messages = [HumanMessage(content="hi")]

    with patch.object(agent_service, "trim_messages", side_effect=RuntimeError("boom")):
        trimmed = agent_service.trim_history_messages(messages)

    assert trimmed is messages


# ---------------------------------------------------------------------------
# compress_history_if_needed（上下文压缩）
# ---------------------------------------------------------------------------

def _convo(n):
    """构造 n 条 human/ai 交替的对话消息。"""
    out = []
    for i in range(n):
        if i % 2 == 0:
            out.append(HumanMessage(content=f"u{i}"))
        else:
            out.append(AIMessage(content=f"a{i}"))
    return out


def test_compress_below_trigger_uses_sliding_window():
    """对话未超过触发阈值时，退化为滑动窗口，不调用摘要 LLM。"""
    db = MagicMock()
    messages = [SystemMessage(content="sys")] + _convo(agent_service.COMPRESSION_TRIGGER)

    with patch.object(agent_service, "trim_history_messages", return_value=messages) as trim, \
         patch.object(agent_service, "_get_summary_llm") as get_llm:
        out = agent_service.compress_history_if_needed(messages, "uid", "sid", db)

    trim.assert_called_once()
    get_llm.assert_not_called()
    assert out == messages


def test_compress_falls_back_when_no_llm():
    """历史超阈值但拿不到摘要模型时，回退到滑动窗口。"""
    db = MagicMock()
    messages = [SystemMessage(content="sys")] + _convo(agent_service.COMPRESSION_TRIGGER + 10)

    with patch.object(agent_service, "_get_summary_llm", return_value=None), \
         patch.object(agent_service, "trim_history_messages", return_value=["fallback"]) as trim:
        out = agent_service.compress_history_if_needed(messages, "uid", "sid", db)

    trim.assert_called_once()
    assert out == ["fallback"]


def test_compress_builds_summary_and_keeps_recent():
    """历史超阈值时：生成摘要 + 保留 system + 最近 KEEP_RECENT_MESSAGES 条，并持久化摘要。"""
    db = MagicMock()
    system = SystemMessage(content="sys")
    convo = _convo(agent_service.COMPRESSION_TRIGGER + 10)
    messages = [system] + convo

    fake_llm = MagicMock()
    fake_llm.invoke.return_value = SimpleNamespace(content="摘要要点")

    with patch.object(agent_service, "_get_summary_llm", return_value=fake_llm), \
         patch.object(agent_service.agent_crud, "get_context_summary", return_value=None), \
         patch.object(agent_service.agent_crud, "update_context_summary") as upd:
        out = agent_service.compress_history_if_needed(messages, "uid", "sid", db)

    # 结构：system + 摘要 + 最近 KEEP_RECENT_MESSAGES 条
    assert out[0] is system
    assert isinstance(out[1], SystemMessage)
    assert "摘要要点" in out[1].content
    recent = out[2:]
    assert len(recent) == agent_service.KEEP_RECENT_MESSAGES
    assert recent == convo[-agent_service.KEEP_RECENT_MESSAGES:]
    # 摘要被持久化
    upd.assert_called_once()


def test_compress_merges_previous_summary():
    """已有历史摘要时，会把旧摘要一并喂给 LLM 做增量合并。"""
    db = MagicMock()
    messages = [SystemMessage(content="sys")] + _convo(agent_service.COMPRESSION_TRIGGER + 10)

    fake_llm = MagicMock()
    fake_llm.invoke.return_value = SimpleNamespace(content="新摘要")

    with patch.object(agent_service, "_get_summary_llm", return_value=fake_llm), \
         patch.object(agent_service.agent_crud, "get_context_summary", return_value="旧摘要内容"), \
         patch.object(agent_service.agent_crud, "update_context_summary"):
        agent_service.compress_history_if_needed(messages, "uid", "sid", db)

    # 传给 LLM 的 prompt 里应包含旧摘要
    prompt = fake_llm.invoke.call_args[0][0][0].content
    assert "旧摘要内容" in prompt


def test_compress_falls_back_when_llm_raises():
    """摘要 LLM 调用抛异常时，回退到滑动窗口，不中断对话。"""
    db = MagicMock()
    messages = [SystemMessage(content="sys")] + _convo(agent_service.COMPRESSION_TRIGGER + 10)

    fake_llm = MagicMock()
    fake_llm.invoke.side_effect = RuntimeError("llm boom")

    with patch.object(agent_service, "_get_summary_llm", return_value=fake_llm), \
         patch.object(agent_service.agent_crud, "get_context_summary", return_value=None), \
         patch.object(agent_service, "trim_history_messages", return_value=["fallback"]) as trim:
        out = agent_service.compress_history_if_needed(messages, "uid", "sid", db)

    trim.assert_called_once()
    assert out == ["fallback"]
