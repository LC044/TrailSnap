import logging
import os
import secrets
from datetime import timedelta, datetime
from typing import Any
from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from app.crud import user as crud_user
from app.schemas.user import (
    UserCreate,
    UserResponse,
    PasswordResetCheck,
    PasswordResetCheckResponse,
    PasswordResetConfirm,
    LogResetCodeConfirm
)
from app.schemas.token import Token
from app.core import security
from app.core.config_manager import config_manager
from app.core.system_config import system_config
from app.core.migration import migrate_system_config
from app.dependencies import get_db, BaseResponse
from app.service import reset_code_store

logger = logging.getLogger("app.auth")

router = APIRouter()


@router.post("/desktop-session", response_model=BaseResponse[Token])
def create_desktop_session(
    db: Session = Depends(get_db),
    desktop_secret: str | None = Header(
        default=None,
        alias="X-TrailSnap-Desktop-Secret",
    ),
) -> Any:
    """Issue the normal administrator JWT used by the local desktop UI."""

    from app.db.bootstrap import ensure_desktop_admin, is_desktop_mode

    expected_secret = os.environ.get("TS_DESKTOP_SESSION_SECRET")
    if (
        not is_desktop_mode()
        or not expected_secret
        or not isinstance(desktop_secret, str)
        or not desktop_secret
        or not secrets.compare_digest(desktop_secret, expected_secret)
    ):
        raise HTTPException(status_code=404, detail="Not found")

    user = ensure_desktop_admin(db)
    access_token_expires = timedelta(
        minutes=system_config.config.security.access_token_expire_minutes
    )
    return BaseResponse.success(
        data={
            "access_token": security.create_access_token(
                {"sub": str(user.id)}, expires_delta=access_token_expires
            ),
            "token_type": "bearer",
        }
    )


@router.post("/login", response_model=Token)
def login_access_token(
    db: Session = Depends(get_db), form_data: OAuth2PasswordRequestForm = Depends()
) -> Any:
    """
    OAuth2 compatible token login, get an access token for future requests
    """
    user = crud_user.authenticate(
        db, email=form_data.username, password=form_data.password
    )
    if not user:
        # Check if user exists to provide more specific error (lockout vs invalid creds)
        user_obj = crud_user.get_by_username_or_email(db, identifier=form_data.username)
        if user_obj and user_obj.lockout_until and user_obj.lockout_until > datetime.now():
             raise HTTPException(status_code=403, detail="密码错误次数过多，用户已被锁定，请5分钟后重试")

        raise HTTPException(status_code=401, detail="用户名或密码错误")
    elif not user.is_active:
        raise HTTPException(status_code=400, detail="用户已被禁用")
    
    access_token_expires = timedelta(minutes=system_config.config.security.access_token_expire_minutes)
    return {
        "access_token": security.create_access_token(
            {"sub": str(user.id)}, expires_delta=access_token_expires
        ),
        "token_type": "bearer",
    }

@router.post("/register", response_model=UserResponse)
def register_user(
    *,
    db: Session = Depends(get_db),
    user_in: UserCreate,
) -> Any:
    """
    Create new user.
    """
    # Check if registration is allowed (always allowed when no users exist — first-time setup)
    has_users = db.query(crud_user.User).count() > 0
    if has_users and not system_config.config.security.allow_registration:
        raise HTTPException(
            status_code=403,
            detail="Registration is currently disabled. Please contact an administrator.",
        )

    user = crud_user.get_by_email(db, email=user_in.email)
    if user:
        raise HTTPException(
            status_code=400,
            detail="The user with this email already exists in the system.",
        )
    user = crud_user.get_by_username(db, username=user_in.username)
    if user:
         raise HTTPException(
            status_code=400,
            detail="The user with this username already exists in the system.",
        )

    # Check if this is the first user
    is_first_user = db.query(crud_user.User).count() == 0
    if is_first_user:
        user_in.is_superuser = True

    user = crud_user.create(db, user=user_in)
    user.settings = config_manager.get_default_config()  # Apply default settings to new user
    if is_first_user:
        migrate_system_config(db, user)

    return user

@router.post("/check-reset-user", response_model=PasswordResetCheckResponse)
def check_password_reset_user(
    payload: PasswordResetCheck,
    db: Session = Depends(get_db)
) -> Any:
    """
    Check if user exists and return security question.
    """
    user = crud_user.get_by_username_or_email(db, identifier=payload.username_or_email)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not user.security_question:
        raise HTTPException(status_code=400, detail="User has no security question set")

    return {"security_question": user.security_question}

@router.post("/reset-password", response_model=UserResponse)
def confirm_password_reset(
    payload: PasswordResetConfirm,
    db: Session = Depends(get_db)
) -> Any:
    """
    Verify security answer and reset password.
    """
    user = crud_user.get_by_username_or_email(db, identifier=payload.username_or_email)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not crud_user.verify_security_answer(user, payload.security_answer):
        raise HTTPException(status_code=400, detail="Incorrect security answer")

    user = crud_user.reset_password(db, user, payload.new_password)
    return user

@router.post("/send-log-reset-code")
def send_log_reset_code(
    payload: PasswordResetCheck,
    db: Session = Depends(get_db)
) -> BaseResponse:
    """
    生成密码重置验证码并写入服务器日志（兜底重置方式）。

    验证码只会出现在服务器日志中，绝不返回给前端。
    同一用户 60 秒内只能生成一次。
    """
    user = crud_user.get_by_username_or_email(db, identifier=payload.username_or_email)
    if not user:
        return BaseResponse.fail(code=404, msg="用户不存在")

    code = reset_code_store.issue_code(str(user.id), payload.username_or_email)
    if code is None:
        return BaseResponse.fail(code=429, msg=f"发送过于频繁，请 {reset_code_store.RESEND_INTERVAL_SECONDS} 秒后再试")

    return BaseResponse.success(
        msg=f"验证码已写入服务器日志（有效期 {reset_code_store.CODE_TTL_SECONDS // 60} 分钟），请联系管理员查看日志获取"
    )

@router.post("/reset-password-by-code")
def reset_password_by_code(
    payload: LogResetCodeConfirm,
    db: Session = Depends(get_db)
) -> BaseResponse:
    """
    通过服务器日志验证码重置密码。

    校验验证码正确且未过期后立即重置密码，验证码用一次即焚。
    """
    if len(payload.new_password) < 6:
        return BaseResponse.fail(code=400, msg="密码长度至少 6 位")

    user = crud_user.get_by_username_or_email(db, identifier=payload.username_or_email)
    if not user:
        return BaseResponse.fail(code=404, msg="用户不存在")

    if not reset_code_store.verify_code(str(user.id), payload.code, payload.username_or_email):
        return BaseResponse.fail(code=400, msg="验证码错误或已过期")

    crud_user.reset_password(db, user, payload.new_password)
    logger.info("用户 %s 通过服务器日志验证码重置密码成功", payload.username_or_email)
    return BaseResponse.success(msg="密码重置成功")

@router.get("/status")
def get_auth_status(db: Session = Depends(get_db)):
    has_users = db.query(crud_user.User).count() > 0
    allow_registration = system_config.config.security.allow_registration
    # demo_mode 供前端可选地展示「演示模式」横幅；不设置时为 False，零影响。
    from app.middleware.demo_mode import DEMO_MODE
    return {
        "has_users": has_users,
        "allow_registration": allow_registration,
        "demo_mode": DEMO_MODE,
    }
