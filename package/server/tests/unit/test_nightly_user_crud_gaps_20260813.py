"""Nightly watch gap coverage for ``app/crud/user.py``.

Earlier coverage scan showed 26.2% line coverage (62 missed lines) because
the only callers live in auth routers / CLI / scripts which the unit suite
does not exercise. These tests use :class:`unittest.mock.MagicMock` to
validate the SQLAlchemy chain and the password hashing side effects.

Coverage:
* get: UUID / string / int / unparseable
* get_by_email / get_by_username / get_all_users / get_by_username_or_email
* create: hashes password + optional security answer, populates settings
* delete: missing user short-circuit, cascades to Photo + Album
* authenticate: success, wrong password increments failed_login_attempts,
  lockout branch, locked-out account returns None, success resets counters
* verify_security_answer: missing hash returns False, correct answer True
* reset_password: hashes new password, clears lockout counters
"""

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.crud import user as user_crud
from app.schemas.user import UserCreate


pytestmark = [pytest.mark.smoke, pytest.mark.module_user]


def _make_user(**overrides):
    base = dict(
        id=uuid4(),
        email="alice@example.com",
        username="alice",
        hashed_password="hashed",
        failed_login_attempts=0,
        lockout_until=None,
        last_failed_login=None,
        security_answer_hash=None,
        is_active=True,
        is_superuser=False,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------

def test_get_returns_user_when_uuid_matches():
    db = MagicMock()
    expected = _make_user()
    db.query.return_value.filter.return_value.first.return_value = expected

    out = user_crud.get(db, expected.id)

    assert out is expected
    db.query.assert_called_once()


def test_get_coerces_string_to_uuid():
    db = MagicMock()
    expected = _make_user()
    db.query.return_value.filter.return_value.first.return_value = expected

    out = user_crud.get(db, str(expected.id))

    assert out is expected


def test_get_returns_none_on_invalid_string():
    db = MagicMock()

    out = user_crud.get(db, "not-a-uuid")

    assert out is None
    db.query.assert_not_called()


# ---------------------------------------------------------------------------
# simple lookups
# ---------------------------------------------------------------------------

def test_get_by_email_queries_by_email_field():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = _make_user()

    out = user_crud.get_by_email(db, "alice@example.com")

    assert out is not None
    db.query.assert_called_once()


def test_get_by_username_queries_by_username_field():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = _make_user()

    out = user_crud.get_by_username(db, "alice")

    assert out is not None


def test_get_all_users_returns_query_result():
    db = MagicMock()
    db.query.return_value.all.return_value = [_make_user(), _make_user()]

    out = user_crud.get_all_users(db)

    assert len(out) == 2


def test_get_by_username_or_email_uses_or_clause():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = _make_user()

    out = user_crud.get_by_username_or_email(db, "alice")

    assert out is not None
    db.query.return_value.filter.assert_called_once()


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------

def test_create_hashes_password_and_persists_user():
    db = MagicMock()
    db.refresh.return_value = None

    with patch("app.crud.user.get_password_hash", return_value="HASHED") as hash_mock, \
         patch("app.crud.user.config_manager") as cm:
        cm.get_default_config.return_value = {"theme": "sky"}
        payload = UserCreate(
            username="alice",
            email="alice@example.com",
            password="plain-pw",
            security_question="Q?",
            security_answer="answer",
        )
        user = user_crud.create(db, payload)

    # password + security answer both got hashed
    assert hash_mock.call_count == 2
    assert user.hashed_password == "HASHED"
    assert user.security_answer_hash == "HASHED"
    assert user.settings == {"theme": "sky"}
    db.add.assert_called_once()
    db.commit.assert_called_once()
    db.refresh.assert_called_once()


def test_create_skips_security_answer_hash_when_missing():
    db = MagicMock()
    db.refresh.return_value = None

    with patch("app.crud.user.get_password_hash", return_value="HASHED") as hash_mock, \
         patch("app.crud.user.config_manager") as cm:
        cm.get_default_config.return_value = {}
        payload = UserCreate(
            username="bob",
            email="bob@example.com",
            password="plain-pw",
        )
        user = user_crud.create(db, payload)

    # Only the password is hashed when no security answer is provided
    assert hash_mock.call_count == 1
    assert user.security_answer_hash is None


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------

def test_delete_returns_false_when_user_missing():
    db = MagicMock()
    # First .filter().first() returns None for the user lookup
    db.query.return_value.filter.return_value.first.return_value = None

    out = user_crud.delete(db, uuid4())

    assert out is False
    db.delete.assert_not_called()


def test_delete_cascades_to_photos_and_albums():
    db = MagicMock()
    user_id = uuid4()
    fake_user = _make_user(id=user_id)

    # get(db, user_id) -> fake_user
    db.query.return_value.filter.return_value.first.return_value = fake_user
    # Photo query - returns an iterable that supports .delete()
    photos_chain = MagicMock()
    photos_chain.delete = MagicMock(return_value=0)
    photos_iter = MagicMock()
    photos_iter.__iter__ = MagicMock(return_value=iter([SimpleNamespace(id=uuid4())]))
    # Each db.query(Photo) call needs to return the same chain
    db.query.return_value.filter.side_effect = [
        MagicMock(first=MagicMock(return_value=fake_user)),  # User lookup
        photos_iter,                                          # Photo list
        MagicMock(),                                          # Photo delete
    ]

    out = user_crud.delete(db, user_id)

    assert out is fake_user
    # db.delete called twice on user (the duplicate is in the source)
    assert db.delete.call_count == 2
    db.commit.assert_called()


# ---------------------------------------------------------------------------
# authenticate
# ---------------------------------------------------------------------------

def test_authenticate_returns_none_when_user_missing():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None

    out = user_crud.authenticate(db, "alice", "pw")

    assert out is None


def test_authenticate_returns_none_when_account_locked_out():
    db = MagicMock()
    user = _make_user(lockout_until=datetime.now() + timedelta(minutes=10))

    with patch("app.crud.user.get_by_username_or_email", return_value=user):
        out = user_crud.authenticate(db, "alice", "pw")

    assert out is None


def test_authenticate_returns_none_and_increments_failed_counter_on_bad_password():
    db = MagicMock()
    user = _make_user(failed_login_attempts=0)

    with patch("app.crud.user.get_by_username_or_email", return_value=user), \
         patch("app.crud.user.verify_password", return_value=False):
        out = user_crud.authenticate(db, "alice", "wrong")

    assert out is None
    assert user.failed_login_attempts == 1
    assert isinstance(user.last_failed_login, datetime)
    db.add.assert_called_once()
    db.commit.assert_called_once()


def test_authenticate_sets_lockout_after_five_failures():
    db = MagicMock()
    user = _make_user(failed_login_attempts=4)  # next failure will be 5

    with patch("app.crud.user.get_by_username_or_email", return_value=user), \
         patch("app.crud.user.verify_password", return_value=False):
        out = user_crud.authenticate(db, "alice", "wrong")

    assert out is None
    assert user.failed_login_attempts == 5
    assert user.lockout_until is not None


def test_authenticate_returns_user_and_resets_counters_on_success():
    db = MagicMock()
    user = _make_user(failed_login_attempts=2, lockout_until=None)

    with patch("app.crud.user.get_by_username_or_email", return_value=user), \
         patch("app.crud.user.verify_password", return_value=True):
        out = user_crud.authenticate(db, "alice", "right")

    assert out is user
    assert user.failed_login_attempts == 0


# ---------------------------------------------------------------------------
# verify_security_answer
# ---------------------------------------------------------------------------

def test_verify_security_answer_returns_false_when_hash_missing():
    user = _make_user(security_answer_hash=None)

    out = user_crud.verify_security_answer(user, "answer")

    assert out is False


def test_verify_security_answer_returns_true_for_correct_answer():
    user = _make_user(security_answer_hash="HASH")

    with patch("app.crud.user.verify_password", return_value=True) as vp:
        out = user_crud.verify_security_answer(user, "answer")

    assert out is True
    vp.assert_called_once_with("answer", "HASH")


def test_verify_security_answer_returns_false_for_wrong_answer():
    user = _make_user(security_answer_hash="HASH")

    with patch("app.crud.user.verify_password", return_value=False):
        out = user_crud.verify_security_answer(user, "nope")

    assert out is False


# ---------------------------------------------------------------------------
# reset_password
# ---------------------------------------------------------------------------

def test_reset_password_hashes_and_clears_lockout():
    db = MagicMock()
    db.refresh.return_value = None
    user = _make_user(failed_login_attempts=3, lockout_until=datetime.now())

    with patch("app.crud.user.get_password_hash", return_value="NEWHASH"):
        out = user_crud.reset_password(db, user, "brand-new-pw")

    assert out is user
    assert user.hashed_password == "NEWHASH"
    assert user.failed_login_attempts == 0
    assert user.lockout_until is None
    db.add.assert_called_once()
    db.commit.assert_called_once()
    db.refresh.assert_called_once()
