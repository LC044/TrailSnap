import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import or_
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import AgentToken, User


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def authenticate(db: Session, identifier: str, password: str) -> User | None:
    user = db.query(User).filter(or_(User.username == identifier, User.email == identifier)).first()
    if not user or not user.is_active or not verify_password(password, user.password_hash):
        return None
    return user


def create_token(user: User) -> str:
    expires = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    return jwt.encode({"sub": user.id, "role": user.role, "exp": expires}, settings.jwt_secret, algorithm="HS256")


def create_agent_token_value() -> tuple[str, str, str]:
    value = f"trp_{secrets.token_urlsafe(36)}"
    return value, value[:12], hashlib.sha256(value.encode()).hexdigest()


def resolve_agent_token(db: Session, value: str) -> AgentToken | None:
    token_hash = hashlib.sha256(value.encode()).hexdigest()
    row = db.query(AgentToken).filter(AgentToken.token_hash == token_hash, AgentToken.revoked_at.is_(None)).first()
    now = datetime.now(timezone.utc)
    if not row or (row.expires_at and row.expires_at.replace(tzinfo=timezone.utc) <= now):
        return None
    return row


def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        payload = jwt.decode(credentials.credentials, settings.jwt_secret, algorithms=["HS256"])
        user_id = payload.get("sub")
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc
    user = db.query(User).filter(User.id == user_id, User.is_active.is_(True)).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User | None:
    if credentials is None:
        return None
    return current_user(credentials, db)


def manager(user: User = Depends(current_user)) -> User:
    if user.role not in {"admin", "owner"}:
        raise HTTPException(status_code=403, detail="Manager role required")
    return user


def owner(user: User = Depends(current_user)) -> User:
    if user.role != "owner":
        raise HTTPException(status_code=403, detail="Owner role required")
    return user
