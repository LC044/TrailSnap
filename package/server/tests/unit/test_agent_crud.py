"""Unit tests for ``app/crud/agent.py``.

Covers the session + message CRUD wrappers. ``db`` is mocked so we never
touch Postgres. The module's UUID coercion (str → UUID) is also covered.

Scenarios:
* get_session accepts a UUID string and queries by it
* get_sessions_by_user coerces a string user_id and orders by pinned/created
* create_session persists and refreshes
* update_session applies only the explicitly provided fields
* delete_session returns False when missing, True when removed
* get_messages_by_session coerces session id and orders by created_at
* create_message also bumps summary_update_time on the parent session
* delete_messages_by_session returns True even when nothing matched
"""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest

from app.crud import agent as agent_crud
from app.schemas.agent import (
    AgentMessageCreate,
    AgentSessionCreate,
    AgentSessionUpdate,
)


pytestmark = [pytest.mark.smoke, pytest.mark.module_agent]


# ---------------------------------------------------------------------------
# Session CRUD
# ---------------------------------------------------------------------------

def test_get_session_accepts_uuid_string_and_queries_by_uuid():
    db = MagicMock()
    expected = SimpleNamespace(id=uuid4(), user_id=uuid4())
    db.query.return_value.filter.return_value.first.return_value = expected

    out = agent_crud.get_session(db, str(expected.id))

    db.query.assert_called_once()
    # The filter clause was built with the UUID instance, not a raw string.
    args, _ = db.query.return_value.filter.call_args
    assert args[0].right.value == expected.id
    assert isinstance(args[0].right.value, UUID)
    assert out is expected


def test_get_sessions_by_user_orders_by_pinned_then_created():
    db = MagicMock()
    user_id = uuid4()
    expected = [SimpleNamespace(id=uuid4()), SimpleNamespace(id=uuid4())]
    # 会话列表会额外过滤掉隐藏的"记忆专用会话"，因此链上有两层 filter：
    # query().filter(owner).filter(title != __memory__).order_by()...
    db.query.return_value.filter.return_value.filter.return_value.order_by.return_value \
        .offset.return_value.limit.return_value.all.return_value = expected

    out = agent_crud.get_sessions_by_user(db, str(user_id), skip=10, limit=25)

    assert out is expected
    db.query.return_value.filter.return_value.filter.return_value.order_by.return_value \
        .offset.assert_called_once_with(10)
    db.query.return_value.filter.return_value.filter.return_value.order_by.return_value \
        .offset.return_value.limit.assert_called_once_with(25)


def test_create_session_persists_payload_and_user_id():
    db = MagicMock()
    user_id = uuid4()
    payload = AgentSessionCreate(title="trip chat", is_pinned=True)

    out = agent_crud.create_session(db, payload, user_id)

    db.add.assert_called_once()
    db.commit.assert_called_once()
    db.refresh.assert_called_once()
    # The added object carries coerced UUID + payload fields.
    added = db.add.call_args[0][0]
    assert added.user_id == user_id
    assert isinstance(added.user_id, UUID)
    assert added.title == "trip chat"
    assert added.is_pinned is True
    # create_session returns the same instance it refreshed.
    assert out is added


def test_update_session_only_applies_supplied_fields():
    db = MagicMock()
    db_obj = SimpleNamespace(title="old", status="active", is_pinned=False)
    # Only `title` is explicitly supplied; the other two stay untouched.
    payload = AgentSessionUpdate(title="new")

    out = agent_crud.update_session(db, db_obj, payload)

    assert db_obj.title == "new"
    # status & is_pinned were not set in the payload → not in exclude_unset dump
    assert db_obj.status == "active"
    assert db_obj.is_pinned is False
    db.add.assert_called_once_with(db_obj)
    db.commit.assert_called_once()
    assert out is db_obj


def test_delete_session_returns_false_when_not_found():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None

    assert agent_crud.delete_session(db, str(uuid4())) is False
    db.delete.assert_not_called()
    db.commit.assert_not_called()


def test_delete_session_returns_true_when_removed():
    db = MagicMock()
    target = SimpleNamespace(id=uuid4())
    db.query.return_value.filter.return_value.first.return_value = target

    assert agent_crud.delete_session(db, str(target.id)) is True
    db.delete.assert_called_once_with(target)
    db.commit.assert_called_once()


# ---------------------------------------------------------------------------
# Message CRUD
# ---------------------------------------------------------------------------

def test_get_messages_by_session_orders_by_created_at_ascending():
    db = MagicMock()
    session_id = uuid4()
    expected = [SimpleNamespace(id=1), SimpleNamespace(id=2)]
    db.query.return_value.filter.return_value.order_by.return_value \
        .offset.return_value.limit.return_value.all.return_value = expected

    out = agent_crud.get_messages_by_session(db, str(session_id), skip=0, limit=50)

    assert out is expected
    db.query.return_value.filter.return_value.order_by.return_value \
        .offset.assert_called_once_with(0)
    db.query.return_value.filter.return_value.order_by.return_value \
        .offset.return_value.limit.assert_called_once_with(50)


def test_create_message_bumps_parent_session_summary_time():
    db = MagicMock()
    parent = SimpleNamespace(summary_update_time=None)
    db.query.return_value.filter.return_value.first.return_value = parent
    payload = AgentMessageCreate(
        session_id=uuid4(), role="user", content="hi", token_count=3
    )

    agent_crud.create_message(db, payload)

    assert isinstance(parent.summary_update_time, datetime)
    db.add.assert_called()  # both message and session were added
    db.commit.assert_called_once()
    db.refresh.assert_called_once()


def test_create_message_succeeds_even_without_matching_session():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    payload = AgentMessageCreate(session_id=uuid4(), role="assistant", content="ok")

    agent_crud.create_message(db, payload)

    db.commit.assert_called_once()
    # Only the message itself was added; no session row to touch.
    assert db.add.call_count == 1


def test_delete_messages_by_session_returns_true_regardless_of_matches():
    db = MagicMock()
    db.query.return_value.filter.return_value.delete.return_value = 0

    assert agent_crud.delete_messages_by_session(db, str(uuid4())) is True
    db.query.return_value.filter.return_value.delete.assert_called_once()
    db.commit.assert_called_once()