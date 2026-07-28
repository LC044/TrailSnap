"""Unit tests for app/api/deps.py (FastAPI auth dependency injection).

Covers `get_current_user` and `resolve_user_from_token` across:
  * Valid JWT token
  * Expired JWT token (401)
  * Invalid JWT token (403)
  * Valid `ts_` agent token
  * Expired `ts_` agent token (401)
  * Unknown `ts_` agent token (401)
  * JWT referencing a missing user (401)
  * Empty / missing query-param token (401)

All persistence boundaries (`crud.user.get`, `crud.agent_token.get_token_by_string`)
are mocked; the real `system_config.security` settings are reused so the
HS256 secret/algorithm line up with `jose.jwt`.
"""

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from jose import jwt

from app.api import deps
from app.core.system_config import system_config


pytestmark = [pytest.mark.smoke]


def _make_jwt(user_id, *, expired: bool = False) -> str:
    secret = system_config.config.security.secret_key
    algo = system_config.config.security.algorithm
    exp = datetime.utcnow() + (timedelta(minutes=-5) if expired else timedelta(minutes=10))
    return jwt.encode({"sub": str(user_id), "exp": exp}, secret, algorithm=algo)


def _user_row(user_id):
    return SimpleNamespace(id=user_id, email="u@example.com")


def test_get_current_user_returns_user_for_valid_jwt():
    db = object()
    user_id = uuid4()
    token = _make_jwt(user_id)
    user = _user_row(user_id)

    with patch.object(deps, "get_db", return_value=db):
        with patch.object(deps.crud_user, "get", return_value=user) as get_user:
            result = deps.get_current_user(db=db, token=token)

    assert result is user
    get_user.assert_called_once_with(db, id=str(user_id))


def test_get_current_user_raises_401_for_expired_jwt():
    db = object()
    user_id = uuid4()
    token = _make_jwt(user_id, expired=True)

    with patch.object(deps, "get_db", return_value=db):
        with pytest.raises(HTTPException) as exc:
            deps.get_current_user(db=db, token=token)
    assert exc.value.status_code == 401
    assert "expired" in exc.value.detail.lower()


def test_get_current_user_raises_403_for_garbled_jwt():
    db = object()
    with patch.object(deps, "get_db", return_value=db):
        with pytest.raises(HTTPException) as exc:
            deps.get_current_user(db=db, token="not.a.real.token")
    assert exc.value.status_code == 403


def test_get_current_user_raises_401_when_user_missing():
    db = object()
    user_id = uuid4()
    token = _make_jwt(user_id)

    with patch.object(deps, "get_db", return_value=db):
        with patch.object(deps.crud_user, "get", return_value=None):
            with pytest.raises(HTTPException) as exc:
                deps.get_current_user(db=db, token=token)
    assert exc.value.status_code == 401


def test_get_current_user_accepts_agent_token():
    db = object()
    user_id = uuid4()
    agent_token_value = "ts_abcdef1234567890"
    agent_row = SimpleNamespace(
        user_id=user_id,
        expires_at=datetime.utcnow() + timedelta(days=1),
    )
    user = _user_row(user_id)

    with patch.object(deps, "get_db", return_value=db):
        with patch(
            "app.crud.agent_token.get_token_by_string", return_value=agent_row
        ) as get_token:
            with patch.object(deps.crud_user, "get", return_value=user) as get_user:
                result = deps.get_current_user(db=db, token=agent_token_value)

    assert result is user
    get_token.assert_called_once_with(db, agent_token_value)
    get_user.assert_called_once_with(db, id=user_id)


def test_get_current_user_rejects_unknown_agent_token():
    db = object()
    with patch.object(deps, "get_db", return_value=db):
        with patch("app.crud.agent_token.get_token_by_string", return_value=None):
            with pytest.raises(HTTPException) as exc:
                deps.get_current_user(db=db, token="ts_unknown")
    assert exc.value.status_code == 401
    assert "invalid" in exc.value.detail.lower()


def test_get_current_user_rejects_expired_agent_token():
    db = object()
    user_id = uuid4()
    agent_row = SimpleNamespace(
        user_id=user_id,
        expires_at=datetime.utcnow() - timedelta(days=1),
    )

    with patch.object(deps, "get_db", return_value=db):
        with patch("app.crud.agent_token.get_token_by_string", return_value=agent_row):
            with pytest.raises(HTTPException) as exc:
                deps.get_current_user(db=db, token="ts_expired")
    assert exc.value.status_code == 401
    assert "expired" in exc.value.detail.lower()


def test_resolve_user_from_token_rejects_empty():
    with pytest.raises(HTTPException) as exc:
        deps.resolve_user_from_token(token="", db=object())
    assert exc.value.status_code == 401


def test_resolve_user_from_token_returns_user_for_valid_jwt():
    db = object()
    user_id = uuid4()
    token = _make_jwt(user_id)
    user = _user_row(user_id)

    with patch.object(deps.crud_user, "get", return_value=user):
        result = deps.resolve_user_from_token(token=token, db=db)
    assert result is user


def test_resolve_user_from_token_uses_query_token_branch():
    """`resolve_user_from_token` must also dispatch agent tokens correctly."""
    db = object()
    user_id = uuid4()
    agent_row = SimpleNamespace(
        user_id=user_id,
        expires_at=datetime.utcnow() + timedelta(days=1),
    )
    user = _user_row(user_id)

    with patch("app.crud.agent_token.get_token_by_string", return_value=agent_row):
        with patch.object(deps.crud_user, "get", return_value=user):
            result = deps.resolve_user_from_token(token="ts_queryparam", db=db)
    assert result is user
