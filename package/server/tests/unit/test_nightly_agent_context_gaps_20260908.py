"""Nightly gap tests for Agent context compression (2026-09-08).

Targets ``app/service/agent/service.py`` helpers that remained uncovered:
structured message serialization, summary LLM construction, and successful
history compression with persisted context.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

pytestmark = [pytest.mark.smoke]

USER_ID = "00000000-0000-0000-0000-000000000001"
SESSION_ID = "00000000-0000-0000-0000-000000000002"


def test_messages_to_text_serializes_structured_content():
    from app.service.agent import service as agent_service

    messages = [
        SystemMessage(content="system prompt"),
        HumanMessage(content=[{"type": "text", "text": "找上周的西湖照片"}]),
        AIMessage(content=[{"type": "text", "text": "找到 3 张"}]),
        HumanMessage(content=""),
    ]

    text = agent_service._messages_to_text(messages)

    assert "system prompt" not in text
    assert "用户：" in text
    assert "助手：" in text
    assert "找上周的西湖照片" in text
    assert "找到 3 张" in text
    assert text.count("\n") == 1  # empty content is omitted


def test_get_summary_llm_uses_configured_analysis_connection():
    from app.service.agent import service as agent_service

    connection = SimpleNamespace(
        id="analysis-1",
        enable=True,
        api_key="sk-test",
        api_base="https://api.example.com/v1",
    )
    user_config = SimpleNamespace(
        ai=SimpleNamespace(
            analysis_connection_id="analysis-1",
            analysis_model_name="summary-model",
            connections=[connection],
        )
    )
    db = object()

    with patch.object(agent_service.config_manager, "get_user_config", return_value=user_config):
        with patch.object(agent_service, "ChatOpenAI") as chat_openai:
            result = agent_service._get_summary_llm(USER_ID, db)

    assert result is chat_openai.return_value
    kwargs = chat_openai.call_args.kwargs
    assert kwargs["model"] == "summary-model"
    assert kwargs["api_key"] == "sk-test"
    assert kwargs["base_url"] == "https://api.example.com/v1"
    assert kwargs["temperature"] == 0.2
    assert kwargs["timeout"] == 30


def test_compress_history_if_needed_persists_summary_and_keeps_recent():
    from app.service.agent import service as agent_service

    system = SystemMessage(content="system prompt")
    old = [HumanMessage(content=f"old-{i}") for i in range(25)]
    recent = [HumanMessage(content=f"recent-{i}") for i in range(10)]
    messages = [system] + old + recent

    llm = SimpleNamespace(invoke=MagicMock(return_value=SimpleNamespace(content="摘要内容")))
    db = object()

    with patch.object(agent_service, "_get_summary_llm", return_value=llm):
        with patch.object(agent_service.agent_crud, "get_context_summary", return_value="旧摘要") as get_summary:
            with patch.object(agent_service.agent_crud, "update_context_summary") as update_summary:
                result = agent_service.compress_history_if_needed(messages, USER_ID, SESSION_ID, db)

    get_summary.assert_called_once_with(db, SESSION_ID)
    update_summary.assert_called_once_with(db, SESSION_ID, "摘要内容")
    assert len(result) == 12
    assert result[0] is system
    assert isinstance(result[1], SystemMessage)
    assert "【历史对话摘要】" in result[1].content
    assert "摘要内容" in result[1].content
    assert result[2:] == recent
    assert all("old-" not in m.content for m in result[2:])

