"""Scoped toolbox API. New routes always return the shared response envelope."""
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.models.user import User
from app.db.models.toolbox import ToolboxPlan, ToolboxPlanItem
from app.dependencies import BaseResponse, get_db
from app.schemas.toolbox import ExecuteRequest, MediaScope, OrganizeRule, PlanRequest, ToolboxPreferences
from app.service.toolbox_scope import resolve_browser_folder, scope_preview
from app.service.toolbox_plans import create_plan, group_options, item_view, plan_view, validate_template
from app.service.toolbox_execution import get_plan, recovery_plan, start_plan
from app.service.task_manager import TaskManager

router = APIRouter()


def response_call(db, operation):
    try:
        return BaseResponse.success(operation())
    except ValueError as error:
        db.rollback()
        return BaseResponse.fail(code=400, msg=str(error))


@router.get("/folders/resolve", response_model=BaseResponse[dict])
def resolve_folder(parent: str = Query(..., min_length=1, max_length=4096),
                   db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return response_call(db, lambda: {"path": resolve_browser_folder(db, user, parent)})


@router.post("/scopes/preview", response_model=BaseResponse[dict])
def preview_scope(scope: MediaScope, offset: int = Query(0, ge=0), limit: int = Query(40, ge=1, le=100),
                  db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return response_call(db, lambda: scope_preview(db, user, scope, offset, limit))


@router.post("/organize/options", response_model=BaseResponse[list])
def options(request: PlanRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return response_call(db, lambda: group_options(db, user, request.scope, request.config.rules[0]))


@router.post("/plans", response_model=BaseResponse[dict])
def preview(request: PlanRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return response_call(db, lambda: plan_view(create_plan(db, user, request)))


@router.get("/plans", response_model=BaseResponse[list])
def history(offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100),
            active_only: bool = False,
            db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    query = db.query(ToolboxPlan).filter(ToolboxPlan.owner_id == user.id, ToolboxPlan.status != "preview")
    if active_only:
        query = query.filter(ToolboxPlan.status.in_(["queued", "running"]))
    rows = query.order_by(ToolboxPlan.created_at.desc()).offset(offset).limit(limit).all()
    return BaseResponse.success([plan_view(row) for row in rows])


@router.get("/plans/{plan_id}", response_model=BaseResponse[dict])
def detail(plan_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return response_call(db, lambda: plan_view(get_plan(db, user.id, plan_id)))


@router.get("/plans/{plan_id}/items", response_model=BaseResponse[dict])
def items(plan_id: UUID, offset: int = Query(0, ge=0), limit: int = Query(40, ge=1, le=100),
          status: str | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    def load():
        get_plan(db, user.id, plan_id)
        query = db.query(ToolboxPlanItem).filter(ToolboxPlanItem.plan_id == plan_id)
        if status:
            query = query.filter(ToolboxPlanItem.status == status)
        return {"total": query.count(), "items": [item_view(row) for row in
                query.order_by(ToolboxPlanItem.id).offset(offset).limit(limit)]}
    return response_call(db, load)


@router.post("/plans/{plan_id}/execute", response_model=BaseResponse[dict])
def execute(plan_id: UUID, request: ExecuteRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    def run():
        plan = start_plan(db, user, plan_id, request)
        TaskManager.get_instance().start_worker_if_needed()
        return plan_view(plan)
    return response_call(db, run)


@router.post("/plans/{plan_id}/stop", response_model=BaseResponse[dict])
def stop(plan_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    def request_stop():
        plan = get_plan(db, user.id, plan_id)
        if plan.status not in {"queued", "running"}:
            raise ValueError("此任务已结束")
        plan.stop_requested = True
        db.commit()
        return plan_view(plan)
    return response_call(db, request_stop)


@router.post("/plans/{plan_id}/retry", response_model=BaseResponse[dict])
def retry(plan_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return response_call(db, lambda: plan_view(recovery_plan(db, user, get_plan(db, user.id, plan_id))))


@router.post("/plans/{plan_id}/undo", response_model=BaseResponse[dict])
def undo(plan_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return response_call(db, lambda: plan_view(recovery_plan(db, user, get_plan(db, user.id, plan_id), undo=True)))


@router.get("/preferences", response_model=BaseResponse[dict])
def preferences(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    value = ToolboxPreferences.model_validate((user.settings or {}).get("toolbox") or {})
    return BaseResponse.success(value.model_dump(mode="json"))


@router.put("/preferences", response_model=BaseResponse[dict])
def save_preferences(value: ToolboxPreferences, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    def save():
        db.query(User).filter(User.id == user.id).update({User.is_active: User.is_active}, synchronize_session=False)
        db.refresh(user)
        settings = dict(user.settings or {})
        old = settings.get("toolbox") or {}
        if old.get("version", 0) != value.version:
            raise ValueError("模板已在其他页面或设备更新，请重新载入")
        for preset in value.presets:
            if preset.config.kind == "rename":
                validate_template(preset.config.template)
        saved = value.model_dump(mode="json")
        saved["version"] += 1
        saved["recent"] = old.get("recent", [])
        settings["toolbox"] = saved
        user.settings = settings
        db.commit()
        return saved
    return response_call(db, save)
