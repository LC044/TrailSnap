"""Unit tests for the agent token REST router (app/api/agent_token.py).

Three endpoints:
  GET   /tokens        -- list current user tokens (delegates to crud)
  POST  /tokens        -- create a new token (requires password re-auth)
  DELETE /tokens/{id}  -- soft-delete a token; 404 if not owned

The CRUD layer is mocked throughout so we never touch the database.
"""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api import agent_token as tokens_api


pytestmark = [pytest.mark.smoke, pytest.mark.module_agent]


def _user():
    return SimpleNamespace(id=uuid4(), email="owner@example.com")


def _token_row(**overrides):
    base = dict(
        id=uuid4(),
        user_id=uuid4(),
        name="test-token",
        token="ts_abcdef",
        expires_at=datetime(2099, 1, 1, tzinfo=timezone.utc),
        is_deleted=False,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_list_tokens_returns_current_user_tokens():
    user = _user()
    db = object()
    fake_rows = [_token_row(), _token_row(name="second")]

    with patch.object(
        tokens_api.crud_agent_token, "get_tokens_by_user", return_value=fake_rows
    ) as get_tokens:
        result = tokens_api.get_tokens(db=db, current_user=user)

    get_tokens.assert_called_once_with(db, user_id=user.id)
    assert result is fake_rows


def test_create_token_requires_valid_password():
    user = _user()
    db = object()
    payload = SimpleNamespace(
        name="my-token", password="wrong", expires_at=None
    )

    with patch.object(
        tokens_api.crud_user, "authenticate", return_value=None
    ) as authenticate:
        with pytest.raises(HTTPException) as exc_info:
            tokens_api.create_token(token_in=payload, db=db, current_user=user)

    authenticate.assert_called_once_with(db, email=user.email, password="wrong")
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "密码错误"


def test_create_token_persists_when_password_matches():
    user = _user()
    db = object()
    payload = SimpleNamespace(
        name="my-token",
        password="correct",
        expires_at=datetime(2030, 1, 1, tzinfo=timezone.utc),
        scopes=["photos:read", "albums:read"],
    )
    fake_row = _token_row(name="my-token")

    with patch.object(
        tokens_api.crud_user, "authenticate", return_value=user
    ) as authenticate:
        with patch.object(
            tokens_api.crud_agent_token, "create_agent_token", return_value=fake_row
        ) as create_call:
            result = tokens_api.create_token(token_in=payload, db=db, current_user=user)

    authenticate.assert_called_once_with(db, email=user.email, password="correct")
    create_call.assert_called_once_with(
        db=db, user_id=user.id, name="my-token", expires_at=payload.expires_at,
        scopes=["photos:read", "albums:read"],
    )
    assert result is fake_row


@pytest.mark.parametrize("scopes", [[], ["photos:read", "photos:delete"]])
def test_create_token_rejects_empty_or_unknown_scopes(scopes):
    user = _user()
    payload = SimpleNamespace(
        name="limited", password="correct", expires_at=None, scopes=scopes,
    )
    with patch.object(tokens_api.crud_user, "authenticate", return_value=user):
        with pytest.raises(HTTPException) as exc_info:
            tokens_api.create_token(token_in=payload, db=object(), current_user=user)
    assert exc_info.value.status_code == 400


def test_delete_token_returns_404_when_crud_reports_missing():
    user = _user()
    db = object()
    token_id = uuid4()

    with patch.object(
        tokens_api.crud_agent_token, "delete_agent_token", return_value=False
    ) as delete_call:
        with pytest.raises(HTTPException) as exc_info:
            tokens_api.delete_token(token_id=token_id, db=db, current_user=user)

    delete_call.assert_called_once_with(db, token_id=token_id, user_id=user.id)
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Token not found or already deleted"


def test_delete_token_returns_success_message_on_hit():
    user = _user()
    db = object()
    token_id = uuid4()

    with patch.object(
        tokens_api.crud_agent_token, "delete_agent_token", return_value=True
    ) as delete_call:
        result = tokens_api.delete_token(token_id=token_id, db=db, current_user=user)

    delete_call.assert_called_once_with(db, token_id=token_id, user_id=user.id)
    assert result == {"message": "Token deleted successfully"}
