"""2026-10-30 nightly coverage for the context handling in
``app/service/agent/service.py``.

The 2026-10-30 backend scan reported ``service/agent/service.py`` at 92.1%
with 38 uncovered lines.  The uncovered part is the **context window**
plumbing that decides what the model actually sees:

* ``_estimate_message_tokens`` / ``_model_context_window`` -- the tokenizer
  free estimate and the per-model window lookup;
* ``trim_history_messages`` -- the sliding window, including its "fall back to
  the full history" safety net;
* ``_messages_to_text`` -- the readable transcript handed to the summariser;
* ``compress_history_if_needed`` -- the summary + recent-messages path, its
  fallbacks and the non-fatal summary persistence;
* ``generate_session_title_task`` -- the first-question title, including the
  quote stripping;
* ``abort_chat_session`` -- the manual stop flag.

A silent mistake here truncates the user's conversation history or loses the
summary, which is hard to notice and hard to recover from.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.service.agent import service


pytestmark = [pytest.mark.smoke, pytest.mark.module_agent]


def _conversation(count=4, length=2000):
    messages = [SystemMessage(content="系统提示")]
    for index in range(count):
        messages.append(HumanMessage(content=f"问题{index}" + "内容" * length))
        messages.append(AIMessage(content=f"回答{index}" + "内容" * length))
    return messages


# ---------------------------------------------------------------------------
# _estimate_message_tokens
# ---------------------------------------------------------------------------


def test_estimate_message_tokens_counts_string_content():
    messages = [HumanMessage(content="a" * 30)]

    # 30 characters -> 10 tokens + 8 overhead
    assert service._estimate_message_tokens(messages) == 18


def test_estimate_message_tokens_serialises_structured_content():
    messages = [HumanMessage(content=[{"type": "text", "text": "x" * 30}])]

    assert service._estimate_message_tokens(messages) >= 8


def test_estimate_message_tokens_never_returns_zero():
    assert service._estimate_message_tokens([HumanMessage(content="")]) >= 8


# ---------------------------------------------------------------------------
# _model_context_window
# ---------------------------------------------------------------------------


def _ai_settings(window=8192):
    model = SimpleNamespace(model_name="m1", context_window=window)
    connection = SimpleNamespace(id="c1", models=[model])
    return SimpleNamespace(
        chat_connection_id="c1", chat_model_name="m1",
        analysis_connection_id="c1", analysis_model_name="m1",
        connections=[connection],
    )


def test_model_context_window_uses_the_configured_model():
    assert service._model_context_window(_ai_settings()) == 8192


def test_model_context_window_falls_back_to_the_default():
    settings = _ai_settings()
    settings.chat_model_name = "unknown-model"

    assert service._model_context_window(settings) == 128000


def test_model_context_window_accepts_an_explicit_override():
    assert service._model_context_window(_ai_settings(), model_name="m1", connection_id="c1") == 8192


# ---------------------------------------------------------------------------
# trim_history_messages
# ---------------------------------------------------------------------------


def test_trim_history_messages_returns_an_empty_history_unchanged():
    assert service.trim_history_messages([]) == []


def test_trim_history_messages_trims_to_the_context_window():
    messages = _conversation(count=6)

    trimmed = service.trim_history_messages(messages, context_window=4096)

    assert len(trimmed) < len(messages)
    assert isinstance(trimmed[0], SystemMessage)
    assert trimmed[-1].content == messages[-1].content


def test_trim_history_messages_falls_back_to_the_full_history_on_error():
    messages = _conversation(count=2)

    with patch.object(service, "trim_messages", side_effect=RuntimeError("boom")):
        trimmed = service.trim_history_messages(messages)

    assert trimmed is messages


# ---------------------------------------------------------------------------
# _messages_to_text
# ---------------------------------------------------------------------------


def test_messages_to_text_labels_the_roles_and_skips_system_messages():
    text = service._messages_to_text([
        HumanMessage(content="你好"),
        AIMessage(content="在的"),
        SystemMessage(content="系统"),
        HumanMessage(content=""),
    ])

    assert text == "用户：你好\n助手：在的"


# ---------------------------------------------------------------------------
# compress_history_if_needed
# ---------------------------------------------------------------------------


def test_compress_history_returns_an_empty_history_unchanged():
    assert service.compress_history_if_needed([], "u", "s", MagicMock()) == []


def test_compress_history_keeps_short_histories_within_the_token_budget():
    messages = _conversation(count=1, length=10)

    compressed = service.compress_history_if_needed(
        messages, "u", "s", MagicMock(), context_window=128000
    )

    assert compressed is messages


def test_compress_history_falls_back_to_the_sliding_window_without_a_summary_model():
    messages = _conversation(count=4, length=10)
    db = MagicMock()

    with patch.object(service, "_get_summary_llm", return_value=None):
        compressed = service.compress_history_if_needed(messages, "u", "s", db)

    assert compressed is not messages
    assert len(compressed) <= len(messages)


def test_compress_history_replaces_old_messages_with_a_summary():
    messages = _conversation(count=6, length=200)
    db = MagicMock()
    llm = MagicMock()
    llm.invoke.return_value = SimpleNamespace(content="  历史摘要内容  ")

    with patch.object(service, "_get_summary_llm", return_value=llm), \
            patch.object(service.agent_crud, "get_context_summary", return_value=""), \
            patch.object(service.agent_crud, "update_context_summary") as persist:
        compressed = service.compress_history_if_needed(
            messages, "u", "s", db, context_window=1024
        )

    assert isinstance(compressed[0], SystemMessage)
    assert "历史对话摘要" in compressed[1].content
    assert "历史摘要内容" in compressed[1].content
    assert len(compressed) <= len(messages)
    persist.assert_called_once_with(db, "s", "历史摘要内容")


def test_compress_history_survives_a_failing_summary_persistence():
    messages = _conversation(count=6, length=200)
    db = MagicMock()
    llm = MagicMock()
    llm.invoke.return_value = SimpleNamespace(content="摘要")

    with patch.object(service, "_get_summary_llm", return_value=llm), \
            patch.object(service.agent_crud, "get_context_summary", return_value=""), \
            patch.object(service.agent_crud, "update_context_summary", side_effect=RuntimeError("db down")):
        compressed = service.compress_history_if_needed(
            messages, "u", "s", db, context_window=1024
        )

    assert any("摘要" in getattr(message, "content", "") for message in compressed)


def test_compress_history_falls_back_when_the_summary_call_fails():
    messages = _conversation(count=6, length=200)
    db = MagicMock()
    llm = MagicMock()
    llm.invoke.side_effect = RuntimeError("llm down")

    with patch.object(service, "_get_summary_llm", return_value=llm):
        compressed = service.compress_history_if_needed(
            messages, "u", "s", db, context_window=1024
        )

    assert isinstance(compressed, list)


# ---------------------------------------------------------------------------
# generate_session_title_task
# ---------------------------------------------------------------------------


def _title_patch(llm_response):
    llm = MagicMock()
    llm.invoke.return_value = llm_response
    return llm


def test_generate_session_title_strips_surrounding_quotes():
    llm = _title_patch(SimpleNamespace(content='"我的旅行"'))
    settings = SimpleNamespace(
        analysis_connection_id="c1", analysis_model_name="m1",
        connections=[SimpleNamespace(id="c1", enable=True, api_key="k", api_base=None)],
    )

    with patch("langchain_openai.ChatOpenAI", return_value=llm), \
            patch("app.core.config_manager.config_manager.get_user_config",
                  return_value=SimpleNamespace(ai=settings)), \
            patch.object(service, "SessionLocal"), \
            patch("app.crud.agent.get_session", return_value=None):
        title = service.generate_session_title_task(str(uuid.uuid4()), "s", "第一次提问")

    assert title == "我的旅行"


def test_generate_session_title_returns_none_without_a_configured_model():
    settings = SimpleNamespace(analysis_connection_id=None, analysis_model_name=None, connections=[])

    with patch("app.core.config_manager.config_manager.get_user_config",
               return_value=SimpleNamespace(ai=settings)), \
            patch.object(service, "SessionLocal"):
        assert service.generate_session_title_task(str(uuid.uuid4()), "s", "第一次提问") is None


def test_generate_session_title_returns_none_when_the_model_fails():
    with patch.object(service, "SessionLocal"), \
            patch("app.core.config_manager.config_manager.get_user_config",
                  side_effect=RuntimeError("no config")):
        assert service.generate_session_title_task(str(uuid.uuid4()), "s", "第一次提问") is None


# ---------------------------------------------------------------------------
# abort_chat_session
# ---------------------------------------------------------------------------


def test_abort_chat_session_marks_the_session():
    service.abort_chat_session("session-1")

    assert service._aborted_sessions.get("session-1") is True