"""Unit tests for the auth REST router (app/api/auth.py).

Covers the ``status`` endpoint (registration gating + demo-mode flag),
``send-log-reset-code`` rate-limit path, and the ``login`` /
``register`` / ``check-reset-user`` / ``reset-password`` /
``reset-password-by-code`` flows. ``crud_user`` and ``reset_code_store``
are patched so no DB / persistent state is touched.
"""

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.security import OAuth2PasswordRequestForm

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


# ----------------------- POST /auth/login -----------------------


def _form(username="alice", password="secret"):
    return SimpleNamespace(username=username, password=password)


def test_login_returns_token_for_valid_credentials():
    db = MagicMock()
    user = SimpleNamespace(id=uuid4(), is_active=True)
    form = _form()

    with patch.object(auth_api.crud_user, "authenticate", return_value=user):
        with patch.object(auth_api.security, "create_access_token", return_value="JWT"):
            response = auth_api.login_access_token(db=db, form_data=form)

    assert response["access_token"] == "JWT"
    assert response["token_type"] == "bearer"


def test_login_rejects_inactive_user_with_400():
    db = MagicMock()
    user = SimpleNamespace(id=uuid4(), is_active=False)
    form = _form()

    with patch.object(auth_api.crud_user, "authenticate", return_value=user):
        with pytest.raises(HTTPException) as exc_info:
            auth_api.login_access_token(db=db, form_data=form)

    assert exc_info.value.status_code == 400
    assert "禁用" in exc_info.value.detail


def test_login_returns_403_when_account_locked():
    """Wrong creds + account lockout → 403 with lockout message."""
    db = MagicMock()
    locked = SimpleNamespace(
        id=uuid4(),
        is_active=True,
        lockout_until=datetime.now() + timedelta(minutes=5),
    )
    form = _form()

    with patch.object(auth_api.crud_user, "authenticate", return_value=None), \
         patch.object(auth_api.crud_user, "get_by_username_or_email", return_value=locked):
        with pytest.raises(HTTPException) as exc_info:
            auth_api.login_access_token(db=db, form_data=form)

    assert exc_info.value.status_code == 403
    assert "锁定" in exc_info.value.detail


def test_login_returns_401_for_wrong_credentials():
    db = MagicMock()
    form = _form(username="nobody", password="wrong")

    with patch.object(auth_api.crud_user, "authenticate", return_value=None), \
         patch.object(auth_api.crud_user, "get_by_username_or_email", return_value=None):
        with pytest.raises(HTTPException) as exc_info:
            auth_api.login_access_token(db=db, form_data=form)

    assert exc_info.value.status_code == 401


# ----------------------- POST /auth/register -----------------------


def test_register_blocks_when_users_exist_and_registration_disabled():
    db = MagicMock()
    db.query.return_value.count.return_value = 1
    payload = SimpleNamespace(username="bob", email="bob@example.com", is_superuser=False)

    with patch.object(auth_api.system_config.config.security, "allow_registration", False):
        with pytest.raises(HTTPException) as exc_info:
            auth_api.register_user(db=db, user_in=payload)

    assert exc_info.value.status_code == 403


def test_register_rejects_duplicate_email():
    db = MagicMock()
    db.query.return_value.count.side_effect = [2, 2]  # has_users, then first_user check
    payload = SimpleNamespace(username="bob", email="dup@example.com", is_superuser=False)
    existing = SimpleNamespace(email="dup@example.com")

    with patch.object(auth_api.system_config.config.security, "allow_registration", True), \
         patch.object(auth_api.crud_user, "get_by_email", return_value=existing):
        with pytest.raises(HTTPException) as exc_info:
            auth_api.register_user(db=db, user_in=payload)

    assert exc_info.value.status_code == 400
    assert "email" in exc_info.value.detail.lower()


def test_register_rejects_duplicate_username():
    db = MagicMock()
    db.query.return_value.count.side_effect = [2, 2]
    payload = SimpleNamespace(username="dup", email="bob@example.com", is_superuser=False)
    existing_user = SimpleNamespace(username="dup")

    with patch.object(auth_api.system_config.config.security, "allow_registration", True), \
         patch.object(auth_api.crud_user, "get_by_email", return_value=None), \
         patch.object(auth_api.crud_user, "get_by_username", return_value=existing_user):
        with pytest.raises(HTTPException) as exc_info:
            auth_api.register_user(db=db, user_in=payload)

    assert exc_info.value.status_code == 400
    assert "username" in exc_info.value.detail.lower()


def test_register_promotes_first_user_to_superuser_and_migrates_config():
    db = MagicMock()
    # 0 users → first_user path; crud_user.create is the last call before return
    db.query.return_value.count.side_effect = [0, 0]
    payload = SimpleNamespace(username="founder", email="founder@example.com", is_superuser=False)
    created = SimpleNamespace(id=uuid4())

    with patch.object(auth_api.system_config.config.security, "allow_registration", True), \
         patch.object(auth_api.crud_user, "get_by_email", return_value=None), \
         patch.object(auth_api.crud_user, "get_by_username", return_value=None), \
         patch.object(auth_api.crud_user, "create", return_value=created) as create, \
         patch.object(auth_api.config_manager, "get_default_config", return_value={"default": True}), \
         patch.object(auth_api, "migrate_system_config") as migrate:
        result = auth_api.register_user(db=db, user_in=payload)

    # 第一次注册自动升级为 superuser
    assert payload.is_superuser is True
    create.assert_called_once_with(db, user=payload)
    migrate.assert_called_once_with(db, created)
    assert result is created


# ----------------------- POST /auth/check-reset-user -----------------------


def test_check_reset_user_404_when_user_missing():
    db = MagicMock()
    payload = SimpleNamespace(username_or_email="nobody@example.com")

    with patch.object(auth_api.crud_user, "get_by_username_or_email", return_value=None):
        with pytest.raises(HTTPException) as exc_info:
            auth_api.check_password_reset_user(payload=payload, db=db)

    assert exc_info.value.status_code == 404


def test_check_reset_user_400_when_no_security_question():
    db = MagicMock()
    payload = SimpleNamespace(username_or_email="alice@example.com")
    user = SimpleNamespace(security_question=None)

    with patch.object(auth_api.crud_user, "get_by_username_or_email", return_value=user):
        with pytest.raises(HTTPException) as exc_info:
            auth_api.check_password_reset_user(payload=payload, db=db)

    assert exc_info.value.status_code == 400
    assert "security" in exc_info.value.detail.lower()


def test_check_reset_user_returns_security_question():
    db = MagicMock()
    payload = SimpleNamespace(username_or_email="alice@example.com")
    user = SimpleNamespace(security_question="你最喜欢的颜色？")

    with patch.object(auth_api.crud_user, "get_by_username_or_email", return_value=user):
        response = auth_api.check_password_reset_user(payload=payload, db=db)

    assert response["security_question"] == "你最喜欢的颜色？"


# ----------------------- POST /auth/reset-password -----------------------


def test_confirm_password_reset_rejects_wrong_answer():
    db = MagicMock()
    payload = SimpleNamespace(
        username_or_email="alice@example.com",
        security_answer="wrong",
        new_password="newpw",
    )
    user = SimpleNamespace()

    with patch.object(auth_api.crud_user, "get_by_username_or_email", return_value=user), \
         patch.object(auth_api.crud_user, "verify_security_answer", return_value=False):
        with pytest.raises(HTTPException) as exc_info:
            auth_api.confirm_password_reset(payload=payload, db=db)

    assert exc_info.value.status_code == 400
    assert "Incorrect security answer" in exc_info.value.detail


def test_confirm_password_reset_succeeds_and_returns_user():
    db = MagicMock()
    payload = SimpleNamespace(
        username_or_email="alice@example.com",
        security_answer="correct",
        new_password="newpw",
    )
    user = SimpleNamespace()
    updated = SimpleNamespace(id=uuid4())

    with patch.object(auth_api.crud_user, "get_by_username_or_email", return_value=user), \
         patch.object(auth_api.crud_user, "verify_security_answer", return_value=True), \
         patch.object(auth_api.crud_user, "reset_password", return_value=updated) as reset_pw:
        result = auth_api.confirm_password_reset(payload=payload, db=db)

    reset_pw.assert_called_once_with(db, user, "newpw")
    assert result is updated


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


# ----------------------- POST /auth/reset-password-by-code -----------------------


def test_reset_password_by_code_rejects_short_password():
    db = MagicMock()
    payload = SimpleNamespace(
        username_or_email="alice@example.com",
        code="123456",
        new_password="abc",
    )

    with patch.object(auth_api.reset_code_store, "verify_code") as verify:
        response = auth_api.reset_password_by_code(payload=payload, db=db)

    assert response.code == 400
    assert "6" in response.msg
    verify.assert_not_called()


def test_reset_password_by_code_rejects_missing_user():
    db = MagicMock()
    payload = SimpleNamespace(
        username_or_email="nobody@example.com",
        code="123456",
        new_password="abcdef",
    )

    with patch.object(auth_api.crud_user, "get_by_username_or_email", return_value=None):
        response = auth_api.reset_password_by_code(payload=payload, db=db)

    assert response.code == 404


def test_reset_password_by_code_rejects_bad_code():
    db = MagicMock()
    payload = SimpleNamespace(
        username_or_email="alice@example.com",
        code="000000",
        new_password="abcdef",
    )
    user = _user()

    with patch.object(auth_api.crud_user, "get_by_username_or_email", return_value=user), \
         patch.object(auth_api.reset_code_store, "verify_code", return_value=False):
        response = auth_api.reset_password_by_code(payload=payload, db=db)

    assert response.code == 400
    assert "验证码" in response.msg


def test_reset_password_by_code_succeeds_and_consumes_code():
    db = MagicMock()
    payload = SimpleNamespace(
        username_or_email="alice@example.com",
        code="123456",
        new_password="abcdef",
    )
    user = _user()

    with patch.object(auth_api.crud_user, "get_by_username_or_email", return_value=user), \
         patch.object(auth_api.reset_code_store, "verify_code", return_value=True) as verify, \
         patch.object(auth_api.crud_user, "reset_password") as reset_pw:
        response = auth_api.reset_password_by_code(payload=payload, db=db)

    verify.assert_called_once_with(str(user.id), "123456", "alice@example.com")
    reset_pw.assert_called_once_with(db, user, "abcdef")
    assert response.code == 0
