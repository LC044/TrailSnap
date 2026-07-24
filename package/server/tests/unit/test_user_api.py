"""Unit tests for the user-management REST router (app/api/user.py).

The router enforces a strict superuser boundary: only ``is_superuser``
accounts can list / create / delete other accounts. Password self-service
lets the current user reset their own password (or a superuser reset
anyone else). These tests mock the DB session and the password reset
helper so no real user model is needed.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api import user as user_api


pytestmark = [pytest.mark.smoke, pytest.mark.module_user]


def _user(is_superuser: bool = False, user_id=None):
    return SimpleNamespace(
        id=user_id or uuid4(),
        is_superuser=is_superuser,
        email="u@example.com",
        username="u",
        nickname=None,
        avatar=None,
    )


# ----------------------- GET /users/ -----------------------


def test_read_users_returns_only_self_for_non_superuser():
    """Non-superusers must see only themselves in the listing."""
    self_user = _user(is_superuser=False)
    db = MagicMock()

    result = user_api.read_users(db=db, skip=0, limit=100, current_user=self_user)

    assert result == [self_user]
    db.query.assert_not_called()

def test_read_users_calls_query_for_superuser():
    """Superusers hit ``db.query(User).offset().limit().all()``."""
    self_user = _user(is_superuser=True)
    db = MagicMock()
    rows = [self_user, _user()]
    db.query.return_value.offset.return_value.limit.return_value.all.return_value = rows

    result = user_api.read_users(db=db, skip=10, limit=50, current_user=self_user)

    db.query.assert_called_once()
    db.query.return_value.offset.assert_called_once_with(10)
    db.query.return_value.offset.return_value.limit.assert_called_once_with(50)
    assert result == rows


# ----------------------- POST /users/ -----------------------


def test_create_user_403_for_non_superuser():
    """Non-superuser creation attempts must 403 before any DB lookup."""
    self_user = _user(is_superuser=False)
    db = MagicMock()
    payload = SimpleNamespace(email="new@example.com", username="newbie")

    with pytest.raises(HTTPException) as exc_info:
        user_api.create_new_user(user_in=payload, db=db, current_user=self_user)

    assert exc_info.value.status_code == 403
    db.query.assert_not_called()


def test_create_user_rejects_existing_email():
    """Email already taken -> 400, before any insert."""
    self_user = _user(is_superuser=True)
    db = MagicMock()
    existing = SimpleNamespace(email="dup@example.com")
    db.query.return_value.filter.return_value.first.return_value = existing
    payload = SimpleNamespace(email="dup@example.com", username="brand_new")

    with pytest.raises(HTTPException) as exc_info:
        user_api.create_new_user(user_in=payload, db=db, current_user=self_user)

    assert exc_info.value.status_code == 400
    assert "email" in str(exc_info.value.detail).lower()


# ----------------------- PUT /users/{user_id}/password -----------------------


def test_update_user_password_rejects_under_6_chars():
    """Passwords shorter than 6 chars must 400 without hitting reset_password."""
    self_user = _user(is_superuser=True)
    target = _user()
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = target
    payload = {"password": "abc"}

    with patch("app.api.user.reset_password") as reset:
        with pytest.raises(HTTPException) as exc_info:
            user_api.update_user_password(target.id, payload, db=db, current_user=self_user)

    assert exc_info.value.status_code == 400
    assert "6 characters" in str(exc_info.value.detail).lower()
    reset.assert_not_called()


def test_update_user_password_403_for_other_user():
    """A non-superuser must not reset another user's password."""
    self_user = _user(is_superuser=False)
    other_user = _user(user_id=uuid4())
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = other_user
    payload = {"password": "longenough"}

    with pytest.raises(HTTPException) as exc_info:
        user_api.update_user_password(other_user.id, payload, db=db, current_user=self_user)

    assert exc_info.value.status_code == 403


def test_update_user_password_self_allowed():
    """A non-superuser can reset their OWN password (>= 6 chars)."""
    user_id = uuid4()
    self_user = _user(is_superuser=False, user_id=user_id)
    db = MagicMock()
    me = _user(user_id=user_id)
    db.query.return_value.filter.return_value.first.return_value = me
    payload = {"password": "longenough"}

    with patch("app.api.user.reset_password", return_value=me) as reset:
        result = user_api.update_user_password(user_id, payload, db=db, current_user=self_user)

    reset.assert_called_once_with(db, me, "longenough")
    assert result is me


# ----------------------- GET /users/me -----------------------


def test_read_user_me_returns_current_user():
    """``read_user_me`` simply returns the current_user without DB calls."""
    self_user = _user()

    assert user_api.read_user_me(current_user=self_user) is self_user


# ----------------------- PUT /users/me -----------------------


def test_update_user_me_persists_nickname_and_avatar():
    """``update_user_me`` writes nickname/avatar and refreshes the row."""
    self_user = _user()
    db = MagicMock()
    payload = SimpleNamespace(nickname="新昵称", avatar="http://x/a.png")

    result = user_api.update_user_me(payload=payload, db=db, current_user=self_user)

    db.add.assert_called_once_with(self_user)
    db.commit.assert_called_once()
    db.refresh.assert_called_once_with(self_user)
    assert result is self_user
    assert self_user.nickname == "新昵称"
    assert self_user.avatar == "http://x/a.png"


def test_update_user_me_noop_when_no_fields():
    """No payload fields -> add/commit/refresh still run, attrs unchanged."""
    self_user = _user()
    db = MagicMock()
    payload = SimpleNamespace(nickname=None, avatar=None)

    user_api.update_user_me(payload=payload, db=db, current_user=self_user)

    db.add.assert_called_once()
    db.commit.assert_called_once()
    assert self_user.nickname is None
    assert self_user.avatar is None

