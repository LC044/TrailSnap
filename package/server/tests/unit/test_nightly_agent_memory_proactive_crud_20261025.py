"""Nightly coverage for the hidden memory / proactive agent sessions (2026-10-25).

The 2026-10-25 backend coverage scan listed ``app/crud/agent.py`` at 77.0% with
32 missed lines.  The missed lines all belong to the two *hidden* session
helpers, which the agent service uses to persist

* the long-term memory anchor  (``__memory__`` session + one ``memory`` message)
* the proactive "this day" push (``__proactive__`` session + ``proactive`` messages)

None of the branches was exercised: session creation vs. reuse, the
create-vs-overwrite decision of the memory anchor, and the idempotency check
behind ``has_proactive_for_date``.

These tests run against a real SQLite session so the assertions describe the
persisted rows (and the visibility rules that hide the internal sessions from
the normal session list).
"""

import uuid

import pytest

pytestmark = [pytest.mark.smoke]


@pytest.fixture()
def db(face_sqlite_session):
    return face_sqlite_session


# ---------------------------------------------------------------------------
# memory session
# ---------------------------------------------------------------------------


def test_memory_session_is_created_once(db):
    """The first call creates the hidden session, the second one reuses it."""
    from app.crud.agent import MEMORY_SESSION_TITLE, get_or_create_memory_session

    user_id = uuid.uuid4()
    first = get_or_create_memory_session(db, user_id)
    second = get_or_create_memory_session(db, user_id)

    assert first.title == MEMORY_SESSION_TITLE
    assert first.status == "active"
    assert second.id == first.id


def test_memory_session_accepts_a_string_user_id(db):
    """``user_id`` may arrive as a string and is coerced to a UUID."""
    from app.crud.agent import get_or_create_memory_session

    user_id = uuid.uuid4()
    session = get_or_create_memory_session(db, str(user_id))
    assert session.user_id == user_id


def test_memory_sessions_are_isolated_per_user(db):
    from app.crud.agent import get_or_create_memory_session

    first = get_or_create_memory_session(db, uuid.uuid4())
    second = get_or_create_memory_session(db, uuid.uuid4())
    assert first.id != second.id


def test_memory_message_is_absent_before_the_first_upsert(db):
    from app.crud.agent import get_memory_message

    assert get_memory_message(db, uuid.uuid4()) is None


def test_upsert_memory_message_creates_the_anchor(db):
    """The anchor is stored in ``content_ext`` because ``content`` is non-null."""
    from app.crud.agent import MEMORY_CONTENT_TYPE, get_memory_message, upsert_memory_message

    user_id = uuid.uuid4()
    message = upsert_memory_message(db, user_id, {"anchor": "2024-05-01"})

    assert message.content_type == MEMORY_CONTENT_TYPE
    assert message.role == "system"
    assert message.content == ""
    assert message.content_ext == {"anchor": "2024-05-01"}

    stored = get_memory_message(db, user_id)
    assert stored is not None
    assert stored.id == message.id


def test_upsert_memory_message_overwrites_instead_of_duplicating(db):
    """A second upsert replaces the anchor in place."""
    from app.crud.agent import get_memory_message, upsert_memory_message

    user_id = uuid.uuid4()
    first = upsert_memory_message(db, user_id, {"anchor": "2024-05-01"})
    second = upsert_memory_message(db, user_id, {"anchor": "2024-06-01"})

    assert second.id == first.id
    assert second.content_ext == {"anchor": "2024-06-01"}

    stored = get_memory_message(db, user_id)
    assert stored.content_ext == {"anchor": "2024-06-01"}


# ---------------------------------------------------------------------------
# proactive session
# ---------------------------------------------------------------------------


def test_proactive_session_is_created_once(db):
    from app.crud.agent import PROACTIVE_SESSION_TITLE, get_or_create_proactive_session

    user_id = uuid.uuid4()
    first = get_or_create_proactive_session(db, user_id)
    second = get_or_create_proactive_session(db, user_id)

    assert first.title == PROACTIVE_SESSION_TITLE
    assert second.id == first.id


def test_proactive_session_accepts_a_string_user_id(db):
    from app.crud.agent import get_or_create_proactive_session

    user_id = uuid.uuid4()
    session = get_or_create_proactive_session(db, str(user_id))
    assert session.user_id == user_id


def test_has_proactive_for_date_is_idempotent(db):
    """The same anchor date must not be generated twice."""
    from app.crud.agent import create_proactive_message, has_proactive_for_date

    user_id = uuid.uuid4()
    assert has_proactive_for_date(db, user_id, "2024-05-01") is False

    create_proactive_message(db, user_id, "去年今日你在海边", "2024-05-01")

    assert has_proactive_for_date(db, user_id, "2024-05-01") is True
    assert has_proactive_for_date(db, user_id, "2024-05-02") is False


def test_create_proactive_message_stores_the_anchor(db):
    from app.crud.agent import PROACTIVE_CONTENT_TYPE, create_proactive_message

    message = create_proactive_message(
        db, uuid.uuid4(), "去年今日你在海边", "2024-05-01", recommendations=[{"id": "a"}]
    )
    assert message.content_type == PROACTIVE_CONTENT_TYPE
    assert message.role == "assistant"
    assert message.content == "去年今日你在海边"
    assert message.content_ext["anchor_date"] == "2024-05-01"
    assert message.content_ext["read"] is False
    assert message.content_ext["recommendations"] == [{"id": "a"}]


def test_unread_proactive_messages_only_returns_unread(db):
    from app.crud.agent import create_proactive_message, get_unread_proactive_messages

    user_id = uuid.uuid4()
    create_proactive_message(db, user_id, "第一条", "2024-05-01")
    create_proactive_message(db, user_id, "第二条", "2024-05-02")

    assert len(get_unread_proactive_messages(db, user_id)) == 2


def test_mark_proactive_read_hides_the_message(db):
    from app.crud.agent import (
        create_proactive_message,
        get_unread_proactive_messages,
        mark_proactive_read,
    )

    user_id = uuid.uuid4()
    message = create_proactive_message(db, user_id, "去年今日你在海边", "2024-05-01")

    assert mark_proactive_read(db, user_id, message.id) is True
    assert get_unread_proactive_messages(db, user_id) == []


def test_mark_proactive_read_rejects_an_unknown_message(db):
    from app.crud.agent import mark_proactive_read

    assert mark_proactive_read(db, uuid.uuid4(), 999999) is False


# ---------------------------------------------------------------------------
# the internal sessions stay hidden from the normal session list
# ---------------------------------------------------------------------------


def test_internal_sessions_are_hidden_from_the_session_list(db):
    """``__memory__`` / ``__proactive__`` must not show up as normal chats."""
    from app.crud.agent import (
        MEMORY_SESSION_TITLE,
        PROACTIVE_SESSION_TITLE,
        get_or_create_memory_session,
        get_or_create_proactive_session,
        get_sessions_by_user,
    )
    from app.db.models.agent import AgentSession

    user_id = uuid.uuid4()
    get_or_create_memory_session(db, user_id)
    get_or_create_proactive_session(db, user_id)
    db.add(AgentSession(user_id=user_id, title="普通会话", status="active"))
    db.commit()

    titles = [session.title for session in get_sessions_by_user(db, user_id)]
    assert titles == ["普通会话"]
    assert MEMORY_SESSION_TITLE not in titles
    assert PROACTIVE_SESSION_TITLE not in titles
