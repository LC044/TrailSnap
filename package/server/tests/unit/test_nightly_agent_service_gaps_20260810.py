"""Nightly watch gap coverage for app.service.agent.service.

Targets helper functions in ``service.py`` that the existing
``test_agent_api.py`` does not exercise (lines 32-227 missed in nightly scan).

* ``abort_chat_session`` - pure state mutator on the module-level dict.
* ``trim_history_messages`` - sliding-window trim with system message preservation.
* ``FixedChatOpenAI._convert_chunk_to_generation_chunk`` - reasoning passthrough.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.service.agent import service as agent_service


pytestmark = [pytest.mark.smoke]


# -------------------- abort_chat_session --------------------


def test_abort_chat_session_marks_session_in_global_dict():
    """abort_chat_session must flip the flag in ``_aborted_sessions`` to True."""
    session_id = "sess-abort-001"
    # Clean slate so the assertion is deterministic.
    agent_service._aborted_sessions.pop(session_id, None)
    try:
        agent_service.abort_chat_session(session_id)
        assert agent_service._aborted_sessions[session_id] is True
    finally:
        agent_service._aborted_sessions.pop(session_id, None)


def test_abort_chat_session_does_not_clear_other_flags():
    """Setting one session aborted must not disturb other sessions."""
    keep = "sess-keep"
    target = "sess-target"
    agent_service._aborted_sessions.update({keep: False, target: False})
    try:
        agent_service.abort_chat_session(target)
        assert agent_service._aborted_sessions[keep] is False
        assert agent_service._aborted_sessions[target] is True
    finally:
        agent_service._aborted_sessions.pop(keep, None)
        agent_service._aborted_sessions.pop(target, None)


# -------------------- trim_history_messages --------------------


def _human(content):
    return SimpleNamespace(content=content, type="human")


def _system(content):
    return SimpleNamespace(content=content, type="system")


def test_trim_history_messages_empty_input_returns_empty():
    assert agent_service.trim_history_messages([]) == []


def test_trim_history_messages_preserves_system_and_keeps_recent_window(monkeypatch):
    """The trimmer must keep the system prompt and only the most-recent messages."""
    captured = {}

    def fake_trim(messages, **kwargs):
        captured["messages"] = messages
        captured["kwargs"] = kwargs
        max_tokens = kwargs["max_tokens"]
        if len(messages) <= max_tokens + 1:
            return messages
        return [messages[0], *messages[-max_tokens:]]

    monkeypatch.setattr(agent_service, "trim_messages", fake_trim)

    system = _system("sys-prompt")
    human = [_human("h{0}".format(i)) for i in range(30)]
    messages = [system, *human]

    trimmed = agent_service.trim_history_messages(messages)

    assert trimmed[0] is system
    assert captured["kwargs"]["max_tokens"] == agent_service.MAX_HISTORY_MESSAGES
    assert captured["kwargs"]["strategy"] == "last"
    assert captured["kwargs"]["include_system"] is True
    assert len(trimmed) == 21


def test_trim_history_messages_falls_back_to_full_history_when_trim_returns_empty(monkeypatch):
    """If trim_messages returns falsy, the original list must be returned intact."""

    def fake_trim(messages, **kwargs):
        return []

    monkeypatch.setattr(agent_service, "trim_messages", fake_trim)

    original = [_system("sys"), _human("a"), _human("b")]
    result = agent_service.trim_history_messages(original)
    assert result is original


def test_trim_history_messages_falls_back_when_trim_raises(monkeypatch):
    """If trim_messages raises, the original list must be returned intact."""

    def fake_trim(messages, **kwargs):
        raise RuntimeError("tokeniser missing")

    monkeypatch.setattr(agent_service, "trim_messages", fake_trim)

    original = [_system("sys"), _human("a")]
    result = agent_service.trim_history_messages(original)
    assert result is original


# -------------------- FixedChatOpenAI._convert_chunk_to_generation_chunk --------------------


def _make_wrapper():
    """Construct a FixedChatOpenAI without invoking __init__."""
    instance = agent_service.FixedChatOpenAI.__new__(agent_service.FixedChatOpenAI)
    return instance


def test_convert_chunk_populates_reasoning_summary_when_delta_has_reasoning():
    """Reasoning text in the delta must be appended to additional_kwargs.summary."""
    instance = _make_wrapper()

    base_message = MagicMock()
    base_message.content = ""
    base_message.additional_kwargs = {}

    parent_result = MagicMock()
    parent_result.message = base_message

    chunk = {"choices": [{"delta": {"reasoning": "thinking hard"}}]}

    with patch(
        "langchain_openai.ChatOpenAI._convert_chunk_to_generation_chunk",
        return_value=parent_result,
    ):
        result = instance._convert_chunk_to_generation_chunk(
            chunk,
            default_chunk_class=MagicMock(),
            base_generation_info=None,
        )

    assert result is parent_result
    assert base_message.additional_kwargs["type"] == "reasoning"
    assert base_message.additional_kwargs["summary"] == [
        {"index": 0, "type": "summary_text", "text": "thinking hard"}
    ]


def test_convert_chunk_skips_when_message_already_has_content():
    """If the base message already carries content, the reasoning pass-through is a no-op."""
    instance = _make_wrapper()

    base_message = MagicMock()
    base_message.content = "already has content"
    parent_result = MagicMock()
    parent_result.message = base_message

    chunk = {"choices": [{"delta": {"reasoning": "should be ignored"}}]}

    with patch(
        "langchain_openai.ChatOpenAI._convert_chunk_to_generation_chunk",
        return_value=parent_result,
    ):
        result = instance._convert_chunk_to_generation_chunk(
            chunk,
            default_chunk_class=MagicMock(),
            base_generation_info=None,
        )

    assert result is parent_result
