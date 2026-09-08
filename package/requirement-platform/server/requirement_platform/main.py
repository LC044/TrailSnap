import json
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db, init_db
from .models import (
    BackgroundJob,
    ReleaseBatch,
    ReleaseBatchItem,
    Requirement,
    RequirementFollower,
    RequirementRevision,
    ReviewDecision,
    TriageReport,
    User,
    WebhookEvent,
    utcnow,
)
from .schemas import (
    BatchCreate,
    BatchItemInput,
    BatchRead,
    BatchStatusInput,
    DeliveryStatusInput,
    LoginInput,
    RegisterInput,
    RequirementCreate,
    RequirementRead,
    RequirementUpdate,
    ReviewInput,
    RoleUpdate,
    UserRead,
)
from .security import authenticate, create_token, current_user, hash_password, manager, optional_user, owner
from .services import audit, enqueue, requirement_snapshot, verify_webhook


def ok(data=None, msg: str = "success"):
    return {"code": 0, "msg": msg, "data": data}


def requirement_data(row: Requirement, db: Session, *, include_private: bool = False) -> dict:
    data = RequirementRead.model_validate(row).model_dump(mode="json")
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
    return data


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
    return JSONResponse(
        status_code=422,
        content={"code": 422, "msg": "请求参数校验失败", "data": {"errors": exc.errors()}},
    )


@app.get("/api/health")
def health(db: Session = Depends(get_db)):
    db.query(User.id).first()
    return ok({"status": "healthy", "database": "sqlite"})


@app.get("/api/auth/status")
def auth_status(db: Session = Depends(get_db)):
    return ok({"has_owner": db.query(User).filter(User.role == "owner").first() is not None, "allow_registration": settings.allow_registration})


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
    return ok({"token": create_token(user), "user": UserRead.model_validate(user).model_dump(mode="json")})


@app.post("/api/auth/login")
def login(payload: LoginInput, db: Session = Depends(get_db)):
    user = authenticate(db, payload.identifier, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username/email or password")
    audit(db, user.id, "user.login", "user", user.id)
    db.commit()
    return ok({"token": create_token(user), "user": UserRead.model_validate(user).model_dump(mode="json")})


@app.get("/api/auth/me")
def me(user: User = Depends(current_user)):
    return ok(UserRead.model_validate(user).model_dump(mode="json"))


@app.get("/api/admin/users")
def list_users(_owner: User = Depends(owner), db: Session = Depends(get_db)):
    return ok([UserRead.model_validate(row).model_dump(mode="json") for row in db.query(User).order_by(User.created_at).all()])


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
    return ok(UserRead.model_validate(row).model_dump(mode="json"))


@app.post("/api/requirements")
def create_requirement(payload: RequirementCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    since = datetime.now(timezone.utc) - timedelta(days=1)
    daily = db.query(func.count(Requirement.id)).filter(Requirement.created_by == user.id, Requirement.created_at >= since).scalar() or 0
    if daily >= settings.daily_submission_limit:
        raise HTTPException(status_code=429, detail="Daily submission limit reached")
    terminal = {"rejected", "duplicate", "withdrawn", "closed", "released"}
    open_count = db.query(func.count(Requirement.id)).filter(
        Requirement.created_by == user.id, Requirement.status.notin_(terminal)
    ).scalar() or 0
    if open_count >= settings.max_open_requirements:
        raise HTTPException(status_code=429, detail="Too many open requirements")
    row = Requirement(created_by=user.id, **payload.model_dump())
    db.add(row)
    db.flush()
    db.add(RequirementFollower(requirement_id=row.id, user_id=user.id))
    audit(db, user.id, "requirement.created", "requirement", row.id, type=row.type)
    enqueue(db, "triage", row.id, f"triage:{row.id}:v{row.version}")
    db.commit()
    db.refresh(row)
    return ok(requirement_data(row, db, include_private=True), "submitted")


@app.get("/api/requirements")
def list_requirements(
    status: str | None = None,
    type: str | None = None,
    q: str | None = Query(default=None, max_length=100),
    mine: bool = False,
    limit: int = Query(50, ge=1, le=100),
    skip: int = Query(0, ge=0),
    user: User | None = Depends(optional_user),
    db: Session = Depends(get_db),
):
    query = db.query(Requirement)
    is_manager = bool(user and user.role in {"admin", "owner"})
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
        pattern = f"%{q.strip()}%"
        query = query.filter(or_(Requirement.title.ilike(pattern), Requirement.description.ilike(pattern)))
    rows = query.order_by(Requirement.created_at.desc()).offset(skip).limit(limit).all()
    return ok([requirement_data(row, db, include_private=is_manager or bool(user and row.created_by == user.id)) for row in rows])


@app.get("/api/requirements/{requirement_id}")
def get_requirement(requirement_id: str, user: User | None = Depends(optional_user), db: Session = Depends(get_db)):
    row = db.query(Requirement).filter(Requirement.id == requirement_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Requirement not found")
    allowed = row.visibility == "public" or bool(user and (user.id == row.created_by or user.role in {"admin", "owner"}))
    if not allowed:
        raise HTTPException(status_code=404, detail="Requirement not found")
    include_private = bool(user and (user.id == row.created_by or user.role in {"admin", "owner"}))
    return ok(requirement_data(row, db, include_private=include_private))


@app.patch("/api/requirements/{requirement_id}")
def update_requirement(
    requirement_id: str, payload: RequirementUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    row = db.query(Requirement).filter(Requirement.id == requirement_id).first()
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
        row.status = "submitted"
    enqueue(db, "triage", row.id, f"triage:{row.id}:v{row.version}")
    audit(db, user.id, "requirement.updated", "requirement", row.id, version=row.version)
    db.commit()
    return ok(requirement_data(row, db, include_private=True))


@app.post("/api/requirements/{requirement_id}/withdraw")
def withdraw_requirement(requirement_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    row = db.query(Requirement).filter(Requirement.id == requirement_id, Requirement.created_by == user.id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Requirement not found")
    if row.status in {"scheduled", "developing", "testing", "release_ready", "released"}:
        raise HTTPException(status_code=409, detail="Scheduled requirement cannot be withdrawn")
    row.status = "withdrawn"
    audit(db, user.id, "requirement.withdrawn", "requirement", row.id)
    db.commit()
    return ok(requirement_data(row, db, include_private=True))


@app.post("/api/requirements/{requirement_id}/follow")
def follow_requirement(requirement_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    requirement = db.query(Requirement).filter(Requirement.id == requirement_id).first()
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
    row = db.query(Requirement).filter(Requirement.id == requirement_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Requirement not found")
    key = f"triage:{row.id}:v{row.version}:manual:{int(datetime.now().timestamp()) // 60}"
    job = enqueue(db, "triage", row.id, key)
    row.status = "triaging"
    audit(db, actor.id, "triage.queued", "requirement", row.id, job_id=job.id)
    db.commit()
    return ok({"job_id": job.id})


@app.post("/api/requirements/{requirement_id}/review")
def review_requirement(requirement_id: str, payload: ReviewInput, actor: User = Depends(manager), db: Session = Depends(get_db)):
    row = db.query(Requirement).filter(Requirement.id == requirement_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Requirement not found")
    status_by_action = {
        "candidate": "candidate", "needs_information": "needs_information", "rejected": "rejected",
        "deferred": "deferred", "duplicate": "duplicate", "close": "closed",
    }
    if payload.action == "duplicate":
        target = db.query(Requirement).filter(Requirement.id == payload.duplicate_of_id).first()
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
    row.status = status_by_action[payload.action]
    row.review_reason = payload.reason
    row.priority = payload.priority
    row.risk_level = payload.risk_level
    db.add(ReviewDecision(
        requirement_id=row.id, reviewer_id=actor.id, action=payload.action, reason=payload.reason,
        metadata_json={"priority": payload.priority, "risk_level": payload.risk_level, "duplicate_of_id": payload.duplicate_of_id},
    ))
    if payload.action == "candidate" and row.visibility == "public":
        enqueue(db, "github_issue", row.id, f"github_issue:{row.id}")
    audit(db, actor.id, f"requirement.{payload.action}", "requirement", row.id, reason=payload.reason)
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
    requirement = db.query(Requirement).filter(Requirement.id == payload.requirement_id).first()
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
            requirement.status = "scheduled"
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
                requirement.status = requirement_status
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
        requirement.status = mapping[payload.status]
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
