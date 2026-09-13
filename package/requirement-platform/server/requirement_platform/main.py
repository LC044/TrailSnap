import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from .config import settings
from .db import SessionLocal, get_db, init_db
from .models import (
    AgentRun,
    AgentRunQuestion,
    BackgroundJob,
    AgentToken,
    DeliveryTask,
    DomainEvent,
    Requirement,
    RequirementFollower,
    RequirementSpec,
    User,
)
from .schemas import (
    AgentClaimInput,
    ArtifactInput,
    DeliveryTaskCreate,
    ImplementationPlanInput,
    PullRequestLinkInput,
    RequirementSpecCreate,
    RequirementSpecUpdate,
    RunHeartbeatInput,
    RunQuestionInput,
    RunQuestionAnswerInput,
    RunResultInput,
    SpecApproveInput,
)
from .security import (
    manager, resolve_agent_token,
)
from . import usage as usage_api
from .delivery import (
    DomainConflict, answer_run_question, approve_spec, cancel_run, claim_task, create_delivery_task, create_spec,
    heartbeat as heartbeat_service, idempotent_result, link_pull_request as link_pr_service,
    lease_token_for, register_artifact, run_dict, spec_dict,
    submit_question as submit_question_service,
    submit_result as submit_result_service, task_dict, update_spec,
    submit_implementation_plan,
)
from .api.responses import ok
from .api.admin import router as admin_router
from .api.ai_settings import router as ai_settings_router
from .api.auth import router as auth_router
from .api.github import router as github_router
from .api.requirements import router as requirements_router
from .api.releases import router as releases_router

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


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="TrailSnap Requirement Platform", version="0.1.0", lifespan=lifespan)
app.include_router(usage_api.router)
app.include_router(admin_router)
app.include_router(auth_router)
app.include_router(ai_settings_router)
app.include_router(github_router)
app.include_router(requirements_router)
app.include_router(releases_router)
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
    contributors_rows = db.query(
        Requirement.created_by, User.username, func.count(Requirement.id)
    ).join(User, User.id == Requirement.created_by).filter(
        Requirement.deleted_at.is_(None), Requirement.created_by.is_not(None)
    ).group_by(Requirement.created_by, User.username).all()
    contributors = [{
        "user_id": user_id,
        "name": username,
        "count": count,
    } for user_id, username, count in contributors_rows]
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
