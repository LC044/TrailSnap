import hashlib
import hashlib
import json
import logging
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode

import httpx
from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from jose import JWTError, jwt
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db, init_db
from .models import (
    BackgroundJob,
    AgentToken,
    AuditEvent,
    GitHubIdentity,
    OAuthLoginGrant,
    ReleaseBatch,
    ReleaseBatchItem,
    Requirement,
    RequirementAttachment,
    RequirementFollower,
    RequirementRevision,
    ReviewDecision,
    TriageReport,
    User,
    WebhookEvent,
    utcnow,
)
from .schemas import (
    AgentTokenCreate,
    BatchCreate,
    BatchItemInput,
    BatchRead,
    BatchStatusInput,
    DeliveryStatusInput,
    GitHubIdentityRead,
    GitHubIssueLinkInput,
    LoginInput,
    RegisterInput,
    ReasonInput,
    RequirementCreate,
    RequirementRead,
    RequirementUpdate,
    ReviewInput,
    RoleUpdate,
    UserRead,
)
from .security import (
    authenticate, create_agent_token_value, create_token, current_user, hash_password, manager, optional_user, owner,
)
from .services import GitHubClient, STATUS_LABELS, audit, enqueue, requirement_snapshot, verify_webhook


logger = logging.getLogger(__name__)


def ok(data=None, msg: str = "success"):
    return {"code": 0, "msg": msg, "data": data}


def user_data(row: User, db: Session) -> dict:
    data = UserRead.model_validate(row).model_dump(mode="json")
    identity = db.query(GitHubIdentity).filter(GitHubIdentity.user_id == row.id).first()
    data["github"] = GitHubIdentityRead.model_validate(identity).model_dump(mode="json") if identity else None
    return data


def requirement_data(row: Requirement, db: Session, *, include_private: bool = False, include_contact: bool = False) -> dict:
    data = RequirementRead.model_validate(row).model_dump(mode="json")
    if not include_private:
        data["log_text"] = None
    creator = db.query(User.username).filter(User.id == row.created_by).scalar() if row.created_by else None
    data["created_by_name"] = creator or row.submitter_name or "匿名用户"
    if not include_contact:
        data["submitter_contact"] = None
    data["follower_count"] = db.query(func.count(RequirementFollower.id)).filter(
        RequirementFollower.requirement_id == row.id
    ).scalar() or 0
    report = db.query(TriageReport).filter(TriageReport.requirement_id == row.id).order_by(
        TriageReport.created_at.desc()
    ).first()
    if report:
        public_fields = {"summary", "category", "user_value", "recommendation", "confidence"}
        data["triage"] = report.report if include_private else {key: value for key, value in report.report.items() if key in public_fields}
        data["triage_provider"] = report.provider if include_private else None
    else:
        data["triage"] = None
    attachments = db.query(RequirementAttachment).filter(
        RequirementAttachment.requirement_id == row.id
    ).order_by(RequirementAttachment.created_at).all() if include_private else []
    data["attachments"] = [{
        "id": item.id, "name": item.original_name, "content_type": item.content_type,
        "size_bytes": item.size_bytes, "kind": item.kind,
        "created_at": item.created_at.isoformat(),
        "download_url": f"/api/requirements/{row.id}/attachments/{item.id}",
    } for item in attachments]
    return data


def enqueue_github_sync(db: Session, row: Requirement) -> None:
    if row.github_issue_number or (row.visibility == "public" and row.status == "candidate"):
        enqueue(db, "github_issue", row.id, f"github_issue:{row.id}:{row.status}:{secrets.token_hex(6)}")


def next_requirement_number(db: Session) -> int:
    return (db.query(func.max(Requirement.public_number)).scalar() or 0) + 1


def can_access_private_data(row: Requirement, user: User | None) -> bool:
    return bool(user and (user.id == row.created_by or user.role in {"admin", "owner"}))


def batch_data(row: ReleaseBatch, db: Session, *, include_private: bool = False) -> dict:
    data = BatchRead.model_validate(row).model_dump(mode="json")
    items = db.query(ReleaseBatchItem).filter(ReleaseBatchItem.batch_id == row.id).order_by(
        ReleaseBatchItem.priority_order, ReleaseBatchItem.created_at
    ).all()
    data["items"] = []
    for item in items:
        snapshot = item.requirement_snapshot
        if snapshot.get("visibility") == "private" and not include_private:
            snapshot = {
                "id": snapshot.get("id"),
                "title": "私密需求",
                "type": snapshot.get("type"),
                "status": snapshot.get("status"),
                "visibility": "private",
            }
        data["items"].append({
            "id": item.id,
            "requirement_id": item.requirement_id,
            "priority_order": item.priority_order,
            "delivery_status": item.delivery_status,
            "requirement_snapshot": snapshot,
        })
    return data


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="TrailSnap Requirement Platform", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(HTTPException)
async def http_error(_request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"code": exc.status_code, "msg": str(exc.detail), "data": None})


@app.exception_handler(RequestValidationError)
async def validation_error(_request: Request, exc: RequestValidationError):
    first = exc.errors()[0] if exc.errors() else {}
    field = str((first.get("loc") or ["参数"])[-1])
    message = first.get("msg") or "格式不正确"
    return JSONResponse(
        status_code=422,
        content={"code": 422, "msg": f"{field}：{message}", "data": {"errors": exc.errors()}},
    )


@app.get("/api/health")
def health(db: Session = Depends(get_db)):
    db.query(User.id).first()
    return ok({"status": "healthy", "database": "sqlite"})


@app.get("/api/auth/status")
def auth_status(db: Session = Depends(get_db)):
    return ok({"has_owner": db.query(User).filter(User.role == "owner").first() is not None,
               "allow_registration": settings.allow_registration,
               "github_oauth_enabled": bool(settings.github_oauth_client_id and settings.github_oauth_client_secret)})


@app.post("/api/auth/register")
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


@app.post("/api/auth/login")
def login(payload: LoginInput, db: Session = Depends(get_db)):
    user = authenticate(db, payload.identifier, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username/email or password")
    audit(db, user.id, "user.login", "user", user.id)
    db.commit()
    return ok({"token": create_token(user), "user": user_data(user, db)})


@app.get("/api/auth/me")
def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return ok(user_data(user, db))


@app.get("/api/auth/github/start")
def github_oauth_start(
    mode: str = Query("login", pattern="^(login|link)$"),
    user: User | None = Depends(optional_user),
):
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
        "client_id": settings.github_oauth_client_id,
        "redirect_uri": settings.github_oauth_redirect_uri,
        "scope": "read:user user:email",
        "state": state,
    })
    response = JSONResponse(ok({"authorize_url": url}))
    response.set_cookie("rp_github_oauth", state, max_age=600, httponly=True, secure=settings.web_url.startswith("https://"),
                        samesite="lax", path="/api/auth/github")
    return response


@app.get("/api/auth/github/callback")
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
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
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


@app.post("/api/auth/github/redeem")
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


@app.delete("/api/auth/github/link")
def unlink_github(actor: User = Depends(current_user), db: Session = Depends(get_db)):
    identity = db.query(GitHubIdentity).filter(GitHubIdentity.user_id == actor.id).first()
    if not identity:
        raise HTTPException(status_code=404, detail="GitHub account is not linked")
    db.delete(identity)
    audit(db, actor.id, "github.account_unlinked", "user", actor.id)
    db.commit()
    return ok({"unlinked": True})


@app.get("/api/admin/users")
def list_users(_owner: User = Depends(owner), db: Session = Depends(get_db)):
    return ok([user_data(row, db) for row in db.query(User).order_by(User.created_at).all()])


@app.patch("/api/admin/users/{user_id}/role")
def update_user_role(user_id: str, payload: RoleUpdate, actor: User = Depends(owner), db: Session = Depends(get_db)):
    row = db.query(User).filter(User.id == user_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    if row.role == "owner":
        raise HTTPException(status_code=409, detail="Owner role cannot be changed here")
    before = row.role
    row.role = payload.role
    audit(db, actor.id, "user.role_changed", "user", row.id, before=before, after=row.role)
    db.commit()
    return ok(user_data(row, db))


@app.get("/api/admin/agent-tokens")
def list_agent_tokens(actor: User = Depends(manager), db: Session = Depends(get_db)):
    query = db.query(AgentToken)
    if actor.role != "owner":
        query = query.filter(AgentToken.created_by == actor.id)
    rows = query.order_by(AgentToken.created_at.desc()).all()
    return ok([{"id": row.id, "name": row.name, "token_prefix": row.token_prefix, "scopes": row.scopes,
                "expires_at": row.expires_at.isoformat() if row.expires_at else None,
                "last_used_at": row.last_used_at.isoformat() if row.last_used_at else None,
                "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None,
                "created_at": row.created_at.isoformat()} for row in rows])


@app.post("/api/admin/agent-tokens")
def create_agent_token(payload: AgentTokenCreate, actor: User = Depends(manager), db: Session = Depends(get_db)):
    value, prefix, token_hash = create_agent_token_value()
    expires_at = datetime.now(timezone.utc) + timedelta(days=payload.expires_in_days) if payload.expires_in_days else None
    row = AgentToken(name=payload.name, token_prefix=prefix, token_hash=token_hash,
                     scopes=sorted(set(payload.scopes)), created_by=actor.id, expires_at=expires_at)
    db.add(row)
    db.flush()
    audit(db, actor.id, "agent_token.created", "agent_token", row.id, name=row.name, scopes=row.scopes)
    db.commit()
    return ok({"id": row.id, "name": row.name, "token": value, "token_prefix": prefix,
               "scopes": row.scopes, "expires_at": expires_at.isoformat() if expires_at else None},
              "令牌仅显示一次，请立即保存")


@app.delete("/api/admin/agent-tokens/{token_id}")
def revoke_agent_token(token_id: str, actor: User = Depends(manager), db: Session = Depends(get_db)):
    query = db.query(AgentToken).filter(AgentToken.id == token_id)
    if actor.role != "owner":
        query = query.filter(AgentToken.created_by == actor.id)
    row = query.first()
    if not row:
        raise HTTPException(status_code=404, detail="Agent token not found")
    row.revoked_at = datetime.now(timezone.utc)
    audit(db, actor.id, "agent_token.revoked", "agent_token", row.id)
    db.commit()
    return ok({"revoked": True})


@app.post("/api/requirements")
def create_requirement(payload: RequirementCreate, user: User | None = Depends(optional_user), db: Session = Depends(get_db)):
    is_manager = bool(user and user.role in {"admin", "owner"})
    if not is_manager:
        since = datetime.now(timezone.utc) - timedelta(hours=1)
        manager_ids = db.query(User.id).filter(User.role.in_({"admin", "owner"}))
        recent = db.query(func.count(Requirement.id)).filter(
            Requirement.created_at >= since,
            or_(Requirement.created_by.is_(None), Requirement.created_by.notin_(manager_ids)),
        ).scalar() or 0
        if recent >= settings.non_admin_hourly_submission_limit:
            raise HTTPException(status_code=429, detail="所有非管理员用户每小时最多提交 20 条需求，请稍后再试")
    values = payload.model_dump()
    if user:
        values["submitter_name"] = None
        values["submitter_contact"] = None
    else:
        values["visibility"] = "public"
        values["submitter_name"] = (values.get("submitter_name") or "").strip() or None
        values["submitter_contact"] = (values.get("submitter_contact") or "").strip() or None
    upload_token = secrets.token_urlsafe(32) if not user else None
    row = Requirement(
        public_number=next_requirement_number(db), created_by=user.id if user else None,
        anonymous_upload_token_hash=hashlib.sha256(upload_token.encode()).hexdigest() if upload_token else None,
        **values,
    )
    db.add(row)
    db.flush()
    if user:
        db.add(RequirementFollower(requirement_id=row.id, user_id=user.id))
    audit(db, user.id if user else None, "requirement.created", "requirement", row.id, type=row.type, status=row.status)
    enqueue(db, "triage", row.id, f"triage:{row.id}:v{row.version}")
    db.commit()
    db.refresh(row)
    data = requirement_data(row, db, include_private=bool(user), include_contact=is_manager)
    if upload_token:
        data["upload_token"] = upload_token
    return ok(data, "submitted")


ALLOWED_ATTACHMENT_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".txt", ".log", ".json", ".pdf"}
IMAGE_ATTACHMENT_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


@app.post("/api/requirements/{requirement_id}/attachments")
async def upload_requirement_attachment(
    requirement_id: str, file: UploadFile = File(...), user: User | None = Depends(optional_user),
    x_requirement_upload_token: str | None = Header(default=None), db: Session = Depends(get_db)
):
    row = db.query(Requirement).filter(Requirement.id == requirement_id, Requirement.deleted_at.is_(None)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Requirement not found")
    anonymous_token_ok = bool(
        not user and x_requirement_upload_token and row.anonymous_upload_token_hash
        and secrets.compare_digest(
            hashlib.sha256(x_requirement_upload_token.encode()).hexdigest(), row.anonymous_upload_token_hash
        )
    )
    if not can_access_private_data(row, user) and not anonymous_token_ok:
        raise HTTPException(status_code=403, detail="Not allowed")
    count = db.query(func.count(RequirementAttachment.id)).filter(
        RequirementAttachment.requirement_id == row.id
    ).scalar() or 0
    if count >= settings.max_attachments_per_requirement:
        raise HTTPException(status_code=409, detail=f"每条需求最多上传 {settings.max_attachments_per_requirement} 个附件")
    original_name = Path(file.filename or "attachment").name[:255]
    suffix = Path(original_name).suffix.lower()
    if suffix not in ALLOWED_ATTACHMENT_EXTENSIONS:
        raise HTTPException(status_code=415, detail="仅支持 PNG、JPG、WebP、TXT、LOG、JSON 和 PDF 文件")
    upload_dir = Path(settings.upload_dir).resolve()
    upload_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{secrets.token_hex(16)}{suffix}"
    target = upload_dir / stored_name
    size = 0
    try:
        with target.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > settings.max_attachment_bytes:
                    raise HTTPException(status_code=413, detail="单个附件不能超过 5MB")
                output.write(chunk)
        if size == 0:
            raise HTTPException(status_code=422, detail="附件不能为空")
    except Exception:
        target.unlink(missing_ok=True)
        raise
    attachment = RequirementAttachment(
        requirement_id=row.id, uploaded_by=user.id if user else None, original_name=original_name, stored_name=stored_name,
        content_type=(file.content_type or "application/octet-stream")[:100], size_bytes=size,
        kind="image" if suffix in IMAGE_ATTACHMENT_EXTENSIONS else "file",
    )
    db.add(attachment)
    db.flush()
    audit(db, user.id if user else None, "requirement.attachment_uploaded", "requirement", row.id,
          attachment_id=attachment.id, name=original_name, size_bytes=size)
    db.commit()
    return ok({"id": attachment.id, "name": original_name, "content_type": attachment.content_type,
               "size_bytes": size, "kind": attachment.kind,
               "download_url": f"/api/requirements/{row.id}/attachments/{attachment.id}"})


@app.get("/api/requirements/{requirement_id}/attachments/{attachment_id}")
def download_requirement_attachment(
    requirement_id: str, attachment_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    row = db.query(Requirement).filter(Requirement.id == requirement_id, Requirement.deleted_at.is_(None)).first()
    attachment = db.query(RequirementAttachment).filter(
        RequirementAttachment.id == attachment_id, RequirementAttachment.requirement_id == requirement_id
    ).first()
    if not row or not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")
    if not can_access_private_data(row, user):
        raise HTTPException(status_code=403, detail="Not allowed")
    path = Path(settings.upload_dir).resolve() / attachment.stored_name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Attachment file not found")
    return FileResponse(path, media_type=attachment.content_type, filename=attachment.original_name)


@app.get("/api/requirements")
def list_requirements(
    status: str | None = None,
    type: str | None = None,
    q: str | None = Query(default=None, max_length=100),
    mine: bool = False,
    limit: int = Query(50, ge=1, le=100),
    skip: int = Query(0, ge=0),
    include_deleted: bool = False,
    user: User | None = Depends(optional_user),
    db: Session = Depends(get_db),
):
    query = db.query(Requirement)
    is_manager = bool(user and user.role in {"admin", "owner"})
    if include_deleted:
        if not is_manager:
            raise HTTPException(status_code=403, detail="Manager role required")
    else:
        query = query.filter(Requirement.deleted_at.is_(None))
    if mine:
        if not user:
            raise HTTPException(status_code=401, detail="Authentication required")
        query = query.filter(Requirement.created_by == user.id)
    elif not is_manager:
        if user:
            query = query.filter(or_(Requirement.visibility == "public", Requirement.created_by == user.id))
        else:
            query = query.filter(Requirement.visibility == "public")
    if status:
        query = query.filter(Requirement.status == status)
    if type:
        query = query.filter(Requirement.type == type)
    if q:
        search = q.strip()
        pattern = f"%{search}%"
        number_text = search.upper().removeprefix("REQ-").lstrip("0") or "0"
        conditions = [Requirement.title.ilike(pattern), Requirement.description.ilike(pattern)]
        if number_text.isdigit():
            conditions.append(Requirement.public_number == int(number_text))
        query = query.filter(or_(*conditions))
    rows = query.order_by(Requirement.created_at.desc()).offset(skip).limit(limit).all()
    return ok([requirement_data(
        row, db,
        include_private=is_manager or bool(user and row.created_by == user.id),
        include_contact=is_manager,
    ) for row in rows])


@app.get("/api/requirements/number/{public_number}")
def get_requirement_by_number(public_number: int, user: User | None = Depends(optional_user), db: Session = Depends(get_db)):
    row = db.query(Requirement).filter(
        Requirement.public_number == public_number, Requirement.deleted_at.is_(None)
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Requirement not found")
    allowed = row.visibility == "public" or bool(user and (user.id == row.created_by or user.role in {"admin", "owner"}))
    if not allowed:
        raise HTTPException(status_code=404, detail="Requirement not found")
    is_manager = bool(user and user.role in {"admin", "owner"})
    return ok(requirement_data(row, db, include_private=is_manager or bool(user and user.id == row.created_by), include_contact=is_manager))


@app.get("/api/requirements/{requirement_id}/history")
def requirement_history(requirement_id: str, user: User | None = Depends(optional_user), db: Session = Depends(get_db)):
    row = db.query(Requirement).filter(Requirement.id == requirement_id, Requirement.deleted_at.is_(None)).first()
    if not row or (row.visibility != "public" and not user) or (
        row.visibility != "public" and user and user.id != row.created_by and user.role not in {"admin", "owner"}
    ):
        raise HTTPException(status_code=404, detail="Requirement not found")
    allowed_actions = {
        "requirement.created", "requirement.updated", "requirement.status_changed", "requirement.withdrawn",
        "requirement.candidate", "requirement.needs_information", "requirement.rejected", "requirement.deferred",
        "requirement.duplicate", "requirement.closed", "triage.queued", "triage.completed",
    }
    events = db.query(AuditEvent).filter(
        AuditEvent.object_type == "requirement", AuditEvent.object_id == row.id,
        AuditEvent.action.in_(allowed_actions),
    ).order_by(AuditEvent.created_at).all()
    result = []
    for event in events:
        actor_name = db.query(User.username).filter(User.id == event.actor_id).scalar() if event.actor_id else None
        details = event.details or {}
        result.append({
            "id": event.id, "action": event.action, "actor_name": actor_name or "系统",
            "before": details.get("before"), "after": details.get("after") or details.get("status"),
            "reason": details.get("reason"), "created_at": event.created_at.isoformat(),
        })
    return ok(result)


@app.get("/api/requirements/{requirement_id}")
def get_requirement(requirement_id: str, user: User | None = Depends(optional_user), db: Session = Depends(get_db)):
    row = db.query(Requirement).filter(Requirement.id == requirement_id, Requirement.deleted_at.is_(None)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Requirement not found")
    allowed = row.visibility == "public" or bool(user and (user.id == row.created_by or user.role in {"admin", "owner"}))
    if not allowed:
        raise HTTPException(status_code=404, detail="Requirement not found")
    include_private = bool(user and (user.id == row.created_by or user.role in {"admin", "owner"}))
    return ok(requirement_data(row, db, include_private=include_private, include_contact=bool(user and user.role in {"admin", "owner"})))


@app.patch("/api/requirements/{requirement_id}")
def update_requirement(
    requirement_id: str, payload: RequirementUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    row = db.query(Requirement).filter(Requirement.id == requirement_id, Requirement.deleted_at.is_(None)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Requirement not found")
    if row.created_by != user.id and user.role not in {"admin", "owner"}:
        raise HTTPException(status_code=403, detail="Not allowed")
    if row.status not in {"submitted", "needs_information", "pending_review"} and user.role == "viewer":
        raise HTTPException(status_code=409, detail="Requirement can no longer be edited")
    db.add(RequirementRevision(requirement_id=row.id, editor_id=user.id, snapshot=requirement_snapshot(row), reason="updated"))
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    row.version += 1
    if row.status == "needs_information":
        before = row.status
        row.status = "submitted"
        audit(db, user.id, "requirement.status_changed", "requirement", row.id, before=before, after=row.status)
    enqueue_github_sync(db, row)
    enqueue(db, "triage", row.id, f"triage:{row.id}:v{row.version}")
    audit(db, user.id, "requirement.updated", "requirement", row.id, version=row.version)
    db.commit()
    return ok(requirement_data(row, db, include_private=True, include_contact=user.role in {"admin", "owner"}))


@app.post("/api/requirements/{requirement_id}/withdraw")
def withdraw_requirement(requirement_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    row = db.query(Requirement).filter(Requirement.id == requirement_id, Requirement.created_by == user.id,
                                       Requirement.deleted_at.is_(None)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Requirement not found")
    if row.status in {"scheduled", "developing", "testing", "release_ready", "released"}:
        raise HTTPException(status_code=409, detail="Scheduled requirement cannot be withdrawn")
    before = row.status
    row.status = "withdrawn"
    enqueue_github_sync(db, row)
    audit(db, user.id, "requirement.withdrawn", "requirement", row.id, before=before, after=row.status)
    db.commit()
    return ok(requirement_data(row, db, include_private=True))


@app.post("/api/requirements/{requirement_id}/follow")
def follow_requirement(requirement_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    requirement = db.query(Requirement).filter(Requirement.id == requirement_id, Requirement.deleted_at.is_(None)).first()
    if not requirement or (
        requirement.visibility == "private"
        and requirement.created_by != user.id
        and user.role not in {"admin", "owner"}
    ):
        raise HTTPException(status_code=404, detail="Requirement not found")
    row = db.query(RequirementFollower).filter(
        RequirementFollower.requirement_id == requirement_id, RequirementFollower.user_id == user.id
    ).first()
    if row:
        db.delete(row)
        following = False
    else:
        db.add(RequirementFollower(requirement_id=requirement_id, user_id=user.id))
        following = True
    db.commit()
    return ok({"following": following})


@app.post("/api/requirements/{requirement_id}/triage")
def queue_triage(requirement_id: str, actor: User = Depends(manager), db: Session = Depends(get_db)):
    row = db.query(Requirement).filter(Requirement.id == requirement_id, Requirement.deleted_at.is_(None)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Requirement not found")
    key = f"triage:{row.id}:v{row.version}:manual:{int(datetime.now().timestamp()) // 60}"
    job = enqueue(db, "triage", row.id, key)
    before = row.status
    row.status = "triaging"
    enqueue_github_sync(db, row)
    audit(db, actor.id, "triage.queued", "requirement", row.id, job_id=job.id, before=before, after=row.status)
    db.commit()
    return ok({"job_id": job.id})


@app.post("/api/requirements/{requirement_id}/review")
def review_requirement(requirement_id: str, payload: ReviewInput, actor: User = Depends(manager), db: Session = Depends(get_db)):
    row = db.query(Requirement).filter(Requirement.id == requirement_id, Requirement.deleted_at.is_(None)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Requirement not found")
    status_by_action = {
        "candidate": "candidate", "needs_information": "needs_information", "rejected": "rejected",
        "deferred": "deferred", "duplicate": "duplicate", "close": "closed",
    }
    if payload.action == "duplicate":
        target = db.query(Requirement).filter(Requirement.id == payload.duplicate_of_id, Requirement.deleted_at.is_(None)).first()
        if not target or target.id == row.id:
            raise HTTPException(status_code=409, detail="Valid duplicate target is required")
        row.duplicate_of_id = target.id
        followers = db.query(RequirementFollower).filter(RequirementFollower.requirement_id == row.id).all()
        for follower in followers:
            exists = db.query(RequirementFollower).filter(
                RequirementFollower.requirement_id == target.id, RequirementFollower.user_id == follower.user_id
            ).first()
            if not exists:
                db.add(RequirementFollower(requirement_id=target.id, user_id=follower.user_id))
    before = row.status
    row.status = status_by_action[payload.action]
    row.review_reason = payload.reason
    row.priority = payload.priority
    row.risk_level = payload.risk_level
    db.add(ReviewDecision(
        requirement_id=row.id, reviewer_id=actor.id, action=payload.action, reason=payload.reason,
        metadata_json={"priority": payload.priority, "risk_level": payload.risk_level, "duplicate_of_id": payload.duplicate_of_id},
    ))
    enqueue_github_sync(db, row)
    audit(db, actor.id, f"requirement.{payload.action}", "requirement", row.id,
          before=before, after=row.status, reason=payload.reason)
    db.commit()
    return ok(requirement_data(row, db, include_private=True))


@app.post("/api/requirements/{requirement_id}/close")
def close_requirement(requirement_id: str, payload: ReasonInput, actor: User = Depends(manager), db: Session = Depends(get_db)):
    row = db.query(Requirement).filter(Requirement.id == requirement_id, Requirement.deleted_at.is_(None)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Requirement not found")
    before = row.status
    row.status, row.review_reason = "closed", payload.reason
    enqueue_github_sync(db, row)
    db.add(ReviewDecision(requirement_id=row.id, reviewer_id=actor.id, action="close", reason=payload.reason))
    audit(db, actor.id, "requirement.closed", "requirement", row.id,
          before=before, after=row.status, reason=payload.reason)
    db.commit()
    return ok(requirement_data(row, db, include_private=True))


@app.delete("/api/requirements/{requirement_id}")
def delete_requirement(requirement_id: str, payload: ReasonInput, actor: User = Depends(manager), db: Session = Depends(get_db)):
    row = db.query(Requirement).filter(Requirement.id == requirement_id, Requirement.deleted_at.is_(None)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Requirement not found")
    active_batch = db.query(ReleaseBatchItem).join(ReleaseBatch, ReleaseBatch.id == ReleaseBatchItem.batch_id).filter(
        ReleaseBatchItem.requirement_id == row.id,
        ReleaseBatch.status.notin_({"completed", "cancelled"}),
        ReleaseBatchItem.delivery_status != "removed",
    ).first()
    if active_batch:
        raise HTTPException(status_code=409, detail="Remove requirement from its active version before deleting")
    row.deleted_at, row.deleted_by, row.delete_reason = datetime.now(timezone.utc), actor.id, payload.reason
    audit(db, actor.id, "requirement.deleted", "requirement", row.id, reason=payload.reason)
    db.commit()
    return ok({"deleted": True, "id": row.id})


@app.post("/api/requirements/{requirement_id}/restore")
def restore_requirement(requirement_id: str, actor: User = Depends(manager), db: Session = Depends(get_db)):
    row = db.query(Requirement).filter(Requirement.id == requirement_id, Requirement.deleted_at.is_not(None)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Deleted requirement not found")
    row.deleted_at, row.deleted_by, row.delete_reason = None, None, None
    audit(db, actor.id, "requirement.restored", "requirement", row.id)
    db.commit()
    return ok(requirement_data(row, db, include_private=True))


@app.post("/api/requirements/{requirement_id}/github/create")
def create_requirement_github_issue(requirement_id: str, actor: User = Depends(manager), db: Session = Depends(get_db)):
    row = db.query(Requirement).filter(Requirement.id == requirement_id, Requirement.deleted_at.is_(None)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Requirement not found")
    if row.github_issue_number:
        raise HTTPException(status_code=409, detail="Requirement already has a GitHub issue")
    try:
        data = GitHubClient().create_issue(row)
    except (RuntimeError, httpx.HTTPError) as exc:
        raise HTTPException(status_code=502, detail=f"GitHub issue creation failed: {exc}") from exc
    row.github_issue_number, row.github_issue_url, row.github_state = data["number"], data["html_url"], data["state"]
    audit(db, actor.id, "github.issue.created", "requirement", row.id, issue_number=data["number"])
    db.commit()
    return ok(requirement_data(row, db, include_private=True))


@app.post("/api/admin/github/issues/sync")
def import_github_issues(actor: User = Depends(manager), db: Session = Depends(get_db)):
    try:
        issues = GitHubClient().list_issues()
    except (RuntimeError, httpx.HTTPError) as exc:
        raise HTTPException(status_code=502, detail=f"GitHub Issue 同步失败：{exc}") from exc
    status_by_label = {label_name.lower(): status for status, (label_name, _color, _desc) in STATUS_LABELS.items()}
    created = updated = skipped = 0
    for issue in issues:
        number = issue.get("number")
        if not number:
            skipped += 1
            continue
        label_names = [label.get("name", "") if isinstance(label, dict) else str(label) for label in issue.get("labels", [])]
        managed_status = next((status_by_label[name.lower()] for name in label_names if name.lower() in status_by_label), None)
        issue_status = managed_status or ("closed" if issue.get("state") == "closed" else "submitted")
        kind = "bug" if any(name.lower() == "bug" for name in label_names) else (
            "feature" if any(name.lower() in {"enhancement", "feature"} for name in label_names) else "improvement"
        )
        row = db.query(Requirement).filter(Requirement.github_issue_number == number).first()
        if row:
            row.github_issue_url = issue.get("html_url")
            row.github_state = issue.get("state")
            if row.source == "github":
                row.title = (issue.get("title") or f"GitHub Issue #{number}")[:160]
                row.description = ((issue.get("body") or "GitHub Issue 未提供正文").strip() or "GitHub Issue 未提供正文")[:8000]
                row.type = kind
                row.status = issue_status
            updated += 1
            continue
        row = Requirement(
            public_number=next_requirement_number(db),
            type=kind, title=(issue.get("title") or f"GitHub Issue #{number}")[:160],
            description=((issue.get("body") or "GitHub Issue 未提供正文").strip() or "GitHub Issue 未提供正文")[:8000],
            severity="medium", visibility="public", status=issue_status, source="github", created_by=actor.id,
            github_issue_number=number, github_issue_url=issue.get("html_url"), github_state=issue.get("state"),
        )
        db.add(row)
        db.flush()
        db.add(RequirementFollower(requirement_id=row.id, user_id=actor.id))
        if issue_status == "submitted":
            enqueue(db, "triage", row.id, f"triage:{row.id}:v{row.version}")
        audit(db, actor.id, "github.issue.imported", "requirement", row.id, issue_number=number)
        created += 1
    audit(db, actor.id, "github.issues.synchronized", "github_repository", settings.github_repo,
          created=created, updated=updated, skipped=skipped, total=len(issues))
    db.commit()
    return ok({"created": created, "updated": updated, "skipped": skipped, "total": len(issues)})


@app.post("/api/requirements/{requirement_id}/github/link")
def link_requirement_github_issue(requirement_id: str, payload: GitHubIssueLinkInput, actor: User = Depends(manager), db: Session = Depends(get_db)):
    row = db.query(Requirement).filter(Requirement.id == requirement_id, Requirement.deleted_at.is_(None)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Requirement not found")
    other = db.query(Requirement).filter(Requirement.github_issue_number == payload.issue_number, Requirement.id != row.id).first()
    if other:
        raise HTTPException(status_code=409, detail="GitHub issue is already linked to another requirement")
    try:
        data = GitHubClient().get_issue(payload.issue_number)
    except (RuntimeError, httpx.HTTPError) as exc:
        raise HTTPException(status_code=502, detail=f"GitHub issue lookup failed: {exc}") from exc
    row.github_issue_number, row.github_issue_url, row.github_state = data["number"], data["html_url"], data["state"]
    enqueue_github_sync(db, row)
    audit(db, actor.id, "github.issue.linked", "requirement", row.id, issue_number=data["number"])
    db.commit()
    return ok(requirement_data(row, db, include_private=True))


@app.delete("/api/requirements/{requirement_id}/github/link")
def unlink_requirement_github_issue(requirement_id: str, actor: User = Depends(manager), db: Session = Depends(get_db)):
    row = db.query(Requirement).filter(Requirement.id == requirement_id, Requirement.deleted_at.is_(None)).first()
    if not row or not row.github_issue_number:
        raise HTTPException(status_code=404, detail="Linked GitHub issue not found")
    issue_number = row.github_issue_number
    row.github_issue_number, row.github_issue_url, row.github_state = None, None, None
    audit(db, actor.id, "github.issue.unlinked", "requirement", row.id, issue_number=issue_number)
    db.commit()
    return ok(requirement_data(row, db, include_private=True))


@app.post("/api/requirements/{requirement_id}/github/close")
def close_requirement_github_issue(requirement_id: str, payload: ReasonInput, actor: User = Depends(manager), db: Session = Depends(get_db)):
    row = db.query(Requirement).filter(Requirement.id == requirement_id, Requirement.deleted_at.is_(None)).first()
    if not row or not row.github_issue_number:
        raise HTTPException(status_code=404, detail="Linked GitHub issue not found")
    try:
        data = GitHubClient().update_issue_state(row.github_issue_number, "closed")
    except (RuntimeError, httpx.HTTPError) as exc:
        raise HTTPException(status_code=502, detail=f"GitHub issue close failed: {exc}") from exc
    row.github_state, row.status, row.review_reason = data["state"], "closed", payload.reason
    enqueue_github_sync(db, row)
    audit(db, actor.id, "github.issue.closed", "requirement", row.id,
          issue_number=row.github_issue_number, reason=payload.reason)
    db.commit()
    return ok(requirement_data(row, db, include_private=True))


@app.get("/api/versions")
def list_batches(user: User | None = Depends(optional_user), db: Session = Depends(get_db)):
    include_private = bool(user and user.role in {"admin", "owner"})
    return ok([
        batch_data(row, db, include_private=include_private)
        for row in db.query(ReleaseBatch).order_by(ReleaseBatch.created_at.desc()).all()
    ])


@app.post("/api/versions")
def create_batch(payload: BatchCreate, actor: User = Depends(manager), db: Session = Depends(get_db)):
    row = ReleaseBatch(created_by=actor.id, **payload.model_dump())
    db.add(row)
    try:
        db.flush()
        audit(db, actor.id, "release_batch.created", "release_batch", row.id, version_name=row.version_name)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Version name already exists") from exc
    return ok(batch_data(row, db, include_private=True))


@app.get("/api/versions/{batch_id}")
def get_batch(batch_id: str, user: User | None = Depends(optional_user), db: Session = Depends(get_db)):
    row = db.query(ReleaseBatch).filter(ReleaseBatch.id == batch_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Version batch not found")
    return ok(batch_data(row, db, include_private=bool(user and user.role in {"admin", "owner"})))


@app.post("/api/versions/{batch_id}/items")
def add_batch_item(batch_id: str, payload: BatchItemInput, actor: User = Depends(manager), db: Session = Depends(get_db)):
    batch = db.query(ReleaseBatch).filter(ReleaseBatch.id == batch_id).first()
    requirement = db.query(Requirement).filter(Requirement.id == payload.requirement_id, Requirement.deleted_at.is_(None)).first()
    if not batch or not requirement:
        raise HTTPException(status_code=404, detail="Batch or requirement not found")
    if batch.status not in {"planning", "candidate_selection"}:
        raise HTTPException(status_code=409, detail="Version scope is locked")
    if requirement.status not in {"candidate", "scheduled"}:
        raise HTTPException(status_code=409, detail="Only candidate requirements can be scheduled")
    risk_rank = {"low": 1, "medium": 2, "high": 3, "critical": 4}
    if risk_rank.get(requirement.risk_level, 4) > risk_rank.get(batch.max_risk_level, 3):
        raise HTTPException(status_code=409, detail="Requirement risk exceeds the version batch limit")
    row = ReleaseBatchItem(
        batch_id=batch.id, requirement_id=requirement.id, priority_order=payload.priority_order,
        requirement_snapshot=requirement_snapshot(requirement),
    )
    db.add(row)
    batch.status = "candidate_selection"
    try:
        db.flush()
        audit(db, actor.id, "release_batch.item_added", "release_batch", batch.id, requirement_id=requirement.id)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Requirement is already in this batch") from exc
    return ok(batch_data(batch, db, include_private=True))


@app.delete("/api/versions/{batch_id}/items/{item_id}")
def remove_batch_item(batch_id: str, item_id: str, actor: User = Depends(manager), db: Session = Depends(get_db)):
    batch = db.query(ReleaseBatch).filter(ReleaseBatch.id == batch_id).first()
    item = db.query(ReleaseBatchItem).filter(ReleaseBatchItem.id == item_id, ReleaseBatchItem.batch_id == batch_id).first()
    if not batch or not item:
        raise HTTPException(status_code=404, detail="Batch item not found")
    if batch.status not in {"planning", "candidate_selection"}:
        raise HTTPException(status_code=409, detail="Version scope is locked")
    audit(db, actor.id, "release_batch.item_removed", "release_batch", batch.id, requirement_id=item.requirement_id)
    db.delete(item)
    db.commit()
    return ok({"removed": True})


@app.post("/api/versions/{batch_id}/lock")
def lock_batch(batch_id: str, actor: User = Depends(manager), db: Session = Depends(get_db)):
    batch = db.query(ReleaseBatch).filter(ReleaseBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Version batch not found")
    items = db.query(ReleaseBatchItem).filter(ReleaseBatchItem.batch_id == batch.id).all()
    if not items:
        raise HTTPException(status_code=409, detail="Version batch has no requirements")
    if batch.status not in {"planning", "candidate_selection"}:
        raise HTTPException(status_code=409, detail="Version scope is already locked")
    batch.status = "scope_locked"
    batch.locked_at = utcnow()
    for item in items:
        requirement = db.query(Requirement).filter(Requirement.id == item.requirement_id).first()
        if requirement:
            item.requirement_snapshot = requirement_snapshot(requirement)
            before = requirement.status
            requirement.status = "scheduled"
            enqueue_github_sync(db, requirement)
            audit(db, actor.id, "requirement.status_changed", "requirement", requirement.id,
                  before=before, after=requirement.status, reason=f"加入版本 {batch.version_name}")
    enqueue(db, "github_milestone", batch.id, f"github_milestone:{batch.id}")
    audit(db, actor.id, "release_batch.locked", "release_batch", batch.id, count=len(items))
    db.commit()
    return ok(batch_data(batch, db, include_private=True))


@app.patch("/api/versions/{batch_id}/status")
def update_batch_status(batch_id: str, payload: BatchStatusInput, actor: User = Depends(manager), db: Session = Depends(get_db)):
    batch = db.query(ReleaseBatch).filter(ReleaseBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Version batch not found")
    before = batch.status
    allowed_transitions = {
        "planning": {"cancelled"},
        "candidate_selection": {"cancelled"},
        "scope_locked": {"developing", "blocked", "paused", "cancelled"},
        "developing": {"testing", "blocked", "paused", "cancelled"},
        "testing": {"developing", "release_ready", "blocked", "paused", "cancelled"},
        "release_ready": {"testing", "published", "blocked", "paused", "cancelled"},
        "published": {"completed"},
        "blocked": {"developing", "testing", "release_ready", "paused", "cancelled"},
        "paused": {"developing", "testing", "release_ready", "blocked", "cancelled"},
        "completed": set(),
        "cancelled": set(),
    }
    if payload.status != before and payload.status not in allowed_transitions.get(before, set()):
        raise HTTPException(status_code=409, detail=f"Invalid version transition: {before} -> {payload.status}")
    if payload.status in {"completed", "cancelled"} and actor.role != "owner":
        raise HTTPException(status_code=403, detail="Only the owner can complete or cancel a version")
    if payload.status == "published":
        unfinished = db.query(func.count(ReleaseBatchItem.id)).filter(
            ReleaseBatchItem.batch_id == batch.id,
            ReleaseBatchItem.delivery_status.notin_({"completed", "removed"}),
        ).scalar() or 0
        if unfinished:
            raise HTTPException(status_code=409, detail="All included requirements must be completed before publishing")
    batch.status = payload.status
    requirement_status = {
        "developing": "developing",
        "testing": "testing",
        "release_ready": "release_ready",
        "published": "released",
        "completed": "released",
    }.get(payload.status)
    if requirement_status:
        items = db.query(ReleaseBatchItem).filter(ReleaseBatchItem.batch_id == batch.id).all()
        for item in items:
            requirement = db.query(Requirement).filter(Requirement.id == item.requirement_id).first()
            if requirement and (requirement_status != "released" or item.delivery_status == "completed"):
                before_status = requirement.status
                requirement.status = requirement_status
                enqueue_github_sync(db, requirement)
                audit(db, actor.id, "requirement.status_changed", "requirement", requirement.id,
                      before=before_status, after=requirement.status, reason=payload.reason)
    audit(db, actor.id, "release_batch.status_changed", "release_batch", batch.id, before=before, after=payload.status, reason=payload.reason)
    db.commit()
    return ok(batch_data(batch, db, include_private=True))


@app.patch("/api/versions/{batch_id}/items/{item_id}/status")
def update_delivery_status(
    batch_id: str, item_id: str, payload: DeliveryStatusInput, actor: User = Depends(manager), db: Session = Depends(get_db)
):
    batch = db.query(ReleaseBatch).filter(ReleaseBatch.id == batch_id).first()
    item = db.query(ReleaseBatchItem).filter(ReleaseBatchItem.id == item_id, ReleaseBatchItem.batch_id == batch_id).first()
    if not batch or not item:
        raise HTTPException(status_code=404, detail="Batch item not found")
    if batch.status in {"planning", "candidate_selection"}:
        raise HTTPException(status_code=409, detail="Lock the version scope before updating delivery status")
    if batch.status in {"published", "completed", "cancelled"}:
        raise HTTPException(status_code=409, detail="Version delivery status is no longer editable")
    item.delivery_status = payload.status
    requirement = db.query(Requirement).filter(Requirement.id == item.requirement_id).first()
    mapping = {"developing": "developing", "pr_open": "developing", "testing": "testing", "completed": "release_ready"}
    if requirement and payload.status in mapping:
        before_status = requirement.status
        requirement.status = mapping[payload.status]
        enqueue_github_sync(db, requirement)
        audit(db, actor.id, "requirement.status_changed", "requirement", requirement.id,
              before=before_status, after=requirement.status, reason=f"版本交付状态：{payload.status}")
    audit(db, actor.id, "release_batch.delivery_status", "release_batch", batch_id, item_id=item.id, status=payload.status)
    db.commit()
    return ok({"id": item.id, "delivery_status": item.delivery_status})


@app.get("/api/admin/jobs")
def list_jobs(_actor: User = Depends(manager), db: Session = Depends(get_db)):
    rows = db.query(BackgroundJob).order_by(BackgroundJob.created_at.desc()).limit(100).all()
    return ok([{
        "id": row.id, "job_type": row.job_type, "object_id": row.object_id, "status": row.status,
        "attempts": row.attempts, "last_error": row.last_error, "created_at": row.created_at.isoformat(),
    } for row in rows])


@app.get("/api/admin/dashboard")
def dashboard(_actor: User = Depends(manager), db: Session = Depends(get_db)):
    base = db.query(Requirement).filter(Requirement.deleted_at.is_(None))
    status_rows = db.query(Requirement.status, func.count(Requirement.id)).filter(
        Requirement.deleted_at.is_(None)
    ).group_by(Requirement.status).all()
    type_rows = db.query(Requirement.type, func.count(Requirement.id)).filter(
        Requirement.deleted_at.is_(None)
    ).group_by(Requirement.type).all()
    since = datetime.now(timezone.utc) - timedelta(days=7)
    return ok({
        "total": base.count(),
        "new_last_7_days": base.filter(Requirement.created_at >= since).count(),
        "pending_review": base.filter(Requirement.status.in_({"submitted", "triaging", "pending_review"})).count(),
        "in_progress": base.filter(Requirement.status.in_({"scheduled", "developing", "testing", "release_ready"})).count(),
        "github_linked": base.filter(Requirement.github_issue_number.is_not(None)).count(),
        "anonymous": base.filter(Requirement.created_by.is_(None)).count(),
        "by_status": {status: count for status, count in status_rows},
        "by_type": {kind: count for kind, count in type_rows},
    })


@app.post("/api/hooks/github")
async def github_webhook(
    request: Request,
    x_hub_signature_256: str | None = Header(default=None),
    x_github_delivery: str | None = Header(default=None),
    x_github_event: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    body = await request.body()
    if not verify_webhook(body, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")
    delivery_id = x_github_delivery or ""
    if not delivery_id:
        raise HTTPException(status_code=400, detail="Missing delivery id")
    if db.query(WebhookEvent).filter(WebhookEvent.delivery_id == delivery_id).first():
        return ok({"duplicate": True})
    payload = json.loads(body)
    event = WebhookEvent(delivery_id=delivery_id, event_type=x_github_event or "unknown", payload=payload)
    db.add(event)
    if x_github_event == "issues":
        issue = payload.get("issue") or {}
        row = db.query(Requirement).filter(Requirement.github_issue_number == issue.get("number")).first()
        if row:
            row.github_state = issue.get("state")
    event.processed = True
    db.commit()
    return ok({"accepted": True})
