"""Nightly coverage for the ``ts_`` agent-token branch of ``app.api.deps``.

The 2026-10-24 backend coverage report ranked ``api/deps.py`` at 82.1% with
12 statements never executed.  The uncovered lines are the *duplicate*
resolution path used by SSE / polling endpoints
(``resolve_user_from_token``) plus the "token owner no longer exists"
branch of the header-based dependency.

Agent tokens are how the CLI and external agents authenticate, so the
contract under test is that every rejection path returns the documented
status code (401 for missing/expired/unknown, 403 for a malformed JWT)
and never leaks a user object.
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


pytestmark = [pytest.mark.smoke, pytest.mark.module_user]


def _make_jwt(user_id, *, expired: bool = False) -> str:
    secret = system_config.config.security.secret_key
    algo = system_config.config.security.algorithm
    exp = datetime.utcnow() + (timedelta(minutes=-5) if expired else timedelta(minutes=10))
    return jwt.encode({"sub": str(user_id), "exp": exp}, secret, algorithm=algo)


def _agent_token(user_id, *, expired: bool = False, scopes=None):
    expires = datetime.utcnow() + (timedelta(minutes=-5) if expired else timedelta(days=1))
    return SimpleNamespace(
        id="agent-token-1",
        user_id=user_id,
        scopes=scopes if scopes is not None else ["photos:read"],
        expires_at=expires,
    )


def _user_row(user_id):
    return SimpleNamespace(id=user_id, email="u@example.com")


# ---------------------------------------------------------------------------
# get_current_user -- agent token whose owner disappeared
# ---------------------------------------------------------------------------


def test_get_current_user_rejects_agent_token_without_user():
    """A token that outlived its owner must not authenticate anybody."""
    db = object()
    user_id = uuid4()
    token = _agent_token(user_id)

    with patch.object(deps.crud_user, "get", return_value=None):
        with patch("app.crud.agent_token.get_token_by_string", return_value=token):
            with pytest.raises(HTTPException) as excinfo:
                deps.get_current_user(
                    request=SimpleNamespace(method="GET", url=SimpleNamespace(path="/photos")),
                    db=db,
                    token="ts_valid",
                )

    assert excinfo.value.status_code == 401
    assert excinfo.value.detail == "User not found"


# ---------------------------------------------------------------------------
# resolve_user_from_token -- agent token branch
# ---------------------------------------------------------------------------


def test_resolve_user_from_token_rejects_unknown_agent_token():
    """An unknown ``ts_`` token is a 401, not a 403."""
    db = object()

    with patch("app.crud.agent_token.get_token_by_string", return_value=None):
        with pytest.raises(HTTPException) as excinfo:
            deps.resolve_user_from_token("ts_unknown", db, method="GET", path="/photos")

    assert excinfo.value.status_code == 401
    assert excinfo.value.detail == "Invalid token"


def test_resolve_user_from_token_rejects_expired_agent_token():
    """An expired ``ts_`` token is a 401 with an explicit message."""
    db = object()
    token = _agent_token(uuid4(), expired=True)

    with patch("app.crud.agent_token.get_token_by_string", return_value=token):
        with pytest.raises(HTTPException) as excinfo:
            deps.resolve_user_from_token("ts_expired", db, method="GET", path="/photos")

    assert excinfo.value.status_code == 401
    assert excinfo.value.detail == "Token has expired"


def test_resolve_user_from_token_rejects_agent_token_without_user():
    """A ``ts_`` token pointing at a deleted user cannot authenticate."""
    db = object()
    token = _agent_token(uuid4())

    with patch("app.crud.agent_token.get_token_by_string", return_value=token):
        with patch.object(deps.crud_user, "get", return_value=None):
            with pytest.raises(HTTPException) as excinfo:
                deps.resolve_user_from_token("ts_orphan", db, method="GET", path="/photos")

    assert excinfo.value.status_code == 401
    assert excinfo.value.detail == "User not found"


def test_resolve_user_from_token_accepts_agent_token_and_checks_scope():
    """A valid ``ts_`` token resolves its owner and applies the scope policy."""
    db = object()
    user_id = uuid4()
    token = _agent_token(user_id, scopes=["photos:read"])
    user = _user_row(user_id)

    with patch("app.crud.agent_token.get_token_by_string", return_value=token):
        with patch.object(deps.crud_user, "get", return_value=user):
            with patch("app.service.agent_token_access.enforce_agent_token_rest_access") as enforce:
                result = deps.resolve_user_from_token(
                    "ts_valid", db, method="GET", path="/photos"
                )

    assert result is user
    enforce.assert_called_once_with("GET", "/photos", ["photos:read"])


# ---------------------------------------------------------------------------
# resolve_user_from_token -- JWT branch
# ---------------------------------------------------------------------------


def test_resolve_user_from_token_rejects_expired_jwt():
    """An expired JWT is a 401 with the dedicated message."""
    db = object()
    token = _make_jwt(uuid4(), expired=True)

    with pytest.raises(HTTPException) as excinfo:
        deps.resolve_user_from_token(token, db, method="GET", path="/photos")

    assert excinfo.value.status_code == 401
    assert excinfo.value.detail == "Token has expired"


def test_resolve_user_from_token_rejects_garbled_jwt():
    """A malformed JWT is a 403 (invalid credentials, not merely missing)."""
    db = object()

    with pytest.raises(HTTPException) as excinfo:
        deps.resolve_user_from_token("not-a-jwt", db, method="GET", path="/photos")

    assert excinfo.value.status_code == 403
    assert excinfo.value.detail == "Could not validate credentials"


def test_resolve_user_from_token_rejects_jwt_without_user():
    """A valid JWT for a deleted user is a 401."""
    db = object()
    token = _make_jwt(uuid4())

    with patch.object(deps.crud_user, "get", return_value=None):
        with pytest.raises(HTTPException) as excinfo:
            deps.resolve_user_from_token(token, db, method="GET", path="/photos")

    assert excinfo.value.status_code == 401
    assert excinfo.value.detail == "User not found"
