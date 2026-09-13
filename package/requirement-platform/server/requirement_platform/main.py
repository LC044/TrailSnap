import hashlib
import asyncio
import json
import logging
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode

import httpx
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from jose import JWTError, jwt
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import settings
from .db import SessionLocal, get_db, init_db
from .models import (
    AIConnection,
    AIModel,
    AITaskRoute,
    AgentRun,
    AgentRunQuestion,
    BackgroundJob,
    AgentToken,
    AuditEvent,
    ClarificationQuestion,
    DeliveryTask,
    DomainEvent,
    GitHubIdentity,
    OAuthLoginGrant,
    ReleaseBatch,
    ReleaseBatchItem,
    Requirement,
    RequirementAttachment,
    RequirementFollower,
    RequirementRevision,
    RequirementSpec,
    ReviewDecision,
    PullRequestLink,
    TriageReport,
    User,
    WebhookEvent,
    utcnow,
)
from .schemas import (
    AIConnectionCreate,
    AIConnectionTestInput,
    AIConnectionUpdate,
    AIModelCreate,
    AIModelUpdate,
    AITaskRouteUpdate,
    AgentClaimInput,
    ArtifactInput,
    AgentTokenCreate,
    BatchCreate,
    BatchItemInput,
    BatchRead,
    BatchStatusInput,
    BatchUpdate,
    ClarificationAnswerInput,
    DeliveryTaskCreate,
    DeliveryStatusInput,
    GitHubIdentityRead,
    GitHubIssueLinkInput,
    ImplementationPlanInput,
    LoginInput,
    PreflightTriageInput,
    PullRequestLinkInput,
    RegisterInput,
    ReasonInput,
    RequirementCreate,
    RequirementRead,
    RequirementStatusInput,
    RequirementUpdate,
    RequirementSpecCreate,
    RequirementSpecUpdate,
    ReviewInput,
    RoleUpdate,
    RunHeartbeatInput,
    RunQuestionInput,
    RunQuestionAnswerInput,
    RunResultInput,
    SpecApproveInput,
    SummaryCorrectionInput,
    UserRead,
)
from .security import (
    authenticate, create_agent_token_value, create_token, current_user, hash_password, manager, optional_user, owner,
    resolve_agent_token,
)
from .services import (
    GitHubClient, analyze_draft, audit, closing_issue_numbers, enqueue, pull_request_summary,
    requirement_snapshot, requirement_status_from_github, verify_webhook,
)
from . import usage as usage_api
from .ai_settings import (
    AIModelTarget, TASK_TYPES, connection_dict, decrypt_api_key, encrypt_api_key, model_dict,
    settings_dict as ai_settings_dict, test_model_target,
)
from .delivery import (
    DomainConflict, answer_run_question, approve_spec, cancel_run, claim_task, create_delivery_task, create_spec,
    heartbeat as heartbeat_service, idempotent_result, link_pull_request as link_pr_service,
    invalidate_delivery_authorizations, lease_token_for, register_artifact, requirement_transition, run_dict, spec_dict,
    submit_question as submit_question_service,
    submit_result as submit_result_service, task_dict, update_spec,
    submit_implementation_plan,
)


logger = logging.getLogger(__name__)


def ok(data=None, msg: str = "success"):
    return {"code": 0, "msg": msg, "data": data}


def agent_with_scope(required_scope: str):
    def dependency(authorization: str | None = Header(default=None, alias="Authorization"), db: Session = Depends(get_db)):
        if not authorization or not authorization.lower().startswith("bearer "):
            raise HTTPException(status_code=401, detail="Agent token required")
        token = resolve_agent_token(db, authorization.split(" ", 1)[1].strip())
        if not token or required_scope not in token.scopes:
            raise HTTPException(status_code=403, detail=f"Missing agent scope: {required_scope}")
        creator = db.query(User).filter(User.id == token.created_by, User.is_active.is_(True)).first()
        if not creator or creator.role not in {"admin", "owner"} or token.project_key != "trailsnap":
            raise HTTPException(status_code=403, detail="Agent token owner or project is no longer authorized")
        return token
    return dependency


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
        public_fields = {"schema_version", "problem_summary", "category", "completeness_items", "duplicate_candidates",
                         "recommended_disposition", "acceptance_draft", "fallback_reason"}
        data["triage"] = report.report if include_private else {key: value for key, value in report.report.items() if key in public_fields}
        data["triage_provider"] = report.provider if include_private else None
        data["triage_model"] = report.model if include_private else None
    else:
        data["triage"] = None
        data["triage_provider"] = None
        data["triage_model"] = None
    attachments = db.query(RequirementAttachment).filter(
        RequirementAttachment.requirement_id == row.id
    ).order_by(RequirementAttachment.created_at).all() if include_private else []
    data["attachments"] = [{
        "id": item.id, "name": item.original_name, "content_type": item.content_type,
        "size_bytes": item.size_bytes, "kind": item.kind, "content_sha256": item.content_sha256,
        "processing_status": item.processing_status, "processing_error": item.processing_error,
        "created_at": item.created_at.isoformat(),
        "download_url": f"/api/requirements/{row.id}/attachments/{item.id}",
    } for item in attachments]
    questions = db.query(ClarificationQuestion).filter(ClarificationQuestion.requirement_id == row.id).order_by(
        ClarificationQuestion.created_at
    ).all()
    if row.created_by is not None and include_private:
        data["clarifications"] = [{"id": item.id, "question_id": item.question_id, "target_field": item.target_field,
                                   "question": item.question, "rationale": item.rationale, "blocking": item.blocking,
                                   "suggested_options": item.suggested_options, "status": item.status,
                                   "answer": item.answer, "round_number": item.round_number} for item in questions]
    else:
        data["clarifications"] = []
    if include_private:
        specs = db.query(RequirementSpec).filter(RequirementSpec.requirement_id == row.id).order_by(RequirementSpec.revision.desc()).all()
        data["specs"] = [spec_dict(db, item) for item in specs]
        tasks = db.query(DeliveryTask).filter(DeliveryTask.requirement_id == row.id).order_by(DeliveryTask.created_at.desc()).all()
        data["delivery_tasks"] = [task_dict(db, item) for item in tasks]
    return data


def enqueue_github_sync(db: Session, row: Requirement) -> None:
    if row.github_issue_number or (row.visibility == "public" and row.status == "candidate"):
        enqueue(db, "github_issue", row.id, f"github_issue:{row.id}:{row.status}:{secrets.token_hex(6)}")


def apply_github_status(
    db: Session, row: Requirement, issue: dict, *, action: str | None = None,
    changed_label: str | None = None, actor_id: str | None = None, actor_name: str = "GitHub",
    source: str = "github",
) -> bool:
    """Apply one GitHub-originated transition and retain an attributable audit record."""
    row.github_state = issue.get("state", row.github_state)
    suggested = requirement_status_from_github(issue, current_status=row.status, action=action, changed_label=changed_label)
    before = row.status
    changed = suggested != before
    if changed:
        requirement_transition(
            db, row, suggested, actor_id=actor_id,
            reason=f"GitHub Issue 状态同步为 {issue.get('state', 'unknown')}", source=source,
        )
    audit(
        db, actor_id, "github.requirement_state_observed", "requirement", row.id,
        platform_status=row.status, suggested_status=suggested, github_state=row.github_state,
        source=source, actor_name=actor_name, github_action=action,
    )
    return changed


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


@app.exception_handler(DomainConflict)
async def domain_conflict(_request: Request, exc: DomainConflict):
    return JSONResponse(status_code=409, content={"code": 409, "msg": str(exc),
        "data": {"current_version": exc.current_version, "allowed_actions": exc.allowed_actions}})


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
                "project_key": row.project_key, "agent_role": row.agent_role, "task_id": row.task_id,
                "expires_at": row.expires_at.isoformat() if row.expires_at else None,
                "last_used_at": row.last_used_at.isoformat() if row.last_used_at else None,
                "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None,
                "created_at": row.created_at.isoformat()} for row in rows])


@app.post("/api/admin/agent-tokens")
def create_agent_token(payload: AgentTokenCreate, actor: User = Depends(manager), db: Session = Depends(get_db)):
    if payload.task_id and not db.query(DeliveryTask).filter(DeliveryTask.id == payload.task_id).first():
        raise HTTPException(status_code=404, detail="Delivery task not found")
    if "tasks:claim" in payload.scopes and payload.agent_role not in {None, "coding"}:
        raise HTTPException(status_code=409, detail="Phase B only supports coding task claims")
    value, prefix, token_hash = create_agent_token_value()
    expires_at = datetime.now(timezone.utc) + timedelta(days=payload.expires_in_days) if payload.expires_in_days else None
    row = AgentToken(name=payload.name, token_prefix=prefix, token_hash=token_hash,
                     scopes=sorted(set(payload.scopes)), created_by=actor.id, expires_at=expires_at,
                     project_key=payload.project_key, agent_role=payload.agent_role, task_id=payload.task_id)
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


@app.get("/api/admin/ai-settings")
def get_ai_settings(_actor: User = Depends(manager), db: Session = Depends(get_db)):
    return ok(ai_settings_dict(db))


@app.post("/api/admin/ai-connections")
def create_ai_connection(payload: AIConnectionCreate, actor: User = Depends(manager), db: Session = Depends(get_db)):
    encrypted, hint = encrypt_api_key(payload.api_key)
    row = AIConnection(
        name=payload.name.strip(), provider=payload.provider, api_base=payload.api_base.rstrip("/"),
        api_key_encrypted=encrypted, api_key_hint=hint, enabled=payload.enabled,
        timeout_seconds=payload.timeout_seconds, priority=payload.priority, created_by=actor.id,
    )
    db.add(row)
    try:
        db.flush()
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="AI connection name already exists") from exc
    audit(db, actor.id, "ai_connection.created", "ai_connection", row.id,
          name=row.name, provider=row.provider, api_base=row.api_base)
    db.commit()
    db.refresh(row)
    return ok(connection_dict(db, row))


@app.patch("/api/admin/ai-connections/{connection_id}")
def update_ai_connection(connection_id: str, payload: AIConnectionUpdate,
                         actor: User = Depends(manager), db: Session = Depends(get_db)):
    row = db.query(AIConnection).filter(AIConnection.id == connection_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="AI connection not found")
    values = payload.model_dump(exclude_unset=True, exclude={"api_key", "clear_api_key"})
    for key, value in values.items():
        setattr(row, key, value.rstrip("/") if key == "api_base" else value)
    if payload.clear_api_key:
        row.api_key_encrypted, row.api_key_hint = None, None
    elif payload.api_key:
        row.api_key_encrypted, row.api_key_hint = encrypt_api_key(payload.api_key)
    audit(db, actor.id, "ai_connection.updated", "ai_connection", row.id,
          fields=sorted(payload.model_fields_set - {"api_key"}), api_key_changed=bool(payload.api_key or payload.clear_api_key))
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="AI connection name already exists") from exc
    db.refresh(row)
    return ok(connection_dict(db, row))


@app.delete("/api/admin/ai-connections/{connection_id}")
def delete_ai_connection(connection_id: str, actor: User = Depends(manager), db: Session = Depends(get_db)):
    row = db.query(AIConnection).filter(AIConnection.id == connection_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="AI connection not found")
    model_ids = [item[0] for item in db.query(AIModel.id).filter(AIModel.connection_id == row.id).all()]
    for route in db.query(AITaskRoute).all():
        filtered = [item for item in (route.model_ids or []) if item not in model_ids]
        if filtered != (route.model_ids or []):
            route.model_ids = filtered
            if not filtered:
                route.enabled = False
    audit(db, actor.id, "ai_connection.deleted", "ai_connection", row.id, name=row.name)
    db.delete(row)
    db.commit()
    return ok({"deleted": True})


@app.post("/api/admin/ai-connections/{connection_id}/models")
def create_ai_model(connection_id: str, payload: AIModelCreate,
                    actor: User = Depends(manager), db: Session = Depends(get_db)):
    if not db.query(AIConnection.id).filter(AIConnection.id == connection_id).first():
        raise HTTPException(status_code=404, detail="AI connection not found")
    row = AIModel(connection_id=connection_id, **payload.model_dump())
    db.add(row)
    try:
        db.flush()
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Model already exists on this connection") from exc
    audit(db, actor.id, "ai_model.created", "ai_model", row.id,
          connection_id=connection_id, model_name=row.model_name)
    db.commit()
    db.refresh(row)
    return ok(model_dict(row))


@app.patch("/api/admin/ai-models/{model_id}")
def update_ai_model(model_id: str, payload: AIModelUpdate,
                    actor: User = Depends(manager), db: Session = Depends(get_db)):
    row = db.query(AIModel).filter(AIModel.id == model_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="AI model not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    audit(db, actor.id, "ai_model.updated", "ai_model", row.id, fields=sorted(payload.model_fields_set))
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Model already exists on this connection") from exc
    db.refresh(row)
    return ok(model_dict(row))


@app.delete("/api/admin/ai-models/{model_id}")
def delete_ai_model(model_id: str, actor: User = Depends(manager), db: Session = Depends(get_db)):
    row = db.query(AIModel).filter(AIModel.id == model_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="AI model not found")
    for route in db.query(AITaskRoute).all():
        if model_id in (route.model_ids or []):
            route.model_ids = [item for item in route.model_ids if item != model_id]
            if not route.model_ids:
                route.enabled = False
    audit(db, actor.id, "ai_model.deleted", "ai_model", row.id, model_name=row.model_name)
    db.delete(row)
    db.commit()
    return ok({"deleted": True})


@app.put("/api/admin/ai-task-routes/{task_type}")
def update_ai_task_route(task_type: str, payload: AITaskRouteUpdate,
                         actor: User = Depends(manager), db: Session = Depends(get_db)):
    if task_type not in TASK_TYPES:
        raise HTTPException(status_code=404, detail="Unknown AI task type")
    if payload.enabled and not payload.model_ids:
        raise HTTPException(status_code=422, detail="Enabled AI task routes require at least one model")
    found = {item[0] for item in db.query(AIModel.id).filter(AIModel.id.in_(payload.model_ids)).all()} if payload.model_ids else set()
    if found != set(payload.model_ids):
        raise HTTPException(status_code=422, detail="One or more AI models do not exist")
    selected_models = db.query(AIModel).filter(AIModel.id.in_(payload.model_ids)).all() if payload.model_ids else []
    unsupported = [item.model_name for item in selected_models if payload.reasoning_effort not in (item.reasoning_levels or ["none"])]
    if unsupported:
        raise HTTPException(status_code=422, detail=f"所选思考等级不受模型支持：{', '.join(unsupported)}")
    row = db.query(AITaskRoute).filter(AITaskRoute.task_type == task_type).first()
    if not row:
        row = AITaskRoute(task_type=task_type, updated_by=actor.id)
        db.add(row)
    row.enabled, row.model_ids, row.reasoning_effort, row.updated_by = (
        payload.enabled, payload.model_ids, payload.reasoning_effort, actor.id
    )
    audit(db, actor.id, "ai_task_route.updated", "ai_task_route", task_type,
          enabled=row.enabled, model_ids=row.model_ids, reasoning_effort=row.reasoning_effort)
    db.commit()
    return ok(next(item for item in ai_settings_dict(db)["routes"] if item["task_type"] == task_type))


@app.post("/api/admin/ai-connections/{connection_id}/test")
def test_ai_connection(connection_id: str, payload: AIConnectionTestInput,
                       _actor: User = Depends(manager), db: Session = Depends(get_db)):
    connection = db.query(AIConnection).filter(AIConnection.id == connection_id).first()
    if not connection:
        raise HTTPException(status_code=404, detail="AI connection not found")
    query = db.query(AIModel).filter(AIModel.connection_id == connection.id, AIModel.enabled.is_(True))
    model = query.filter(AIModel.id == payload.model_id).first() if payload.model_id else query.order_by(AIModel.created_at).first()
    if not model:
        raise HTTPException(status_code=409, detail="Please add and enable a model before testing")
    target = AIModelTarget(
        connection_id=connection.id, connection_name=connection.name, provider=connection.provider,
        api_base=connection.api_base.rstrip("/"), api_key=decrypt_api_key(connection.api_key_encrypted),
        model_id=model.id, model_name=model.model_name, supports_json_mode=model.supports_json_mode,
        timeout_seconds=connection.timeout_seconds,
    )
    return ok(test_model_target(target))


@app.post("/api/requirements/preflight-triage")
def preflight_triage(payload: PreflightTriageInput, db: Session = Depends(get_db)):
    values = payload.model_dump(mode="json")
    values["environment"] = {**values.get("environment", {}), "ai_preflight_answers": values.pop("answers", {})}
    return ok(analyze_draft(db, values))


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
    preflight_answers = values.pop("ai_clarification_answers", {})
    if preflight_answers:
        values["environment"] = {**values.get("environment", {}), "ai_preflight_answers": preflight_answers}
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
    digest = hashlib.sha256()
    try:
        with target.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > settings.max_attachment_bytes:
                    raise HTTPException(status_code=413, detail="单个附件不能超过 5MB")
                output.write(chunk)
                digest.update(chunk)
        if size == 0:
            raise HTTPException(status_code=422, detail="附件不能为空")
    except Exception:
        target.unlink(missing_ok=True)
        raise
    attachment = RequirementAttachment(
        requirement_id=row.id, uploaded_by=user.id if user else None, original_name=original_name, stored_name=stored_name,
        content_type=(file.content_type or "application/octet-stream")[:100], size_bytes=size,
        kind="image" if suffix in IMAGE_ATTACHMENT_EXTENSIONS else "file",
        content_sha256=digest.hexdigest(), processing_status="stored",
    )
    db.add(attachment)
    db.flush()
    row.content_revision += 1
    row.version += 1
    invalidate_delivery_authorizations(db, row, actor_id=user.id if user else None,
                                       reason="需求附件变化，旧执行授权已失效", source="attachment")
    enqueue(db, "triage", row.id, f"triage:{row.id}:content:{row.content_revision}")
    audit(db, user.id if user else None, "requirement.attachment_uploaded", "requirement", row.id,
          attachment_id=attachment.id, name=original_name, size_bytes=size, content_revision=row.content_revision)
    db.commit()
    return ok({"id": attachment.id, "name": original_name, "content_type": attachment.content_type,
               "size_bytes": size, "kind": attachment.kind, "content_sha256": attachment.content_sha256,
               "processing_status": attachment.processing_status,
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
    include_closed: bool = False,
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
    if not include_closed and not status and not mine:
        query = query.filter(Requirement.status != "closed")
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
        details = event.details or {}
        actor_name = db.query(User.username).filter(User.id == event.actor_id).scalar() if event.actor_id else None
        result.append({
            "id": event.id, "action": event.action, "actor_name": details.get("actor_name") or actor_name or "系统",
            "before": details.get("before"), "after": details.get("after") or details.get("status"),
            "reason": details.get("reason"), "source": details.get("source"), "created_at": event.created_at.isoformat(),
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
    row.content_revision += 1
    invalidate_delivery_authorizations(db, row, actor_id=user.id,
                                       reason="需求内容变化，旧执行授权已失效", source="rest")
    if row.status == "needs_information":
        requirement_transition(db, row, "submitted", actor_id=user.id, reason="用户补充了需求信息", source="rest")
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
    requirement_transition(db, row, "withdrawn", actor_id=user.id, reason="用户撤回需求", source="rest")
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
    requirement_transition(db, row, "triaging", actor_id=actor.id, reason="管理员重新发起分诊", source="rest")
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
    requirement_transition(db, row, status_by_action[payload.action], actor_id=actor.id,
                           reason=payload.reason, source="review")
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


@app.patch("/api/requirements/{requirement_id}/status")
def update_requirement_status(
    requirement_id: str,
    payload: RequirementStatusInput,
    actor: User = Depends(manager),
    db: Session = Depends(get_db),
):
    row = db.query(Requirement).filter(Requirement.id == requirement_id, Requirement.deleted_at.is_(None)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Requirement not found")
    if payload.status in {"accepted", "developing", "testing", "release_ready", "merged", "released"} and db.query(
        DeliveryTask.id
    ).filter(DeliveryTask.requirement_id == row.id).first():
        raise DomainConflict("新交付任务的状态只能由规格、执行、PR 和发布事实推进", current_version=row.state_version)
    before = row.status
    requirement_transition(db, row, payload.status, actor_id=actor.id, reason=payload.reason, source="rest")
    row.review_reason = payload.reason
    enqueue_github_sync(db, row)
    db.commit()
    return ok(requirement_data(row, db, include_private=True))


@app.post("/api/requirements/{requirement_id}/close")
def close_requirement(requirement_id: str, payload: ReasonInput, actor: User = Depends(manager), db: Session = Depends(get_db)):
    row = db.query(Requirement).filter(Requirement.id == requirement_id, Requirement.deleted_at.is_(None)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Requirement not found")
    before = row.status
    requirement_transition(db, row, "closed", actor_id=actor.id, reason=payload.reason, source="rest")
    row.review_reason = payload.reason
    enqueue_github_sync(db, row)
    db.add(ReviewDecision(requirement_id=row.id, reviewer_id=actor.id, action="close", reason=payload.reason))
    audit(db, actor.id, "requirement.closed", "requirement", row.id,
          before=before, after=row.status, reason=payload.reason)
    db.commit()
    return ok(requirement_data(row, db, include_private=True))


@app.post("/api/requirements/{requirement_id}/summary-corrections")
def correct_requirement_summary(requirement_id: str, payload: SummaryCorrectionInput,
                                actor: User = Depends(current_user), db: Session = Depends(get_db)):
    row = db.query(Requirement).filter(Requirement.id == requirement_id, Requirement.deleted_at.is_(None)).first()
    if not row or (row.created_by != actor.id and actor.role not in {"admin", "owner"}):
        raise HTTPException(status_code=404, detail="Requirement not found")
    if row.state_version != payload.expected_state_version:
        raise DomainConflict("需求已变化，请刷新后重试", current_version=row.state_version)
    before = row.confirmed_summary
    row.confirmed_summary = payload.summary.strip()
    row.content_revision += 1
    row.version += 1
    row.state_version += 1
    invalidate_delivery_authorizations(db, row, actor_id=actor.id,
                                       reason="确认摘要变化，旧执行授权已失效", source="summary_correction")
    enqueue(db, "triage", row.id, f"triage:{row.id}:content:{row.content_revision}")
    audit(db, actor.id, "requirement.summary_corrected", "requirement", row.id,
          before=before, after=row.confirmed_summary, content_revision=row.content_revision)
    db.commit()
    return ok(requirement_data(row, db, include_private=True, include_contact=actor.role in {"admin", "owner"}))


@app.post("/api/requirements/{requirement_id}/clarifications/{question_id}/answers")
def answer_clarification(requirement_id: str, question_id: str, payload: ClarificationAnswerInput,
                         actor: User = Depends(current_user), db: Session = Depends(get_db)):
    row = db.query(Requirement).filter(Requirement.id == requirement_id, Requirement.deleted_at.is_(None)).first()
    if not row or row.created_by is None or (row.created_by != actor.id and actor.role not in {"admin", "owner"}):
        raise HTTPException(status_code=404, detail="Requirement not found")
    if row.state_version != payload.expected_state_version:
        raise DomainConflict("需求已变化，请刷新后重试", current_version=row.state_version)
    question = db.query(ClarificationQuestion).filter(ClarificationQuestion.requirement_id == row.id,
                                                       ClarificationQuestion.question_id == question_id).first()
    if not question:
        raise HTTPException(status_code=404, detail="Clarification question not found")
    if question.status == "answered":
        raise DomainConflict("该问题已经回答", current_version=row.state_version)
    question.answer, question.answer_source = payload.answer.strip(), "user"
    question.answered_by, question.answered_at, question.status = actor.id, utcnow(), "answered"
    if question.target_field in {"expected_behavior", "steps_to_reproduce", "current_behavior"} and not getattr(row, question.target_field):
        setattr(row, question.target_field, payload.answer.strip())
    row.content_revision += 1
    row.version += 1
    invalidate_delivery_authorizations(db, row, actor_id=actor.id,
                                       reason="澄清答案变化，旧执行授权已失效", source="clarification")
    db.flush()
    remaining = db.query(ClarificationQuestion).filter(ClarificationQuestion.requirement_id == row.id,
                                                        ClarificationQuestion.status == "open",
                                                        ClarificationQuestion.blocking.is_(True)).count()
    if remaining == 0:
        requirement_transition(db, row, "submitted", actor_id=actor.id, reason="用户完成本轮澄清", source="clarification")
        enqueue(db, "triage", row.id, f"triage:{row.id}:content:{row.content_revision}")
    else:
        row.state_version += 1
    audit(db, actor.id, "clarification.answered", "clarification", question.id,
          requirement_id=row.id, question_id=question.question_id, content_revision=row.content_revision)
    db.commit()
    return ok(requirement_data(row, db, include_private=True, include_contact=actor.role in {"admin", "owner"}))


@app.get("/api/requirements/{requirement_id}/specs")
def list_requirement_specs(requirement_id: str, actor: User = Depends(manager), db: Session = Depends(get_db)):
    rows = db.query(RequirementSpec).filter(RequirementSpec.requirement_id == requirement_id).order_by(RequirementSpec.revision.desc()).all()
    return ok([spec_dict(db, row) for row in rows])


@app.post("/api/requirements/{requirement_id}/specs")
def create_requirement_spec(requirement_id: str, payload: RequirementSpecCreate,
                            idempotency_key: str = Header(alias="Idempotency-Key"),
                            actor: User = Depends(manager), db: Session = Depends(get_db)):
    requirement = db.query(Requirement).filter(Requirement.id == requirement_id, Requirement.deleted_at.is_(None)).first()
    if not requirement:
        raise HTTPException(status_code=404, detail="Requirement not found")
    request_data = payload.model_dump(mode="json")
    response, _ = idempotent_result(db, actor_key=actor.id, operation="create_spec", key=idempotency_key,
        request=request_data, action=lambda: spec_dict(db, create_spec(db, requirement, payload.content, actor.id,
                                                        payload.expected_requirement_state_version)))
    db.commit()
    return ok(response)


@app.patch("/api/specs/{spec_id}")
def update_requirement_spec(spec_id: str, payload: RequirementSpecUpdate,
                            idempotency_key: str = Header(alias="Idempotency-Key"),
                            actor: User = Depends(manager), db: Session = Depends(get_db)):
    spec = db.query(RequirementSpec).filter(RequirementSpec.id == spec_id).first()
    if not spec:
        raise HTTPException(status_code=404, detail="Spec not found")
    request_data = payload.model_dump(mode="json")
    response, _ = idempotent_result(db, actor_key=actor.id, operation="update_spec", key=idempotency_key,
        request=request_data, action=lambda: spec_dict(db, update_spec(db, spec, payload.content, actor.id,
                                                        payload.expected_state_version)))
    db.commit()
    return ok(response)


@app.post("/api/specs/{spec_id}/approve")
def approve_requirement_spec(spec_id: str, payload: SpecApproveInput,
                             idempotency_key: str = Header(alias="Idempotency-Key"),
                             actor: User = Depends(manager), db: Session = Depends(get_db)):
    spec = db.query(RequirementSpec).filter(RequirementSpec.id == spec_id).first()
    if not spec:
        raise HTTPException(status_code=404, detail="Spec not found")
    request_data = payload.model_dump(mode="json")
    response, _ = idempotent_result(db, actor_key=actor.id, operation="approve_spec", key=idempotency_key,
        request=request_data, action=lambda: spec_dict(db, approve_spec(db, spec, actor.id, payload.expected_state_version,
            manual_base_sha=payload.manual_base_sha, allow_manual_sha=actor.role == "owner")))
    db.commit()
    return ok(response)


@app.get("/api/specs/{spec_id}")
def get_requirement_spec(spec_id: str, actor: User = Depends(manager), db: Session = Depends(get_db)):
    spec = db.query(RequirementSpec).filter(RequirementSpec.id == spec_id).first()
    if not spec:
        raise HTTPException(status_code=404, detail="Spec not found")
    return ok(spec_dict(db, spec))


@app.post("/api/delivery-tasks", status_code=202)
def create_task(payload: DeliveryTaskCreate, idempotency_key: str = Header(alias="Idempotency-Key"),
                actor: User = Depends(manager), db: Session = Depends(get_db)):
    spec = db.query(RequirementSpec).filter(RequirementSpec.id == payload.spec_id).first()
    if not spec:
        raise HTTPException(status_code=404, detail="Spec not found")
    request_data = payload.model_dump(mode="json")
    response, _ = idempotent_result(db, actor_key=actor.id, operation="create_delivery_task", key=idempotency_key,
        request=request_data, action=lambda: task_dict(db, create_delivery_task(db, spec, actor.id,
            risk_level=payload.risk_level, budget=payload.budget, dependency_ids=payload.dependency_ids), include_context=True))
    db.commit()
    return ok(response, "accepted")


@app.get("/api/delivery-tasks")
def list_delivery_tasks(actor: User = Depends(manager), db: Session = Depends(get_db)):
    return ok([task_dict(db, row) for row in db.query(DeliveryTask).order_by(DeliveryTask.created_at.desc()).all()])


@app.get("/api/delivery-tasks/{task_id}")
def get_delivery_task(task_id: str, actor: User = Depends(manager), db: Session = Depends(get_db)):
    row = db.query(DeliveryTask).filter(DeliveryTask.id == task_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Delivery task not found")
    return ok(task_dict(db, row, include_context=True))


@app.post("/api/agent-runs/claim")
def claim_delivery_task(payload: AgentClaimInput, idempotency_key: str = Header(alias="Idempotency-Key"),
                        token: AgentToken = Depends(agent_with_scope("tasks:claim")), db: Session = Depends(get_db)):
    if token.agent_role not in {None, payload.role}:
        raise HTTPException(status_code=403, detail="Agent token role does not match claim role")
    request_data = payload.model_dump(mode="json")
    def action():
        run, lease_token, task = claim_task(db, runner_name=payload.runner_name, provider=payload.provider,
                                            model=payload.model, role=payload.role, restricted_task_id=token.task_id)
        result = run_dict(db, run, include_lease=True, lease_token=lease_token)
        result["task"] = task_dict(db, task, include_context=True)
        return result
    response, _ = idempotent_result(db, actor_key=f"agent:{token.id}", operation="claim_task", key=idempotency_key,
                                    request=request_data, action=action)
    response = dict(response)
    if "lease_token" not in response:
        response["lease_token"] = lease_token_for(db.query(AgentRun).filter(AgentRun.id == response["id"]).one())
    db.commit()
    return ok(response)


def _agent_run_for_token(db: Session, run_id: str, token: AgentToken) -> AgentRun:
    run = db.query(AgentRun).filter(AgentRun.id == run_id).first()
    if not run or (token.task_id and run.task_id != token.task_id):
        raise HTTPException(status_code=404, detail="Agent run not found")
    return run


@app.get("/api/agent-runs/{run_id}")
def get_agent_run(run_id: str, token: AgentToken = Depends(agent_with_scope("runs:write")), db: Session = Depends(get_db)):
    return ok(run_dict(db, _agent_run_for_token(db, run_id, token)))


@app.post("/api/agent-runs/{run_id}/heartbeat")
def heartbeat_run(run_id: str, payload: RunHeartbeatInput,
                  idempotency_key: str = Header(alias="Idempotency-Key"),
                  token: AgentToken = Depends(agent_with_scope("runs:write")), db: Session = Depends(get_db)):
    run = _agent_run_for_token(db, run_id, token)
    request_data = payload.model_dump(mode="json")
    response, _ = idempotent_result(db, actor_key=f"agent:{token.id}", operation="heartbeat_run", key=idempotency_key,
        request=request_data, action=lambda: run_dict(db, heartbeat_service(db, run, attempt_id=payload.attempt_id,
            lease_token=payload.lease_token, expected_state_version=payload.expected_state_version,
            session_reference=payload.session_reference)))
    db.commit()
    return ok(response)


@app.post("/api/agent-runs/{run_id}/questions")
def request_run_clarification(run_id: str, payload: RunQuestionInput,
                              idempotency_key: str = Header(alias="Idempotency-Key"),
                              token: AgentToken = Depends(agent_with_scope("runs:write")), db: Session = Depends(get_db)):
    run = _agent_run_for_token(db, run_id, token)
    request_data = payload.model_dump(mode="json")
    def action():
        question = submit_question_service(db, run, attempt_id=payload.attempt_id, lease_token=payload.lease_token,
            expected_state_version=payload.expected_state_version, question=payload.question, blocking=payload.blocking)
        db.flush()
        return {"id": question.id, "run": run_dict(db, run)}
    response, _ = idempotent_result(db, actor_key=f"agent:{token.id}", operation="request_clarification",
                                    key=idempotency_key, request=request_data, action=action)
    db.commit()
    return ok(response)


@app.post("/api/agent-runs/{run_id}/implementation-plan")
def submit_run_plan(run_id: str, payload: ImplementationPlanInput,
                    idempotency_key: str = Header(alias="Idempotency-Key"),
                    token: AgentToken = Depends(agent_with_scope("runs:write")), db: Session = Depends(get_db)):
    run = _agent_run_for_token(db, run_id, token)
    request_data = payload.model_dump(mode="json")
    response, _ = idempotent_result(db, actor_key=f"agent:{token.id}", operation="submit_implementation_plan",
        key=idempotency_key, request=request_data, action=lambda: run_dict(db, submit_implementation_plan(
            db, run, attempt_id=payload.attempt_id, lease_token=payload.lease_token,
            expected_state_version=payload.expected_state_version, plan={
                key: value for key, value in request_data.items()
                if key not in {"attempt_id", "lease_token", "expected_state_version"}
            })))
    db.commit()
    return ok(response)


@app.post("/api/agent-runs/{run_id}/results")
def submit_run_result(run_id: str, payload: RunResultInput,
                      idempotency_key: str = Header(alias="Idempotency-Key"),
                      token: AgentToken = Depends(agent_with_scope("runs:write")), db: Session = Depends(get_db)):
    run = _agent_run_for_token(db, run_id, token)
    request_data = payload.model_dump(mode="json")
    response, _ = idempotent_result(db, actor_key=f"agent:{token.id}", operation="submit_run_result",
        key=idempotency_key, request=request_data, action=lambda: run_dict(db, submit_result_service(db, run,
            attempt_id=payload.attempt_id, lease_token=payload.lease_token,
            expected_state_version=payload.expected_state_version, result=request_data)))
    db.commit()
    return ok(response)


@app.post("/api/agent-runs/{run_id}/artifacts")
def submit_run_artifact(run_id: str, payload: ArtifactInput,
                        idempotency_key: str = Header(alias="Idempotency-Key"),
                        token: AgentToken = Depends(agent_with_scope("artifacts:write")), db: Session = Depends(get_db)):
    run = _agent_run_for_token(db, run_id, token)
    request_data = payload.model_dump(mode="json")
    def action():
        row = register_artifact(db, run, attempt_id=payload.attempt_id, lease_token=payload.lease_token,
                                expected_state_version=payload.expected_state_version, producer_token_id=token.id,
                                artifact=request_data)
        return {"id": row.id, "run_state_version": run.state_version, "sha256": row.sha256, "uri": row.uri}
    response, _ = idempotent_result(db, actor_key=f"agent:{token.id}", operation="register_artifact",
                                    key=idempotency_key, request=request_data, action=action)
    db.commit()
    return ok(response)


@app.post("/api/delivery-tasks/{task_id}/pull-requests")
def link_delivery_pull_request(task_id: str, payload: PullRequestLinkInput,
                               idempotency_key: str = Header(alias="Idempotency-Key"),
                               token: AgentToken = Depends(agent_with_scope("runs:write")), db: Session = Depends(get_db)):
    task = db.query(DeliveryTask).filter(DeliveryTask.id == task_id).first()
    if not task or (token.task_id and token.task_id != task.id):
        raise HTTPException(status_code=404, detail="Delivery task not found")
    request_data = payload.model_dump(mode="json")
    def action():
        row = link_pr_service(db, task, number=payload.pull_request_number, url=payload.url,
                              head_sha=payload.head_sha, base_sha=payload.base_sha,
                              covered_ids=payload.covered_acceptance_ids,
                              expected_state_version=payload.expected_state_version)
        db.flush()
        return {"id": row.id, "task": task_dict(db, task)}
    response, _ = idempotent_result(db, actor_key=f"agent:{token.id}", operation="link_pull_request",
                                    key=idempotency_key, request=request_data, action=action)
    db.commit()
    return ok(response)


@app.post("/api/agent-runs/{run_id}/cancel")
def cancel_agent_run(run_id: str, actor: User = Depends(manager), db: Session = Depends(get_db)):
    run = db.query(AgentRun).filter(AgentRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Agent run not found")
    cancel_run(db, run, actor.id)
    db.commit()
    return ok(run_dict(db, run))


@app.post("/api/agent-run-questions/{question_id}/answer")
def answer_agent_question(question_id: str, payload: RunQuestionAnswerInput,
                          idempotency_key: str = Header(alias="Idempotency-Key"),
                          actor: User = Depends(manager), db: Session = Depends(get_db)):
    question = db.query(AgentRunQuestion).filter(AgentRunQuestion.id == question_id).first()
    if not question:
        raise HTTPException(status_code=404, detail="Agent question not found")
    request_data = payload.model_dump(mode="json")
    response, _ = idempotent_result(db, actor_key=actor.id, operation="answer_agent_question", key=idempotency_key,
        request=request_data, action=lambda: run_dict(db, answer_run_question(db, question, actor_id=actor.id,
            answer=payload.answer, expected_run_state_version=payload.expected_run_state_version,
            requires_spec_revision=payload.requires_spec_revision)))
    db.commit()
    return ok(response)


@app.get("/api/events")
def list_events(request: Request, cursor: int = 0, limit: int = Query(default=100, ge=1, le=500),
                actor: User = Depends(manager), db: Session = Depends(get_db)):
    def serialize(row: DomainEvent) -> dict:
        return {"cursor": row.sequence, "id": row.id, "event_type": row.event_type,
                "aggregate_type": row.aggregate_type, "aggregate_id": row.aggregate_id,
                "aggregate_version": row.aggregate_version, "source": row.source,
                "payload": row.payload, "created_at": row.created_at.isoformat()}
    if "text/event-stream" in request.headers.get("accept", ""):
        async def stream():
            last_event_id = request.headers.get("last-event-id", "")
            current = max(cursor, int(last_event_id) if last_event_id.isdigit() else 0)
            while True:
                with SessionLocal() as stream_db:
                    rows = stream_db.query(DomainEvent).filter(DomainEvent.sequence > current).order_by(DomainEvent.sequence).limit(limit).all()
                    payloads = [serialize(row) for row in rows]
                if payloads:
                    for payload in payloads:
                        current = payload["cursor"]
                        yield f"id: {current}\nevent: {payload['event_type']}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                else:
                    yield ": keepalive\n\n"
                await asyncio.sleep(5)
        return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})
    rows = db.query(DomainEvent).filter(DomainEvent.sequence > cursor).order_by(DomainEvent.sequence).limit(limit).all()
    return ok([serialize(row) for row in rows])


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
    enqueue_github_sync(db, row)
    audit(db, actor.id, "github.issue.created", "requirement", row.id, issue_number=data["number"])
    db.commit()
    return ok(requirement_data(row, db, include_private=True))


@app.post("/api/admin/github/issues/sync")
def import_github_issues(actor: User = Depends(manager), db: Session = Depends(get_db)):
    try:
        issues = GitHubClient().list_issues()
    except (RuntimeError, httpx.HTTPError) as exc:
        raise HTTPException(status_code=502, detail=f"GitHub Issue 同步失败：{exc}") from exc
    created = updated = skipped = 0
    for issue in issues:
        number = issue.get("number")
        if not number:
            skipped += 1
            continue
        label_names = [label.get("name", "") if isinstance(label, dict) else str(label) for label in issue.get("labels", [])]
        kind = "bug" if any(name.lower() == "bug" for name in label_names) else (
            "feature" if any(name.lower() in {"enhancement", "feature"} for name in label_names) else "improvement"
        )
        row = db.query(Requirement).filter(Requirement.github_issue_number == number).first()
        if row:
            row.github_issue_url = issue.get("html_url")
            if row.source == "github":
                row.title = (issue.get("title") or f"GitHub Issue #{number}")[:160]
                row.description = ((issue.get("body") or "GitHub Issue 未提供正文").strip() or "GitHub Issue 未提供正文")[:8000]
                row.type = kind
            apply_github_status(
                db, row, issue, actor_id=actor.id, actor_name=actor.username, source="github_manual_sync",
            )
            updated += 1
            continue
        row = Requirement(
            public_number=next_requirement_number(db),
            type=kind, title=(issue.get("title") or f"GitHub Issue #{number}")[:160],
            description=((issue.get("body") or "GitHub Issue 未提供正文").strip() or "GitHub Issue 未提供正文")[:8000],
            severity="medium", visibility="public", status="submitted", source="github", created_by=actor.id,
            github_issue_number=number, github_issue_url=issue.get("html_url"), github_state=issue.get("state"),
        )
        db.add(row)
        db.flush()
        db.add(RequirementFollower(requirement_id=row.id, user_id=actor.id))
        apply_github_status(
            db, row, issue, actor_id=actor.id, actor_name=actor.username, source="github_manual_sync",
        )
        if row.status == "submitted":
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
    apply_github_status(db, row, data, actor_id=actor.id, actor_name=actor.username, source="github_link")
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
    data = GitHubClient().update_issue_state(row.github_issue_number, "closed")
    row.github_state = data.get("state", "closed")
    audit(db, actor.id, "github.issue.closed", "requirement", row.id, platform_status=row.status,
          issue_number=row.github_issue_number, reason=payload.reason, source="platform")
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


@app.patch("/api/versions/{batch_id}")
def update_batch(batch_id: str, payload: BatchUpdate, actor: User = Depends(manager), db: Session = Depends(get_db)):
    batch = db.query(ReleaseBatch).filter(ReleaseBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Version batch not found")
    values = payload.model_dump(exclude_unset=True)
    if "version_name" in values and values["version_name"] != batch.version_name:
        other = db.query(ReleaseBatch).filter(ReleaseBatch.version_name == values["version_name"], ReleaseBatch.id != batch.id).first()
        if other:
            raise HTTPException(status_code=409, detail="Version name already exists")
    for key, value in values.items():
        setattr(batch, key, value)
    audit(db, actor.id, "release_batch.updated", "release_batch", batch.id,
          fields=sorted(values.keys()), before_version_name=batch.version_name, version_name=batch.version_name)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Version name already exists") from exc
    return ok(batch_data(batch, db, include_private=True))


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
            requirement_transition(db, requirement, "scheduled", actor_id=actor.id,
                                   reason=f"加入版本 {batch.version_name}", source="release_batch")
            enqueue_github_sync(db, requirement)
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
                if db.query(DeliveryTask.id).filter(DeliveryTask.requirement_id == requirement.id).first():
                    raise DomainConflict("新交付任务不能由旧版本状态接口推进", current_version=requirement.state_version)
                requirement_transition(db, requirement, requirement_status, actor_id=actor.id,
                                       reason=payload.reason, source="release_batch")
                enqueue_github_sync(db, requirement)
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
        if db.query(DeliveryTask.id).filter(DeliveryTask.requirement_id == requirement.id).first():
            raise DomainConflict("新交付任务不能由旧版本条目接口推进", current_version=requirement.state_version)
        requirement_transition(db, requirement, mapping[payload.status], actor_id=actor.id,
                               reason=f"版本交付状态：{payload.status}", source="release_batch")
        enqueue_github_sync(db, requirement)
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


@app.get("/api/usage/overview")
def usage_overview_endpoint(
    date_from: str | None = Query(default=None), date_to: str | None = Query(default=None),
    model: str | None = Query(default=None), app_type: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """cc-switch 用量总览（公开，无需登录）。"""
    return usage_api.get_usage_overview(date_from, date_to, model, app_type, db)


@app.get("/api/usage/daily")
def usage_daily_endpoint(
    date_from: str | None = Query(default=None), date_to: str | None = Query(default=None),
    model: str | None = Query(default=None), app_type: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """cc-switch 用量日序列（公开，无需登录）。"""
    return usage_api.get_usage_daily(date_from, date_to, model, app_type, db)


@app.get("/api/usage/filters")
def usage_filters_endpoint(db: Session = Depends(get_db)):
    """cc-switch 用量筛选可选值（公开，无需登录）。"""
    return usage_api.get_usage_filters(db)


@app.post("/api/usage/imports")
async def usage_import_endpoint(
    file: UploadFile = File(...), device_label: str = Form(...),
    actor: User = Depends(manager), db: Session = Depends(get_db),
):
    """上传 cc-switch 导出的 SQL 备份（仅管理员）。"""
    return await usage_api.upload_usage_import(file=file, device_label=device_label, actor=actor, db=db)


@app.get("/api/usage/imports")
def usage_imports_endpoint(actor: User = Depends(manager), db: Session = Depends(get_db)):
    """导入历史列表（仅管理员）。"""
    return usage_api.list_usage_imports(actor=actor, db=db)


@app.delete("/api/usage/imports/{import_id}")
def usage_import_delete_endpoint(import_id: str, actor: User = Depends(manager), db: Session = Depends(get_db)):
    """删除一次导入及其明细（仅管理员）。"""
    return usage_api.delete_usage_import(import_id, actor=actor, db=db)


@app.delete("/api/usage/devices/{device_id}")
def usage_device_delete_endpoint(device_id: str, actor: User = Depends(manager), db: Session = Depends(get_db)):
    """删除整个设备的全部用量数据（仅管理员）。"""
    return usage_api.delete_usage_device(device_id, actor=actor, db=db)


@app.get("/api/admin/dashboard")
def dashboard(_actor: User = Depends(manager), db: Session = Depends(get_db)):
    base = db.query(Requirement).filter(Requirement.deleted_at.is_(None))
    status_rows = db.query(Requirement.status, func.count(Requirement.id)).filter(
        Requirement.deleted_at.is_(None)
    ).group_by(Requirement.status).all()
    type_rows = db.query(Requirement.type, func.count(Requirement.id)).filter(
        Requirement.deleted_at.is_(None)
    ).group_by(Requirement.type).all()
    now = datetime.now(timezone.utc)
    since_7 = now - timedelta(days=7)
    since_30 = now - timedelta(days=30)
    trend_rows = db.query(
        func.substr(Requirement.created_at, 1, 10).label("day"), func.count(Requirement.id)
    ).filter(
        Requirement.deleted_at.is_(None), Requirement.created_at >= since_30
    ).group_by("day").all()
    trend_by_day = {day: count for day, count in trend_rows}
    daily_new = []
    for offset in range(29, -1, -1):
        day = (now - timedelta(days=offset)).date().isoformat()
        daily_new.append({"date": day, "count": trend_by_day.get(day, 0)})
    contributors_rows = db.query(Requirement.created_by, func.count(Requirement.id)).filter(
        Requirement.deleted_at.is_(None), Requirement.created_by.is_not(None)
    ).group_by(Requirement.created_by).all()
    contributors = [{
        "user_id": user_id,
        "name": db.query(User.username).filter(User.id == user_id).scalar() or "未知用户",
        "count": count,
    } for user_id, count in contributors_rows]
    contributors.sort(key=lambda item: (-item["count"], item["name"]))
    anonymous_count = base.filter(Requirement.created_by.is_(None)).count()
    followers = db.query(func.count(RequirementFollower.id)).scalar() or 0
    return ok({
        "total": base.count(),
        "new_last_7_days": base.filter(Requirement.created_at >= since_7).count(),
        "pending_review": base.filter(Requirement.status.in_({"submitted", "triaging", "pending_review"})).count(),
        "in_progress": base.filter(Requirement.status.in_({"scheduled", "developing", "testing", "release_ready"})).count(),
        "github_linked": base.filter(Requirement.github_issue_number.is_not(None)).count(),
        "anonymous": anonymous_count,
        "by_status": {status: count for status, count in status_rows},
        "by_type": {kind: count for kind, count in type_rows},
        "contributor_count": len(contributors) + (1 if anonymous_count else 0),
        "follower_count": followers,
        "daily_new_30d": daily_new,
        "top_contributors": contributors[:5],
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
            sender = payload.get("sender") or {}
            identity = db.query(GitHubIdentity).filter(GitHubIdentity.github_user_id == sender.get("id")).first()
            action = payload.get("action")
            changed_label = (payload.get("label") or {}).get("name")
            if action in {"closed", "reopened", "labeled", "unlabeled"}:
                changed = apply_github_status(
                    db, row, issue, action=action, changed_label=changed_label,
                    actor_id=identity.user_id if identity else None,
                    actor_name=f"GitHub @{sender.get('login', 'unknown')}", source="github_webhook",
                )
            else:
                row.github_state = issue.get("state", row.github_state)
                changed = False
            if changed:
                enqueue(db, "github_issue", row.id, f"github_issue:{row.id}:webhook:{delivery_id}")
    elif x_github_event == "pull_request":
        pull_request = payload.get("pull_request") or {}
        pull_request_number = pull_request.get("number") or payload.get("number")
        linked_issue_numbers = closing_issue_numbers(pull_request)
        if pull_request_number:
            summary = pull_request_summary({**pull_request, "number": pull_request_number})
            delivery_link = db.query(PullRequestLink).filter(
                PullRequestLink.repository == settings.github_repo,
                PullRequestLink.pull_request_number == pull_request_number,
            ).first()
            if delivery_link:
                delivery_link.url = summary.get("url") or delivery_link.url
                delivery_link.head_sha = str((pull_request.get("head") or {}).get("sha") or delivery_link.head_sha)
                delivery_link.state = summary["state"]
                task = db.query(DeliveryTask).filter(DeliveryTask.id == delivery_link.task_id).one()
                if summary["state"] == "merged" and task.state != "merged":
                    task.state, task.state_version = "merged", task.state_version + 1
                    requirement = db.query(Requirement).filter(Requirement.id == task.requirement_id).one()
                    requirement_transition(db, requirement, "merged", actor_id=None,
                                           reason=f"关联 PR #{pull_request_number} 已合并，等待版本发布",
                                           source="github_pull_request_webhook")
            linked_rows = db.query(Requirement).filter(
                Requirement.github_issue_number.is_not(None), Requirement.deleted_at.is_(None)
            ).all()
            for row in linked_rows:
                related = [
                    item for item in (row.github_pull_requests or [])
                    if item.get("number") != pull_request_number
                ]
                is_linked = row.github_issue_number in linked_issue_numbers
                if is_linked:
                    related.append(summary)
                    related.sort(key=lambda item: item.get("number") or 0, reverse=True)
                if related != (row.github_pull_requests or []):
                    was_linked = any(
                        item.get("number") == pull_request_number for item in (row.github_pull_requests or [])
                    )
                    row.github_pull_requests = related
                    audit(
                        db, None,
                        "github.pull_request.updated" if is_linked else "github.pull_request.unlinked",
                        "requirement", row.id, source="github_webhook",
                        pull_request_number=pull_request_number, pull_request_url=summary.get("url"),
                        newly_linked=is_linked and not was_linked,
                    )
                if is_linked and summary["state"] == "merged":
                    audit(db, None, "github.pull_request.merged", "requirement", row.id,
                          source="github_pull_request_webhook", pull_request_number=pull_request_number)
    event.processed = True
    db.commit()
    return ok({"accepted": True})
    ClarificationQuestion,
    DeliveryTask,
    DomainEvent,
    RequirementSpec,
    ClarificationAnswerInput,
    DeliveryTaskCreate,
    PreflightTriageInput,
    PullRequestLinkInput,
    RequirementSpecCreate,
    RequirementSpecUpdate,
    RunHeartbeatInput,
    RunQuestionInput,
    RunResultInput,
    SpecApproveInput,
    SummaryCorrectionInput,
