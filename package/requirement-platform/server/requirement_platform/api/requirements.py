import asyncio
import hashlib
import json
import logging
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse, PlainTextResponse
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import settings
from ..db import SessionLocal, get_db
from ..delivery import DomainConflict, invalidate_delivery_authorizations, requirement_transition
from ..domain import requirements as requirement_service
from ..domain.common import audit, enqueue, requirement_snapshot
from ..models import (
    AuditEvent, ClarificationQuestion, Requirement, RequirementAttachment, RequirementFollower,
    RequirementRevision, RequirementSupplement, ReviewDecision, User, utcnow,
)
from ..presenters import requirement_data, requirement_list_context
from ..schemas import (
    ClarificationAnswerInput, PreflightTriageInput, ReasonInput, RequirementCreate,
    RequirementStatusInput, RequirementUpdate, RequirementSupplementCreate, ReviewInput, SummaryCorrectionInput,
)
from ..security import current_user, manager, optional_user
from ..services import analyze_draft, analyze_draft_stream
from .responses import ok
from ..public_agent_guide import agent_guide

router = APIRouter(tags=["requirements"])
logger = logging.getLogger(__name__)


@router.get("/api/agent-guide", response_class=PlainTextResponse)
def public_agent_guide():
    return PlainTextResponse(agent_guide(), headers={"Cache-Control": "no-store"})


def enqueue_github_sync(db: Session, row: Requirement) -> None:
    requirement_service.enqueue_github_sync(db, row, unique_suffix=secrets.token_hex(6))


def next_requirement_number(db: Session) -> int:
    return (db.query(func.max(Requirement.public_number)).scalar() or 0) + 1


def can_access_private_data(row: Requirement, user: User | None) -> bool:
    return bool(user and (user.id == row.created_by or user.role in {"admin", "owner"}))


EDITABLE_STATUSES = {"submitted", "needs_information", "pending_review"}


def edit_token_matches(row: Requirement, token: str | None) -> bool:
    return bool(
        row.created_by is None and token and len(token) <= 128 and row.anonymous_edit_token_hash
        and secrets.compare_digest(hashlib.sha256(token.encode()).hexdigest(), row.anonymous_edit_token_hash)
    )


def anonymous_submission_response(row: Requirement, db: Session, token: str) -> JSONResponse:
    data = requirement_data(row, db)
    data["edit_token"] = token
    data["public_url"] = f"{settings.web_url.rstrip('/')}/requirements/REQ-{row.public_number}"
    return JSONResponse(ok(data, "submitted"), headers={"Cache-Control": "no-store"})


@router.post("/api/requirements/preflight-triage")
def preflight_triage(payload: PreflightTriageInput, db: Session = Depends(get_db)):
    values = payload.model_dump(mode="json")
    values.pop("client_edit_token", None)
    values["environment"] = {**values.get("environment", {}), "ai_preflight_answers": values.pop("answers", {})}
    return ok(analyze_draft(db, values))


@router.post("/api/requirements/preflight-triage/stream")
async def preflight_triage_stream(payload: PreflightTriageInput):
    values = payload.model_dump(mode="json")
    values.pop("client_edit_token", None)
    values["environment"] = {**values.get("environment", {}), "ai_preflight_answers": values.pop("answers", {})}

    async def events():
        queue: asyncio.Queue[dict] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def publish(event: dict[str, Any]) -> None:
            loop.call_soon_threadsafe(queue.put_nowait, event)

        def run_analysis() -> None:
            with SessionLocal() as db:
                try:
                    result = analyze_draft_stream(db, values, publish)
                    publish({"type": "complete" if result.get("available") else "error", **result})
                except Exception as exc:
                    logger.exception("Streaming preflight triage failed")
                    publish({"type": "error", "available": False, "questions": [], "reason": str(exc)[:1000]})

        task = asyncio.create_task(asyncio.to_thread(run_analysis))
        try:
            while True:
                event = await queue.get()
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                if event.get("type") in {"complete", "error"}:
                    break
        finally:
            await task

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/api/requirements")
def create_requirement(payload: RequirementCreate, user: User | None = Depends(optional_user), db: Session = Depends(get_db)):
    values = payload.model_dump()
    client_token = values.pop("client_edit_token", None)
    edit_token = (client_token or secrets.token_urlsafe(32)) if not user else None
    token_hash = hashlib.sha256(edit_token.encode()).hexdigest() if edit_token else None
    submission_hash = hashlib.sha256(json.dumps(values, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    if not user and client_token:
        existing = db.query(Requirement).filter(Requirement.anonymous_creation_token_hash == token_hash).first()
        if existing:
            if existing.deleted_at or existing.anonymous_submission_hash != submission_hash or not edit_token_matches(existing, edit_token):
                raise HTTPException(status_code=409, detail="提交回执已使用，请勿改变重试内容")
            return anonymous_submission_response(existing, db, edit_token)
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
        anonymous_edit_token_hash=token_hash,
        anonymous_submission_hash=submission_hash if not user else None,
        anonymous_creation_token_hash=token_hash,
        **values,
    )
    db.add(row)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing = db.query(Requirement).filter(Requirement.anonymous_creation_token_hash == token_hash).first() if token_hash else None
        if existing and not existing.deleted_at and existing.anonymous_submission_hash == submission_hash and edit_token_matches(existing, edit_token):
            return anonymous_submission_response(existing, db, edit_token)
        raise HTTPException(status_code=409, detail="提交冲突，请重试")
    if user:
        db.add(RequirementFollower(requirement_id=row.id, user_id=user.id))
    audit(db, user.id if user else None, "requirement.created", "requirement", row.id, type=row.type, status=row.status)
    enqueue(db, "triage", row.id, f"triage:{row.id}:v{row.version}")
    db.commit()
    db.refresh(row)
    data = requirement_data(row, db, include_private=bool(user), include_contact=is_manager)
    if upload_token:
        data["upload_token"] = upload_token
        data["edit_token"] = edit_token
        data["public_url"] = f"{settings.web_url.rstrip('/')}/requirements/REQ-{row.public_number}"
    return JSONResponse(ok(data, "submitted"), headers={"Cache-Control": "no-store"})


ALLOWED_ATTACHMENT_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".txt", ".log", ".json", ".pdf"}
IMAGE_ATTACHMENT_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


@router.post("/api/requirements/{requirement_id}/attachments")
async def upload_requirement_attachment(
    requirement_id: str, file: UploadFile = File(...), user: User | None = Depends(optional_user),
    x_requirement_upload_token: str | None = Header(default=None), db: Session = Depends(get_db),
    x_requirement_edit_token: str | None = Header(default=None),
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
    edit_access = edit_token_matches(row, x_requirement_edit_token)
    if not can_access_private_data(row, user) and not anonymous_token_ok and not edit_access:
        raise HTTPException(status_code=403, detail="Not allowed")
    if not can_access_private_data(row, user):
        credential_filter = (
            Requirement.anonymous_edit_token_hash == hashlib.sha256(x_requirement_edit_token.encode()).hexdigest()
            if edit_access else
            Requirement.anonymous_upload_token_hash == hashlib.sha256(x_requirement_upload_token.encode()).hexdigest()
        )
        # Lock and recheck credentials/status before writing, including legacy upload receipts.
        changed = db.query(Requirement).filter(
            Requirement.id == row.id, Requirement.deleted_at.is_(None),
            Requirement.status.in_(EDITABLE_STATUSES), credential_filter,
        ).update({Requirement.state_version: Requirement.state_version}, synchronize_session=False)
        if not changed:
            raise HTTPException(status_code=409, detail="需求状态或上传权限已变化，请刷新后重试")
        db.refresh(row)
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
    row.state_version += 1
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


@router.get("/api/requirements/{requirement_id}/attachments/{attachment_id}")
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


@router.get("/api/requirements")
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
    list_context = requirement_list_context(db, rows)
    return ok([requirement_data(
        row, db,
        include_private=is_manager or bool(user and row.created_by == user.id),
        include_contact=is_manager,
        list_context=list_context,
    ) for row in rows])


@router.get("/api/requirements/number/{public_number}")
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


@router.get("/api/requirements/{requirement_id}/history")
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


@router.get("/api/requirements/{requirement_id}")
def get_requirement(requirement_id: str, user: User | None = Depends(optional_user), db: Session = Depends(get_db)):
    row = db.query(Requirement).filter(Requirement.id == requirement_id, Requirement.deleted_at.is_(None)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Requirement not found")
    allowed = row.visibility == "public" or bool(user and (user.id == row.created_by or user.role in {"admin", "owner"}))
    if not allowed:
        raise HTTPException(status_code=404, detail="Requirement not found")
    include_private = bool(user and (user.id == row.created_by or user.role in {"admin", "owner"}))
    return ok(requirement_data(row, db, include_private=include_private, include_contact=bool(user and user.role in {"admin", "owner"})))


@router.get("/api/requirements/{requirement_id}/edit-capability")
def edit_capability(
    requirement_id: str, x_requirement_edit_token: str | None = Header(default=None),
    user: User | None = Depends(optional_user), db: Session = Depends(get_db),
):
    row = db.query(Requirement).filter(Requirement.id == requirement_id, Requirement.deleted_at.is_(None)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Requirement not found")
    if not can_access_private_data(row, user) and not edit_token_matches(row, x_requirement_edit_token):
        raise HTTPException(status_code=403, detail="编辑凭证无效")
    return JSONResponse(ok({
        "can_edit": bool(user and user.role in {"admin", "owner"}) or row.status in EDITABLE_STATUSES,
        "can_supplement": True,
        "state_version": row.state_version,
        "reason": "" if row.status in EDITABLE_STATUSES else "需求已进入处理流程，正文暂时不能修改；你仍可追加补充说明，交由维护者评估。",
    }), headers={"Cache-Control": "no-store"})


@router.get("/api/requirements/{requirement_id}/supplements")
def list_supplements(requirement_id: str, user: User | None = Depends(optional_user), db: Session = Depends(get_db)):
    row = db.query(Requirement).filter(Requirement.id == requirement_id, Requirement.deleted_at.is_(None)).first()
    if not row or (row.visibility != "public" and not can_access_private_data(row, user)):
        raise HTTPException(status_code=404, detail="Requirement not found")
    notes = db.query(RequirementSupplement).filter_by(requirement_id=row.id).order_by(RequirementSupplement.created_at).all()
    return ok([{"id": note.id, "body": note.body, "created_at": note.created_at.isoformat(),
                "author_name": "维护者" if note.author_id and note.author_id != row.created_by else "提交者"} for note in notes])


@router.post("/api/requirements/{requirement_id}/supplements")
def create_supplement(
    requirement_id: str, payload: RequirementSupplementCreate, user: User | None = Depends(optional_user),
    db: Session = Depends(get_db), x_requirement_edit_token: str | None = Header(default=None),
):
    row = db.query(Requirement).filter(Requirement.id == requirement_id, Requirement.deleted_at.is_(None)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Requirement not found")
    anonymous = edit_token_matches(row, x_requirement_edit_token)
    if not anonymous and not can_access_private_data(row, user):
        raise HTTPException(status_code=403, detail="没有这条需求的修改权限")
    filters = [Requirement.id == row.id, Requirement.deleted_at.is_(None)]
    if anonymous:
        filters.append(Requirement.anonymous_edit_token_hash == hashlib.sha256(x_requirement_edit_token.encode()).hexdigest())
    # Serialize additions with deletion/receipt rotation without revising approved content.
    if not db.query(Requirement).filter(*filters).update({Requirement.updated_at: Requirement.updated_at}, synchronize_session=False):
        raise HTTPException(status_code=409, detail="需求或修改权限已变化，请刷新后重试")
    recent = db.query(func.count(RequirementSupplement.id)).filter(
        RequirementSupplement.requirement_id == row.id,
        RequirementSupplement.created_at >= datetime.now(timezone.utc) - timedelta(hours=1),
    ).scalar() or 0
    total = db.query(func.count(RequirementSupplement.id)).filter_by(requirement_id=row.id).scalar() or 0
    if recent >= 10 or total >= 100:
        raise HTTPException(status_code=429, detail="补充次数过多，请稍后再试")
    note = RequirementSupplement(requirement_id=row.id, author_id=user.id if user and not anonymous else None, body=payload.body)
    db.add(note)
    audit(db, note.author_id, "requirement.supplement_added", "requirement", row.id)
    db.commit()
    return JSONResponse(ok({"id": note.id}, "补充说明已保存，等待维护者评估"), headers={"Cache-Control": "no-store"})


@router.post("/api/requirements/{requirement_id}/edit-token/rotate")
def rotate_edit_token(
    requirement_id: str, x_requirement_edit_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    token = secrets.token_urlsafe(32)
    changed = db.query(Requirement).filter(
        Requirement.id == requirement_id, Requirement.created_by.is_(None),
        Requirement.deleted_at.is_(None),
        Requirement.anonymous_edit_token_hash == hashlib.sha256((x_requirement_edit_token or "").encode()).hexdigest(),
    ).update({Requirement.anonymous_edit_token_hash: hashlib.sha256(token.encode()).hexdigest(),
              Requirement.anonymous_upload_token_hash: None},
             synchronize_session=False)
    if not changed:
        raise HTTPException(status_code=403, detail="编辑凭证无效")
    audit(db, None, "requirement.edit_token_rotated", "requirement", requirement_id)
    db.commit()
    return JSONResponse(ok({"edit_token": token}), headers={"Cache-Control": "no-store"})


@router.patch("/api/requirements/{requirement_id}")
def update_requirement(
    requirement_id: str, payload: RequirementUpdate, user: User | None = Depends(optional_user),
    db: Session = Depends(get_db), x_requirement_edit_token: str | None = Header(default=None),
):
    row = db.query(Requirement).filter(Requirement.id == requirement_id, Requirement.deleted_at.is_(None)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Requirement not found")
    anonymous = edit_token_matches(row, x_requirement_edit_token)
    if not can_access_private_data(row, user) and not anonymous:
        raise HTTPException(status_code=403, detail="Not allowed")
    is_manager = bool(user and user.role in {"admin", "owner"})
    if row.status not in EDITABLE_STATUSES and not is_manager:
        raise HTTPException(status_code=409, detail="Requirement can no longer be edited")
    values = payload.model_dump(exclude_unset=True)
    expected = values.pop("expected_state_version", None)
    if anonymous:
        if expected is None:
            raise HTTPException(status_code=422, detail="expected_state_version is required")
        if "visibility" in values or "environment" in values:
            raise HTTPException(status_code=422, detail="匿名编辑不能修改公开范围或内部环境信息")
        if any(values.get(key) is None for key in ("type", "title", "description", "severity") if key in values):
            raise HTTPException(status_code=422, detail="必填字段不能为空")
    before = requirement_snapshot(row)
    if expected is not None:
        filters = [Requirement.id == row.id, Requirement.state_version == expected, Requirement.status == row.status]
        if anonymous:
            filters.append(Requirement.anonymous_edit_token_hash == hashlib.sha256(x_requirement_edit_token.encode()).hexdigest())
        changed = db.query(Requirement).filter(*filters).update(
            {Requirement.state_version: Requirement.state_version + 1}, synchronize_session=False,
        )
        if not changed:
            db.rollback()
            raise DomainConflict("需求已变化，请刷新后重试", current_version=row.state_version)
        db.refresh(row)
    else:
        row.state_version += 1
    actor_id = user.id if user and not anonymous else None
    db.add(RequirementRevision(requirement_id=row.id, editor_id=actor_id, snapshot=before, reason="updated"))
    for key, value in values.items():
        setattr(row, key, value)
    row.version += 1
    row.content_revision += 1
    invalidate_delivery_authorizations(db, row, actor_id=actor_id,
                                       reason="需求内容变化，旧执行授权已失效", source="rest")
    if row.status == "needs_information":
        requirement_transition(db, row, "submitted", actor_id=actor_id, reason="用户补充了需求信息", source="rest")
    enqueue_github_sync(db, row)
    enqueue(db, "triage", row.id, f"triage:{row.id}:v{row.version}")
    audit(db, actor_id, "requirement.updated", "requirement", row.id, version=row.version,
          actor_name="匿名提交者" if anonymous else user.username, source="anonymous_edit" if anonymous else "rest")
    db.commit()
    return JSONResponse(ok(requirement_data(row, db, include_private=not anonymous, include_contact=is_manager)),
                        headers={"Cache-Control": "no-store"})


@router.post("/api/requirements/{requirement_id}/withdraw")
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
@router.post("/api/requirements/{requirement_id}/follow")
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


@router.post("/api/requirements/{requirement_id}/triage")
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


@router.post("/api/requirements/{requirement_id}/review")
def review_requirement(requirement_id: str, payload: ReviewInput, actor: User = Depends(manager), db: Session = Depends(get_db)):
    try:
        row = requirement_service.get_requirement(db, requirement_id)
        requirement_service.review_requirement(
            db, row, actor_id=actor.id, action=payload.action, reason=payload.reason,
            priority=payload.priority, risk_level=payload.risk_level,
            duplicate_of_id=payload.duplicate_of_id, source="review",
            sync_suffix=secrets.token_hex(6),
        )
    except requirement_service.RequirementNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return ok(requirement_data(row, db, include_private=True))


@router.patch("/api/requirements/{requirement_id}/status")
def update_requirement_status(
    requirement_id: str,
    payload: RequirementStatusInput,
    actor: User = Depends(manager),
    db: Session = Depends(get_db),
):
    try:
        row = requirement_service.get_requirement(db, requirement_id)
    except requirement_service.RequirementNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    requirement_service.change_requirement_status(
        db, row, actor_id=actor.id, status=payload.status, reason=payload.reason,
        source="rest", sync_suffix=secrets.token_hex(6),
    )
    db.commit()
    return ok(requirement_data(row, db, include_private=True))


@router.post("/api/requirements/{requirement_id}/close")
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


@router.post("/api/requirements/{requirement_id}/summary-corrections")
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


@router.post("/api/requirements/{requirement_id}/clarifications/{question_id}/answers")
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


@router.delete("/api/requirements/{requirement_id}")
def delete_requirement(requirement_id: str, payload: ReasonInput, actor: User = Depends(manager), db: Session = Depends(get_db)):
    try:
        row = requirement_service.get_requirement(db, requirement_id)
        requirement_service.soft_delete_requirement(
            db, row, actor_id=actor.id, reason=payload.reason, source="rest"
        )
    except requirement_service.RequirementNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    db.commit()
    return ok({"deleted": True, "id": row.id})


@router.post("/api/requirements/{requirement_id}/restore")
def restore_requirement(requirement_id: str, actor: User = Depends(manager), db: Session = Depends(get_db)):
    try:
        row = requirement_service.get_requirement(db, requirement_id, include_deleted=True)
        requirement_service.restore_requirement(db, row, actor_id=actor.id, source="rest")
    except requirement_service.RequirementNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    db.commit()
    return ok(requirement_data(row, db, include_private=True))


