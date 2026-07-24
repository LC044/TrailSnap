"""Unit tests for the agent REST router (app/api/agent.py).

Covers the chat / sessions / messages / abort / pin endpoints. The DB
session is replaced with a ``MagicMock`` and the agent service helpers
(``chat_with_agent``, ``stream_chat_with_agent``, ``abort_chat_session``)
are patched so no real LangChain / DB state is touched.

Scenarios:
* chat creates the session on first use and returns ``ChatResponse``
* chat surfaces ValueError as HTTP 400 (LLM not configured)
* chat surfaces generic Exception as HTTP 500
* abort_chat 404 / 403 / success
* delete_session 404 / 403 / 500 / success
* pin_session 404 / 403 / success
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api import agent as agent_api


pytestmark = [pytest.mark.smoke, pytest.mark.module_agent]


def _user(uid=None):
    return SimpleNamespace(id=uid or uuid4())


def _session(owner_id=None):
    return SimpleNamespace(
        id=uuid4(),
        user_id=owner_id or uuid4(),
        title="t",
        is_pinned=False,
    )


# ----------------------------- POST /chat ------------------------------


def test_chat_creates_session_when_missing_and_returns_reply():
    user = _user()
    db = MagicMock()
    request = agent_api.ChatRequest(message="hi", session_id=None)

    with patch.object(agent_api.agent_crud, "get_session", return_value=None) as get_session:
        with patch.object(agent_api.agent_crud, "create_session", return_value=_session(owner_id=user.id)) as create_session:
            with patch.object(agent_api, "chat_with_agent", return_value="hello back") as chat:
                response = agent_api.chat_endpoint(request=request, current_user=user, db=db)

    assert get_session.called
    assert create_session.called
    chat.assert_called_once()
    assert response.response == "hello back"
    assert response.session_id


def test_chat_reuses_existing_session_without_creating():
    user = _user()
    db = MagicMock()
    sid = uuid4()
    session = _session(owner_id=user.id)
    session.id = sid
    request = agent_api.ChatRequest(message="hi", session_id=str(sid))

    with patch.object(agent_api.agent_crud, "get_session", return_value=session) as get_session:
        with patch.object(agent_api.agent_crud, "create_session") as create_session:
            with patch.object(agent_api, "chat_with_agent", return_value="reply") as chat:
                response = agent_api.chat_endpoint(request=request, current_user=user, db=db)

    get_session.assert_called_once_with(db, str(sid))
    create_session.assert_not_called()
    chat.assert_called_once()
    assert response.session_id == str(sid)


def test_chat_returns_400_on_value_error():
    user = _user()
    db = MagicMock()
    request = agent_api.ChatRequest(message="hi", session_id=None)

    with patch.object(agent_api.agent_crud, "get_session", return_value=None):
        with patch.object(agent_api.agent_crud, "create_session", return_value=_session(owner_id=user.id)):
            with patch.object(agent_api, "chat_with_agent", side_effect=ValueError("no LLM")):
                with pytest.raises(HTTPException) as exc_info:
                    agent_api.chat_endpoint(request=request, current_user=user, db=db)

    assert exc_info.value.status_code == 400
    assert "no LLM" in str(exc_info.value.detail)


def test_chat_returns_500_on_unexpected_exception():
    user = _user()
    db = MagicMock()
    request = agent_api.ChatRequest(message="hi", session_id=None)

    with patch.object(agent_api.agent_crud, "get_session", return_value=None):
        with patch.object(agent_api.agent_crud, "create_session", return_value=_session(owner_id=user.id)):
            with patch.object(agent_api, "chat_with_agent", side_effect=RuntimeError("boom")):
                with pytest.raises(HTTPException) as exc_info:
                    agent_api.chat_endpoint(request=request, current_user=user, db=db)

    assert exc_info.value.status_code == 500
    assert "boom" in str(exc_info.value.detail)


# ----------------------------- abort_chat ------------------------------


def test_abort_chat_returns_404_when_session_missing():
    user = _user()
    db = MagicMock()
    with patch.object(agent_api.agent_crud, "get_session", return_value=None):
        with pytest.raises(HTTPException) as exc_info:
            agent_api.abort_chat(session_id=str(uuid4()), current_user=user, db=db)

    assert exc_info.value.status_code == 404


def test_abort_chat_returns_403_when_user_mismatch():
    user = _user()
    other_owner = uuid4()
    db = MagicMock()
    with patch.object(agent_api.agent_crud, "get_session", return_value=_session(owner_id=other_owner)):
        with pytest.raises(HTTPException) as exc_info:
            agent_api.abort_chat(session_id=str(uuid4()), current_user=user, db=db)

    assert exc_info.value.status_code == 403


def test_abort_chat_calls_abort_service_for_owner():
    user = _user()
    db = MagicMock()
    sid = str(uuid4())
    with patch.object(agent_api.agent_crud, "get_session", return_value=_session(owner_id=user.id)):
        with patch.object(agent_api, "abort_chat_session") as abort_svc:
            result = agent_api.abort_chat(session_id=sid, current_user=user, db=db)

    abort_svc.assert_called_once_with(sid)
    assert result["message"]


# ----------------------------- delete_session --------------------------


def test_delete_session_returns_404_when_missing():
    user = _user()
    db = MagicMock()
    with patch.object(agent_api.agent_crud, "get_session", return_value=None):
        with pytest.raises(HTTPException) as exc_info:
            agent_api.delete_session(session_id=str(uuid4()), current_user=user, db=db)

    assert exc_info.value.status_code == 404


def test_delete_session_returns_403_for_other_user():
    user = _user()
    db = MagicMock()
    with patch.object(agent_api.agent_crud, "get_session", return_value=_session(owner_id=uuid4())):
        with pytest.raises(HTTPException) as exc_info:
            agent_api.delete_session(session_id=str(uuid4()), current_user=user, db=db)

    assert exc_info.value.status_code == 403


def test_delete_session_returns_500_when_crud_fails():
    user = _user()
    db = MagicMock()
    sid = str(uuid4())
    with patch.object(agent_api.agent_crud, "get_session", return_value=_session(owner_id=user.id)):
        with patch.object(agent_api.agent_crud, "delete_session", return_value=False):
            with pytest.raises(HTTPException) as exc_info:
                agent_api.delete_session(session_id=sid, current_user=user, db=db)

    assert exc_info.value.status_code == 500


def test_delete_session_succeeds_for_owner():
    user = _user()
    db = MagicMock()
    sid = str(uuid4())
    with patch.object(agent_api.agent_crud, "get_session", return_value=_session(owner_id=user.id)):
        with patch.object(agent_api.agent_crud, "delete_session", return_value=True) as crud_delete:
            result = agent_api.delete_session(session_id=sid, current_user=user, db=db)

    crud_delete.assert_called_once_with(db, sid)
    assert result["message"] == "Session deleted successfully"


# ----------------------------- pin_session -----------------------------


def test_pin_session_returns_404_when_missing():
    user = _user()
    db = MagicMock()
    with patch.object(agent_api.agent_crud, "get_session", return_value=None):
        with pytest.raises(HTTPException) as exc_info:
            agent_api.pin_session(is_pinned=True, session_id=str(uuid4()), current_user=user, db=db)

    assert exc_info.value.status_code == 404


def test_pin_session_returns_403_for_other_user():
    user = _user()
    db = MagicMock()
    with patch.object(agent_api.agent_crud, "get_session", return_value=_session(owner_id=uuid4())):
        with pytest.raises(HTTPException) as exc_info:
            agent_api.pin_session(is_pinned=True, session_id=str(uuid4()), current_user=user, db=db)

    assert exc_info.value.status_code == 403


def test_pin_session_updates_for_owner_and_returns_session():
    user = _user()
    db = MagicMock()
    sid = str(uuid4())
    updated = _session(owner_id=user.id)
    updated.is_pinned = True
    with patch.object(agent_api.agent_crud, "get_session", return_value=_session(owner_id=user.id)):
        with patch.object(agent_api.agent_crud, "update_session", return_value=updated) as update:
            result = agent_api.pin_session(is_pinned=True, session_id=sid, current_user=user, db=db)

    update.assert_called_once()
    assert result.is_pinned is True
