"""Nightly gap coverage for agent session summary and message bookkeeping."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.crud import agent as agent_crud

SESSION_ID = '12345678-1234-5678-1234-567812345678'

pytestmark = pytest.mark.smoke


def _db_with_first(first):
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = first
    return db


def test_context_summary_returns_none_when_session_is_missing():
    assert agent_crud.get_context_summary(_db_with_first(None), SESSION_ID) is None


def test_update_context_summary_does_not_create_missing_session():
    db = _db_with_first(None)

    assert agent_crud.update_context_summary(db, SESSION_ID, "summary") is None
    db.add.assert_not_called()
    db.commit.assert_not_called()


def test_update_context_summary_refreshes_existing_session():
    session = SimpleNamespace(context_summary="old", summary_update_time=None)
    db = _db_with_first(session)

    result = agent_crud.update_context_summary(db, SESSION_ID, "new summary")

    assert result is session
    assert session.context_summary == "new summary"
    assert session.summary_update_time is not None
    db.add.assert_called_once_with(session)
    db.commit.assert_called_once()


def test_create_message_touches_session_summary_time():
    session = SimpleNamespace(summary_update_time=None)
    db = _db_with_first(session)
    payload = MagicMock()
    payload.session_id = SESSION_ID
    payload.model_dump.return_value = {"session_id": SESSION_ID, "role": "user", "content": "hi"}

    created = agent_crud.create_message(db, payload)

    assert created is not None
    assert session.summary_update_time is not None
    db.add.assert_any_call(created)
    db.add.assert_called_with(session)
    db.commit.assert_called_once()
