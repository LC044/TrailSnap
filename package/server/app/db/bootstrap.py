"""Database bootstrap helpers for runtime-specific setup."""

from __future__ import annotations

import os
import secrets

from sqlalchemy.orm import Session

from app.core.security import get_password_hash
from app.db.models.user import User

DESKTOP_ADMIN_USERNAME = "desktop-admin"
DESKTOP_ADMIN_EMAIL = "desktop@trailsnap.local"


def is_desktop_mode() -> bool:
    return os.environ.get("TS_DESKTOP") == "1"


def ensure_desktop_admin(db: Session) -> User:
    """Create the local administrator once and return it on every startup."""

    if not is_desktop_mode():
        raise RuntimeError("Desktop administrator is only available in desktop mode")

    user = db.query(User).filter(User.username == DESKTOP_ADMIN_USERNAME).first()
    if user:
        return user

    user = User(
        username=DESKTOP_ADMIN_USERNAME,
        email=DESKTOP_ADMIN_EMAIL,
        nickname="TrailSnap Desktop",
        hashed_password=get_password_hash(secrets.token_urlsafe(32)),
        is_active=True,
        is_superuser=True,
        settings={},
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
