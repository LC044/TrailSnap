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
