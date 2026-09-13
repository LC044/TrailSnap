import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from jose import JWTError, jwt
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..domain.common import audit
from ..models import GitHubIdentity, OAuthLoginGrant, User
from ..presenters import user_data
from ..schemas import LoginInput, RegisterInput
from ..security import authenticate, create_token, current_user, hash_password, optional_user
from .responses import ok

router = APIRouter(prefix="/api/auth", tags=["auth"])
logger = logging.getLogger(__name__)


@router.get("/status")
def auth_status(db: Session = Depends(get_db)):
    return ok({"has_owner": db.query(User).filter(User.role == "owner").first() is not None,
               "allow_registration": settings.allow_registration,
               "github_oauth_enabled": bool(settings.github_oauth_client_id and settings.github_oauth_client_secret)})


@router.post("/register")
def register(payload: RegisterInput, db: Session = Depends(get_db)):
    has_users = db.query(User.id).first() is not None
    if has_users and not settings.allow_registration:
        raise HTTPException(status_code=403, detail="Registration is disabled")
    has_owner = db.query(User.id).filter(User.role == "owner").first() is not None
    email = str(payload.email).lower()
    if not has_owner and settings.owner_email and email != settings.owner_email:
        raise HTTPException(status_code=403, detail="The configured owner must register first")
    role = "owner" if not has_owner else "viewer"
    user = User(username=payload.username, email=email, password_hash=hash_password(payload.password), role=role)
    db.add(user)
    try:
        db.flush()
        audit(db, user.id, "user.registered", "user", user.id, role=role)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Username or email already exists") from exc
    db.refresh(user)
    return ok({"token": create_token(user), "user": user_data(user, db)})


@router.post("/login")
def login(payload: LoginInput, db: Session = Depends(get_db)):
    user = authenticate(db, payload.identifier, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username/email or password")
    audit(db, user.id, "user.login", "user", user.id)
    db.commit()
    return ok({"token": create_token(user), "user": user_data(user, db)})


@router.get("/me")
def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return ok(user_data(user, db))


@router.get("/github/start")
def github_oauth_start(mode: str = Query("login", pattern="^(login|link)$"), user: User | None = Depends(optional_user)):
    if not (settings.github_oauth_client_id and settings.github_oauth_client_secret):
        raise HTTPException(status_code=503, detail="GitHub OAuth is not configured")
    if mode == "link" and not user:
        raise HTTPException(status_code=401, detail="Authentication required before linking GitHub")
    state = jwt.encode(
        {"purpose": "github_oauth", "mode": mode, "user_id": user.id if user else None,
         "nonce": secrets.token_urlsafe(16), "exp": datetime.now(timezone.utc) + timedelta(minutes=10)},
        settings.jwt_secret, algorithm="HS256",
    )
    url = "https://github.com/login/oauth/authorize?" + urlencode({
        "client_id": settings.github_oauth_client_id, "redirect_uri": settings.github_oauth_redirect_uri,
        "scope": "read:user user:email", "state": state,
    })
    response = JSONResponse(ok({"authorize_url": url}))
    response.set_cookie("rp_github_oauth", state, max_age=600, httponly=True,
                        secure=settings.web_url.startswith("https://"), samesite="lax", path="/api/auth/github")
    return response


@router.get("/github/callback")
def github_oauth_callback(code: str, state: str, request: Request, db: Session = Depends(get_db)):
    if request.cookies.get("rp_github_oauth") != state:
        raise HTTPException(status_code=400, detail="GitHub OAuth state mismatch")
    try:
        state_data = jwt.decode(state, settings.jwt_secret, algorithms=["HS256"])
        if state_data.get("purpose") != "github_oauth":
            raise JWTError("invalid purpose")
    except JWTError as exc:
        raise HTTPException(status_code=400, detail="GitHub OAuth state is invalid or expired") from exc
    try:
        token_response = httpx.post(
            "https://github.com/login/oauth/access_token", headers={"Accept": "application/json"},
            data={"client_id": settings.github_oauth_client_id, "client_secret": settings.github_oauth_client_secret,
                  "code": code, "redirect_uri": settings.github_oauth_redirect_uri}, timeout=20,
        )
        token_response.raise_for_status()
        access_token = token_response.json().get("access_token")
        if not access_token:
            raise ValueError("GitHub did not return an access token")
        headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github+json"}
        profile_response = httpx.get("https://api.github.com/user", headers=headers, timeout=20)
        profile_response.raise_for_status()
        profile = profile_response.json()
        email = profile.get("email")
        if not email:
            emails_response = httpx.get("https://api.github.com/user/emails", headers=headers, timeout=20)
            emails_response.raise_for_status()
            emails = emails_response.json()
            verified = [item for item in emails if item.get("verified")]
            primary = next((item for item in verified if item.get("primary")), verified[0] if verified else None)
            email = primary.get("email") if primary else None
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        logger.exception("GitHub OAuth token or profile request failed: %s", type(exc).__name__)
        response = RedirectResponse(f"{settings.web_url}/?github_error=oauth_upstream", status_code=302)
        response.delete_cookie("rp_github_oauth", path="/api/auth/github")
        return response

    github_user_id = int(profile["id"])
    identity = db.query(GitHubIdentity).filter(GitHubIdentity.github_user_id == github_user_id).first()
    mode, linked_user_id = state_data.get("mode"), state_data.get("user_id")
    if mode == "link":
        user = db.query(User).filter(User.id == linked_user_id, User.is_active.is_(True)).first()
        if not user:
            raise HTTPException(status_code=401, detail="Linking user no longer exists")
        if identity and identity.user_id != user.id:
            raise HTTPException(status_code=409, detail="This GitHub account is already linked")
        existing = db.query(GitHubIdentity).filter(GitHubIdentity.user_id == user.id).first()
        if existing and existing.github_user_id != github_user_id:
            raise HTTPException(status_code=409, detail="User already has a linked GitHub account")
        identity = existing or GitHubIdentity(user_id=user.id, github_user_id=github_user_id, login=profile["login"])
    elif identity:
        user = db.query(User).filter(User.id == identity.user_id, User.is_active.is_(True)).first()
        if not user:
            raise HTTPException(status_code=403, detail="Linked user is disabled")
    else:
        if not settings.allow_registration:
            raise HTTPException(status_code=403, detail="Registration is disabled; link GitHub from an existing account")
        if not email:
            raise HTTPException(status_code=409, detail="A verified GitHub email is required")
        email = email.lower()
        user = db.query(User).filter(User.email == email).first()
        has_owner = db.query(User.id).filter(User.role == "owner").first() is not None
        if not user:
            if not has_owner and settings.owner_email and email != settings.owner_email:
                raise HTTPException(status_code=403, detail="The configured owner must sign in first")
            base = str(profile["login"])[:45]
            username, suffix = base, 1
            while db.query(User.id).filter(User.username == username).first():
                suffix += 1
                username = f"{base[:45-len(str(suffix))]}-{suffix}"
            user = User(username=username, email=email, password_hash=hash_password(secrets.token_urlsafe(32)),
                        role="owner" if not has_owner else "viewer")
            db.add(user)
            db.flush()
        identity = GitHubIdentity(user_id=user.id, github_user_id=github_user_id, login=profile["login"])

    identity.login, identity.avatar_url, identity.profile_url = profile["login"], profile.get("avatar_url"), profile.get("html_url")
    identity.email, identity.last_login_at = email.lower() if email else None, datetime.now(timezone.utc)
    db.add(identity)
    grant_value = secrets.token_urlsafe(32)
    db.add(OAuthLoginGrant(code_hash=hashlib.sha256(grant_value.encode()).hexdigest(), user_id=user.id,
                           expires_at=datetime.now(timezone.utc) + timedelta(minutes=2)))
    audit(db, user.id, "github.account_linked" if mode == "link" else "user.github_login", "user", user.id,
          github_login=identity.login)
    db.commit()
    response = RedirectResponse(f"{settings.web_url}/?github_grant={grant_value}", status_code=302)
    response.delete_cookie("rp_github_oauth", path="/api/auth/github")
    return response


@router.post("/github/redeem")
def redeem_github_login(payload: dict, db: Session = Depends(get_db)):
    grant = str(payload.get("grant", ""))
    row = db.query(OAuthLoginGrant).filter(OAuthLoginGrant.code_hash == hashlib.sha256(grant.encode()).hexdigest(),
                                           OAuthLoginGrant.used_at.is_(None)).first()
    now = datetime.now(timezone.utc)
    if not row or row.expires_at.replace(tzinfo=timezone.utc) <= now:
        raise HTTPException(status_code=401, detail="GitHub login grant is invalid or expired")
    user = db.query(User).filter(User.id == row.user_id, User.is_active.is_(True)).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    row.used_at = now
    db.commit()
    return ok({"token": create_token(user), "user": user_data(user, db)})


@router.delete("/github/link")
def unlink_github(actor: User = Depends(current_user), db: Session = Depends(get_db)):
    identity = db.query(GitHubIdentity).filter(GitHubIdentity.user_id == actor.id).first()
    if not identity:
        raise HTTPException(status_code=404, detail="GitHub account is not linked")
    db.delete(identity)
    audit(db, actor.id, "github.account_unlinked", "user", actor.id)
    db.commit()
    return ok({"unlinked": True})
