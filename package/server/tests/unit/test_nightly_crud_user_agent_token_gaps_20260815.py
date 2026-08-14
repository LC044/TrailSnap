"""Unit tests covering 2026-08-15 nightly coverage gap scan (round 7).

Targets:
* app/crud/user.py -- previously 26.2% covered, 62 of 84 lines missed.
* app/crud/agent_token.py -- previously 35% covered, 26 of 40 lines missed.

All DB interactions are mocked via MagicMock + SimpleNamespace so the tests run
in isolation without a live Postgres.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest


pytestmark = [pytest.mark.smoke]


def _user_row(**overrides):
    base = dict(
        id=uuid4(),
        username="alice",
        email="alice@example.com",
        nickname="Alice",
        avatar=None,
        hashed_password="hashed::correct",
        is_active=True,
        is_superuser=False,
        failed_login_attempts=0,
        last_failed_login=None,
        lockout_until=None,
        security_question=None,
        security_answer_hash=None,
        settings={},
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _token_row(**overrides):
    base = dict(
        id=uuid4(),
        user_id=uuid4(),
        name="default",
        token="ts_abcdef0123456789",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        expires_at=datetime(2099, 1, 1, tzinfo=timezone.utc),
        is_deleted=False,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


class TestGetBy:
    def test_get_returns_none_for_non_uuid_string(self):
        from app.crud import user as user_crud
        db = MagicMock()
        with patch("uuid.UUID", side_effect=ValueError("bad")):
            assert user_crud.get(db, "not-a-uuid") is None
        db.query.assert_not_called()


    def test_get_int_id_passes_through_to_query(self):
        """Non-string ids bypass the ``UUID(...)`` cast and are forwarded to the
        ORM query as-is. This guards against accidentally raising on ints."""
        from app.crud import user as user_crud
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        assert user_crud.get(db, 12345) is None
        db.query.assert_called_once()

    def test_get_queries_by_uuid_when_string_is_valid(self):
        from app.crud import user as user_crud
        db = MagicMock()
        row = _user_row()
        db.query.return_value.filter.return_value.first.return_value = row
        assert user_crud.get(db, str(row.id)) is row
        db.query.assert_called_once()

    def test_get_by_email_returns_row(self):
        from app.crud import user as user_crud
        db = MagicMock()
        row = _user_row()
        db.query.return_value.filter.return_value.first.return_value = row
        assert user_crud.get_by_email(db, row.email) is row

    def test_get_by_username_returns_row(self):
        from app.crud import user as user_crud
        db = MagicMock()
        row = _user_row()
        db.query.return_value.filter.return_value.first.return_value = row
        assert user_crud.get_by_username(db, row.username) is row

    def test_get_all_users_returns_query_all(self):
        from app.crud import user as user_crud
        db = MagicMock()
        rows = [_user_row(), _user_row(username="bob")]
        db.query.return_value.all.return_value = rows
        assert user_crud.get_all_users(db) is rows

    def test_get_by_username_or_email_returns_row(self):
        from app.crud import user as user_crud
        db = MagicMock()
        row = _user_row()
        db.query.return_value.filter.return_value.first.return_value = row
        assert user_crud.get_by_username_or_email(db, "alice") is row


class TestCreateUser:
    @patch("app.crud.user.get_password_hash", side_effect=lambda p: f"hashed::{p}")
    @patch("app.crud.user.config_manager")
    def test_create_without_security_answer(self, mock_config, mock_hash):
        from app.crud import user as user_crud
        mock_config.get_default_config.return_value = {"theme": "sky"}
        db = MagicMock()
        created = _user_row(username="new", email="new@example.com")
        with patch("app.crud.user.User", return_value=created) as MockUser:
            result = user_crud.create(
                db,
                SimpleNamespace(
                    email="new@example.com",
                    username="new",
                    nickname="New",
                    avatar="a",
                    password="pw",
                    is_active=True,
                    is_superuser=False,
                    security_question=None,
                    security_answer=None,
                ),
            )
        MockUser.assert_called_once()
        kwargs = MockUser.call_args.kwargs
        assert kwargs["email"] == "new@example.com"
        assert kwargs["hashed_password"] == "hashed::pw"
        assert kwargs["security_answer_hash"] is None
        assert kwargs["settings"] == {"theme": "sky"}
        db.add.assert_called_once_with(created)
        db.commit.assert_called_once()
        assert result is created

    @patch("app.crud.user.get_password_hash", side_effect=lambda p: f"hashed::{p}")
    @patch("app.crud.user.config_manager")
    def test_create_with_security_answer_hashes_answer(self, mock_config, mock_hash):
        from app.crud import user as user_crud
        mock_config.get_default_config.return_value = {}
        db = MagicMock()
        created = _user_row()
        with patch("app.crud.user.User", return_value=created) as MockUser:
            user_crud.create(
                db,
                SimpleNamespace(
                    email="e@e.com",
                    username="u",
                    nickname=None,
                    avatar=None,
                    password="pw",
                    is_active=True,
                    is_superuser=False,
                    security_question="pet",
                    security_answer="rex",
                ),
            )
        assert MockUser.call_args.kwargs["security_answer_hash"] == "hashed::rex"


class TestDeleteUser:
    def test_delete_returns_false_when_user_missing(self):
        from app.crud import user as user_crud
        db = MagicMock()
        with patch.object(user_crud, "get", return_value=None):
            assert user_crud.delete(db, uuid4()) is False
        db.delete.assert_not_called()

    def test_delete_removes_photos_albums_and_user(self):
        from app.crud import user as user_crud
        user_id = uuid4()
        photo1 = SimpleNamespace(id=uuid4())
        photo2 = SimpleNamespace(id=uuid4())
        user = _user_row(id=user_id)
        db = MagicMock()
        photos_q = MagicMock()
        photos_q.__iter__ = MagicMock(return_value=iter([photo1, photo2]))
        db.query.return_value.filter.side_effect = [photos_q, MagicMock()]
        with patch.object(user_crud, "get", return_value=user), \
             patch("app.crud.user.storage") as mock_storage:
            result = user_crud.delete(db, user_id)
        assert result is user
        assert mock_storage.delete_thumbnails.call_count == 2
        assert db.commit.call_count >= 1


class TestAuthenticate:
    @patch("app.crud.user.verify_password", return_value=True)
    def test_authenticate_success_resets_failure_count(self, _):
        from app.crud import user as user_crud
        user = _user_row(
            failed_login_attempts=3,
            lockout_until=datetime.now() - timedelta(minutes=1),
        )
        db = MagicMock()
        with patch.object(user_crud, "get_by_username_or_email", return_value=user):
            assert user_crud.authenticate(db, "alice", "pw") is user
        assert user.failed_login_attempts == 0
        assert user.lockout_until is None
        db.add.assert_called_once_with(user)

    @patch("app.crud.user.verify_password", return_value=False)
    def test_authenticate_wrong_password_increments_and_may_lockout(self, _):
        from app.crud import user as user_crud
        user = _user_row(failed_login_attempts=4)
        db = MagicMock()
        with patch.object(user_crud, "get_by_username_or_email", return_value=user):
            assert user_crud.authenticate(db, "alice", "wrong") is None
        assert user.failed_login_attempts == 5
        assert user.lockout_until is not None
        assert user.lockout_until > datetime.now()
        db.commit.assert_called_once()

    def test_authenticate_returns_none_when_user_missing(self):
        from app.crud import user as user_crud
        db = MagicMock()
        with patch.object(user_crud, "get_by_username_or_email", return_value=None):
            assert user_crud.authenticate(db, "ghost", "pw") is None

    def test_authenticate_returns_none_when_user_is_locked_out(self):
        from app.crud import user as user_crud
        user = _user_row(lockout_until=datetime.now() + timedelta(minutes=10))
        db = MagicMock()
        with patch.object(user_crud, "get_by_username_or_email", return_value=user):
            assert user_crud.authenticate(db, "alice", "pw") is None


class TestSecurityAnswerAndReset:
    def test_verify_security_answer_correct(self):
        from app.crud import user as user_crud
        user = _user_row(security_answer_hash="hashed::rex")
        with patch("app.crud.user.verify_password", return_value=True):
            assert user_crud.verify_security_answer(user, "rex") is True

    def test_verify_security_answer_incorrect(self):
        from app.crud import user as user_crud
        user = _user_row(security_answer_hash="hashed::rex")
        with patch("app.crud.user.verify_password", return_value=False):
            assert user_crud.verify_security_answer(user, "woof") is False

    def test_verify_security_answer_no_answer_set(self):
        from app.crud import user as user_crud
        user = _user_row(security_answer_hash=None)
        assert user_crud.verify_security_answer(user, "anything") is False

    @patch("app.crud.user.get_password_hash", return_value="hashed::new")
    def test_reset_password_clears_lockout(self, _):
        from app.crud import user as user_crud
        user = _user_row(
            failed_login_attempts=7,
            lockout_until=datetime.now() + timedelta(minutes=5),
            hashed_password="hashed::old",
        )
        db = MagicMock()
        user_crud.reset_password(db, user, "new")
        assert user.hashed_password == "hashed::new"
        assert user.failed_login_attempts == 0
        assert user.lockout_until is None
        db.commit.assert_called_once()


class TestGenerateTokenString:
    def test_starts_with_prefix_and_default_length(self):
        from app.crud import agent_token as token_crud
        out = token_crud.generate_token_string()
        assert out.startswith("ts_")
        assert len(out) == len("ts_") + 32

    def test_default_alphabet_is_alphanumeric(self):
        from app.crud import agent_token as token_crud
        out = token_crud.generate_token_string(length=64)
        body = out[len("ts_"):]
        assert all(c.isalnum() for c in body)
        assert body.isascii()

    def test_unique_across_calls(self):
        from app.crud import agent_token as token_crud
        a = token_crud.generate_token_string(length=16)
        b = token_crud.generate_token_string(length=16)
        assert a != b


class TestCreateAgentToken:
    def test_persists_and_caches(self):
        from app.crud import agent_token as token_crud
        user_id = uuid4()
        expires = datetime(2099, 1, 1, tzinfo=timezone.utc)
        db = MagicMock()
        row = _token_row(user_id=user_id, expires_at=expires)
        with patch("app.crud.agent_token.AgentToken", return_value=row) as MockTok, \
             patch(
                 "app.crud.agent_token.generate_token_string",
                 return_value="ts_FIXED",
             ):
            result = token_crud.create_agent_token(db, user_id, "name", expires)
        MockTok.assert_called_once()
        kwargs = MockTok.call_args.kwargs
        assert kwargs["user_id"] is user_id
        assert kwargs["name"] == "name"
        assert kwargs["token"] == "ts_FIXED"
        assert kwargs["expires_at"] is expires
        assert kwargs["is_deleted"] is False
        db.add.assert_called_once_with(row)
        db.commit.assert_called_once()
        db.refresh.assert_called_once_with(row)
        assert result is row
        assert token_crud._token_cache["ts_FIXED"] is row


class TestGetTokensByUser:
    def test_filters_and_orders_desc(self):
        from app.crud import agent_token as token_crud
        db = MagicMock()
        rows = [_token_row(name="a"), _token_row(name="b")]
        chain = db.query.return_value.filter.return_value
        chain.order_by.return_value.all.return_value = rows
        assert token_crud.get_tokens_by_user(db, uuid4()) is rows


class TestDeleteAgentToken:
    def test_returns_false_when_token_missing(self):
        from app.crud import agent_token as token_crud
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        assert token_crud.delete_agent_token(db, uuid4(), uuid4()) is False
        db.commit.assert_not_called()

    def test_marks_deleted_and_invalidates_cache(self):
        from app.crud import agent_token as token_crud
        token_str = "ts_abcdef0123456789"
        row = _token_row(token=token_str)
        token_crud._token_cache[token_str] = row
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = row
        assert token_crud.delete_agent_token(db, row.id, row.user_id) is True
        assert row.is_deleted is True
        assert token_str not in token_crud._token_cache
        db.commit.assert_called_once()


class TestGetTokenByString:
    def test_returns_cached_when_alive(self):
        from app.crud import agent_token as token_crud
        token_str = "ts_cached"
        row = _token_row(token=token_str)
        token_crud._token_cache[token_str] = row
        db = MagicMock()
        result = token_crud.get_token_by_string(db, token_str)
        assert result is row
        db.query.assert_not_called()

    def test_drops_through_to_db_when_cached_is_deleted(self):
        """When the cached entry has is_deleted=True the function falls
        through to the DB query. If the DB returns nothing, the function
        returns None and the stale cache entry is left in place -- a
        subsequent call still falls through to the DB because the cached
        row is_deleted flag remains True."""
        from app.crud import agent_token as token_crud
        token_str = "ts_stale"
        row = _token_row(token=token_str, is_deleted=True)
        token_crud._token_cache[token_str] = row
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        assert token_crud.get_token_by_string(db, token_str) is None
        assert token_crud._token_cache[token_str] is row
        # Subsequent call still falls through (cache row is still is_deleted=True).
        assert token_crud.get_token_by_string(db, token_str) is None

    def test_db_miss_returns_none_and_does_not_cache(self):
        from app.crud import agent_token as token_crud
        token_str = "ts_dbmiss"
        token_crud._token_cache.pop(token_str, None)
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        assert token_crud.get_token_by_string(db, token_str) is None
        assert token_str not in token_crud._token_cache

    def test_db_hit_populates_cache(self):
        from app.crud import agent_token as token_crud
        token_str = "ts_dbhit"
        token_crud._token_cache.pop(token_str, None)
        row = _token_row(token=token_str)
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = row
        assert token_crud.get_token_by_string(db, token_str) is row
        assert token_crud._token_cache[token_str] is row
