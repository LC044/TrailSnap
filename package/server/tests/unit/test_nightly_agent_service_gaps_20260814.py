"""Unit tests covering 2026-08-14 nightly coverage gap scan.

Modules exercised:
* app/service/agent/service.py -- get_session_history (user/assistant/system
  message construction), get_agent_executor (missing config, missing connection,
  disabled connection, missing api_key), chat_with_agent (happy path with
  reasoning + tool_calls, exception path returns error string),
  generate_session_title_task (success path with quote stripping, disabled
  connection returns None, missing model returns None).
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, AsyncMock

import pytest
SAMPLE_USER_ID = '00000000-0000-0000-0000-000000000001'
SAMPLE_SESSION_ID = '00000000-0000-0000-0000-000000000002'


pytestmark = [pytest.mark.smoke]


def test_get_session_history_builds_messages_by_role():
    from app.service.agent import service as agent_service

    db = MagicMock()
    db_messages = [
        SimpleNamespace(role="user", content="hi"),
        SimpleNamespace(role="assistant", content="hello"),
        SimpleNamespace(role="system", content="be brief"),
        SimpleNamespace(role="unknown", content="ignored"),
    ]
    with patch("app.service.agent.service.get_messages_by_session", return_value=db_messages):
        history = agent_service.get_session_history(db, "sess-1")

    from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
    assert isinstance(history[0], HumanMessage)
    assert history[0].content == "hi"
    assert isinstance(history[1], AIMessage)
    assert history[1].content == "hello"
    assert isinstance(history[2], SystemMessage)
    assert history[2].content == "be brief"
    # Unknown role -> message is dropped, no crash
    assert len(history) == 3


def test_get_session_history_passes_session_id_and_limit():
    from app.service.agent import service as agent_service

    db = MagicMock()
    with patch("app.service.agent.service.get_messages_by_session", return_value=[]) as gm:
        agent_service.get_session_history(db, "sess-42")
    gm.assert_called_once_with(db, "sess-42", limit=100)


# --- get_agent_executor validation paths -----------------------------------


def _make_user_config(*, conn_id="conn-1", model="gpt-4", enable=True, api_key="sk"):
    conn = SimpleNamespace(
        id=conn_id,
        enable=enable,
        api_key=api_key,
        api_base="https://api.openai.com/v1",
    )
    return SimpleNamespace(
        ai=SimpleNamespace(
            analysis_connection_id=conn_id,
            analysis_model_name=model,
            connections=[conn],
        )
    )


def test_get_agent_executor_raises_when_missing_connection_id():
    from app.service.agent import service as agent_service

    db = MagicMock()
    uc = _make_user_config()
    uc.ai.analysis_connection_id = None
    with patch.object(agent_service, "config_manager") as cm:
        cm.get_user_config.return_value = uc
        with pytest.raises(ValueError, match="未配置智能分析模型"):
            agent_service.get_agent_executor(SAMPLE_USER_ID, SAMPLE_SESSION_ID, db)


def test_get_agent_executor_raises_when_missing_model_name():
    from app.service.agent import service as agent_service

    db = MagicMock()
    uc = _make_user_config()
    uc.ai.analysis_model_name = None
    with patch.object(agent_service, "config_manager") as cm:
        cm.get_user_config.return_value = uc
        with pytest.raises(ValueError, match="未配置智能分析模型"):
            agent_service.get_agent_executor(SAMPLE_USER_ID, SAMPLE_SESSION_ID, db)


def test_get_agent_executor_raises_when_connection_not_found():
    from app.service.agent import service as agent_service

    db = MagicMock()
    uc = _make_user_config()
    uc.ai.connections = []  # connection missing
    with patch.object(agent_service, "config_manager") as cm:
        cm.get_user_config.return_value = uc
        with pytest.raises(ValueError, match="未找到指定的 AI 连接配置"):
            agent_service.get_agent_executor(SAMPLE_USER_ID, SAMPLE_SESSION_ID, db)


def test_get_agent_executor_raises_when_connection_disabled():
    from app.service.agent import service as agent_service

    db = MagicMock()
    uc = _make_user_config(enable=False)
    with patch.object(agent_service, "config_manager") as cm:
        cm.get_user_config.return_value = uc
        with pytest.raises(ValueError, match="已禁用"):
            agent_service.get_agent_executor(SAMPLE_USER_ID, SAMPLE_SESSION_ID, db)


def test_get_agent_executor_raises_when_api_key_missing():
    from app.service.agent import service as agent_service

    db = MagicMock()
    uc = _make_user_config(api_key="")
    with patch.object(agent_service, "config_manager") as cm:
        cm.get_user_config.return_value = uc
        with pytest.raises(ValueError, match="未配置 API Key"):
            agent_service.get_agent_executor(SAMPLE_USER_ID, SAMPLE_SESSION_ID, db)


# --- chat_with_agent ------------------------------------------------------


def test_chat_with_agent_saves_messages_and_returns_ai_content():
    from app.service.agent import service as agent_service

    db = MagicMock()
    final_msg = SimpleNamespace(
        content="answer",
        additional_kwargs={"reasoning_content": "why"},
        tool_calls=[{"name": "search_photos", "args": {"q": "beach"}}],
    )
    fake_agent = MagicMock()
    fake_agent.invoke.return_value = {"messages": [final_msg]}
    uc = _make_user_config()

    with patch.object(agent_service, "get_agent_executor", return_value=(fake_agent, "sys")) as gae, \
         patch("app.service.agent.service.get_session_history", return_value=[]), \
         patch("app.service.agent.service.create_message") as cm, \
         patch("app.service.agent.service.trim_history_messages", side_effect=lambda m: m):
        result = agent_service.chat_with_agent(SAMPLE_USER_ID, SAMPLE_SESSION_ID, "user q", db)

    assert result == "answer"
    gae.assert_called_once()
    # User + assistant messages saved
    assert cm.call_count == 2


def test_chat_with_agent_handles_exception_and_returns_error_string():
    from app.service.agent import service as agent_service

    db = MagicMock()
    fake_agent = MagicMock()
    fake_agent.invoke.side_effect = RuntimeError("boom")
    uc = _make_user_config()

    with patch.object(agent_service, "get_agent_executor", return_value=(fake_agent, "sys")), \
         patch("app.service.agent.service.get_session_history", return_value=[]), \
         patch("app.service.agent.service.create_message"), \
         patch("app.service.agent.service.trim_history_messages", side_effect=lambda m: m):
        result = agent_service.chat_with_agent(SAMPLE_USER_ID, SAMPLE_SESSION_ID, "user q", db)

    assert "抱歉" in result
    assert "boom" in result


# --- generate_session_title_task ------------------------------------------


def test_generate_session_title_task_returns_none_when_no_config():
    from app.service.agent import service as agent_service

    uc = _make_user_config()
    uc.ai.analysis_connection_id = None
    # Patch the source module where generate_session_title_task actually
    # imports config_manager from. Patching only agent_service.config_manager
    # leaves the singleton at app.core.config_manager.config_manager
    # untouched, so the function reads from there. Other test modules
    # (test_gallery_service.py) permanently monkey-patch
    # config_manager.get_user_config via raw attribute assignment, which
    # pollutes the singleton and silently breaks this test when run in
    # combination. Patching the source module sidesteps that pollution.
    with patch("app.core.config_manager.config_manager") as cm, \
         patch("app.db.session.SessionLocal") as sl:
        sl.return_value.__enter__.return_value = MagicMock()
        cm.get_user_config.return_value = uc
        result = agent_service.generate_session_title_task(SAMPLE_USER_ID, SAMPLE_SESSION_ID, "user q")
    assert result is None


def test_generate_session_title_task_returns_none_when_disabled():
    from app.service.agent import service as agent_service

    uc = _make_user_config(enable=False)
    with patch("app.core.config_manager.config_manager") as cm, \
         patch("app.db.session.SessionLocal") as sl:
        sl.return_value.__enter__.return_value = MagicMock()
        cm.get_user_config.return_value = uc
        result = agent_service.generate_session_title_task(SAMPLE_USER_ID, SAMPLE_SESSION_ID, "user q")
    assert result is None


def test_generate_session_title_task_strips_surrounding_quotes():
    from app.service.agent import service as agent_service

    db = MagicMock()
    session = SimpleNamespace(id="s")
    llm = MagicMock()
    llm.invoke.return_value = SimpleNamespace(content='"我的旅行"')
    uc = _make_user_config()

    # Same rationale as the helpers above -- patch the source module that
    # generate_session_title_task imports config_manager / SessionLocal from.
    with patch("app.core.config_manager.config_manager") as cm, \
         patch("app.db.session.SessionLocal") as sl, \
         patch("langchain_openai.ChatOpenAI", return_value=llm), \
         patch("app.crud.agent.get_session", return_value=session), \
         patch("app.crud.agent.update_session") as us:
        sl.return_value.__enter__.return_value = db
        sl.return_value.__exit__.return_value = False
        cm.get_user_config.return_value = uc
        title = agent_service.generate_session_title_task(SAMPLE_USER_ID, SAMPLE_SESSION_ID, "first message")

    assert title == "我的旅行"
    us.assert_called_once()
