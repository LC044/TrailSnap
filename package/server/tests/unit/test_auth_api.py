"""Unit tests for the auth REST router (app/api/auth.py).

Covers the ``status`` endpoint (registration gating + demo-mode flag) and
the ``send-log-reset-code`` rate-limit path. ``crud_user`` and the
``reset_code_store`` are patched so no DB / persistent state is touched.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.api import auth as auth_api


pytestmark = [pytest.mark.smoke, pytest.mark.module_user]


def _user():
    return SimpleNamespace(id=uuid4(), username="alice", email="alice@example.com")


# ----------------------- GET /auth/status -----------------------


def test_auth_status_allow_registration_true_no_users():
    """Status reflects allow_registration flag and has_users count."""
    db = MagicMock()
    db.query.return_value.count.return_value = 0  # no users yet

    with patch.object(auth_api.system_config.config.security, "allow_registration", True), \
         patch("app.middleware.demo_mode.DEMO_MODE", False):
        response = auth_api.get_auth_status(db=db)

    assert response["has_users"] is False
    assert response["allow_registration"] is True
    assert response["demo_mode"] is False


def test_auth_status_registration_blocked_after_first_user():
    """When users exist and admin disabled registration, status is blocked."""
    db = MagicMock()
    db.query.return_value.count.return_value = 1

    with patch.object(auth_api.system_config.config.security, "allow_registration", False), \
         patch("app.middleware.demo_mode.DEMO_MODE", True):
        response = auth_api.get_auth_status(db=db)

    assert response["has_users"] is True
    assert response["allow_registration"] is False
    assert response["demo_mode"] is True


# ----------------------- POST /auth/send-log-reset-code -----------------------


def test_send_log_reset_code_404_when_user_missing():
    """Missing user → BaseResponse.fail(404)."""
    db = MagicMock()
    payload = SimpleNamespace(username_or_email="nobody@example.com")

    with patch.object(auth_api.crud_user, "get_by_username_or_email", return_value=None):
        response = auth_api.send_log_reset_code(payload=payload, db=db)

    assert response.code == 404
    assert "不存在" in response.msg


def test_send_log_reset_code_429_when_rate_limited():
    """Issue-code returning None (rate-limited) → 429."""
    db = MagicMock()
    payload = SimpleNamespace(username_or_email="alice@example.com")
    user = _user()

    with patch.object(auth_api.crud_user, "get_by_username_or_email", return_value=user), \
         patch.object(auth_api.reset_code_store, "issue_code", return_value=None):
        response = auth_api.send_log_reset_code(payload=payload, db=db)

    assert response.code == 429
    assert "发送过于频繁" in response.msg


def test_send_log_reset_code_success_returns_log_instruction():
    """Successful issuance → 0 and a message telling admin to check server logs."""
    db = MagicMock()
    payload = SimpleNamespace(username_or_email="alice@example.com")
    user = _user()

    with patch.object(auth_api.crud_user, "get_by_username_or_email", return_value=user), \
         patch.object(auth_api.reset_code_store, "issue_code", return_value="123456"):
        response = auth_api.send_log_reset_code(payload=payload, db=db)

    assert response.code == 0
    assert "服务器日志" in response.msg
