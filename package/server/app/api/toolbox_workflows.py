"""Scoped toolbox API. New routes always return the shared response envelope."""
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.models.user import User
from app.db.models.toolbox import ToolboxPlan, ToolboxPlanItem
from app.dependencies import BaseResponse, get_db
from app.schemas.toolbox import ExecuteRequest, MediaScope, OrganizeRule, PlanRequest, ToolboxPreferences, CleanupSelectionRequest
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
    if request.config.kind == "cleanup":
        from app.service.cleanup_scan import enqueue_scan
        def enqueue():
            plan = enqueue_scan(db, user, request)
            TaskManager.get_instance().start_worker_if_needed()
            return plan_view(plan)
        return response_call(db, enqueue)
    return response_call(db, lambda: plan_view(create_plan(db, user, request)))


@router.get("/plans", response_model=BaseResponse[list])
def history(offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100),
            active_only: bool = False,
            db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    query = db.query(ToolboxPlan).filter(ToolboxPlan.owner_id == user.id)
    if active_only:
        query = query.filter(ToolboxPlan.status.in_(["queued", "running", "scan_queued", "scanning"]))
    rows = query.order_by(ToolboxPlan.created_at.desc()).offset(offset).limit(limit).all()
    return BaseResponse.success([plan_view(row) for row in rows])


@router.get("/plans/{plan_id}", response_model=BaseResponse[dict])
def detail(plan_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return response_call(db, lambda: plan_view(get_plan(db, user.id, plan_id)))


@router.get("/plans/{plan_id}/items", response_model=BaseResponse[dict])
def items(plan_id: UUID, offset: int = Query(0, ge=0), limit: int = Query(40, ge=1, le=100),
          status: str | None = None, group_by: bool = False, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    def load():
        plan = get_plan(db, user.id, plan_id)
        query = db.query(ToolboxPlanItem).filter(ToolboxPlanItem.plan_id == plan_id)
        if status:
            query = query.filter(ToolboxPlanItem.status == status)
        grouped = (group_by and plan.kind == "cleanup"
                   and plan.request.get("config", {}).get("cleanup_mode") in ("duplicate", "similar"))
        if grouped:
            # Page group seeds, then let the client fetch each group's members.
            group_key = ToolboxPlanItem.detail["group_id"].as_integer()
            seeds = query.with_entities(func.min(ToolboxPlanItem.id).label("id")).group_by(
                func.coalesce(group_key, -ToolboxPlanItem.id)).subquery()
            total = db.query(seeds).count()
            page_ids = db.query(seeds.c.id).order_by(seeds.c.id).offset(offset).limit(limit)
            page_rows = db.query(ToolboxPlanItem).filter(ToolboxPlanItem.id.in_(page_ids)).order_by(ToolboxPlanItem.id)
        else:
            total = query.count()
            page_rows = query.order_by(ToolboxPlanItem.id).offset(offset).limit(limit)
        if plan.kind != "cleanup" or not plan.summary.get("phase"):
            return {"total": total, "items": [item_view(row) for row in page_rows]}
        from app.db.models.toolbox import CleanupSelection
        selected = db.query(CleanupSelection.item_id).filter_by(plan_id=plan_id)
        rows = page_rows.all()
        selected_ids = {pid for (pid,) in selected.filter(CleanupSelection.item_id.in_([r.id for r in rows]))}
        return {"total": total, "selected_count": selected.count(), "items": [
            {**item_view(row), "selected": row.id in selected_ids} for row in rows]}
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
        if plan.status not in {"queued", "running", "scan_queued", "scanning"}:
            raise ValueError("此任务已结束")
        plan.stop_requested = True
        db.commit()
        return plan_view(plan)
    return response_call(db, request_stop)


@router.post("/plans/{plan_id}/retry", response_model=BaseResponse[dict])
def retry(plan_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    def recover():
        plan = get_plan(db, user.id, plan_id)
        if plan.status in {"scan_stopped", "scan_failed"}:
            from app.service.cleanup_scan import queue_scan
            queue_scan(db, plan)
            TaskManager.get_instance().start_worker_if_needed()
            return plan_view(plan)
        if plan.kind == "cleanup" and plan.summary.get("phase") == "done":
            from app.service.cleanup_execution import prepare_retry
            return plan_view(prepare_retry(db, plan))
        return plan_view(recovery_plan(db, user, plan))
    return response_call(db, recover)


@router.put("/plans/{plan_id}/selection", response_model=BaseResponse[dict])
def selection(plan_id: UUID, request: CleanupSelectionRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    def update():
        from app.db.models.toolbox import CleanupSelection
        # Serialize selection edits and execution on both databases.
        db.query(User).filter(User.id == user.id).update({User.is_active: User.is_active}, synchronize_session=False)
        plan = get_plan(db, user.id, plan_id)
        db.refresh(plan)
        if plan.kind != "cleanup" or plan.status != "preview" or plan.version != request.version or plan.expires_at < datetime.utcnow():
            raise ValueError("预览已变化，请刷新")
        ids = set(request.item_ids)
        rows = db.query(ToolboxPlanItem.id).filter(ToolboxPlanItem.plan_id == plan.id,
            ToolboxPlanItem.status == "candidate", ToolboxPlanItem.id.in_(ids)).all()
        if len(rows) != len(ids):
            raise ValueError("所选项目不属于此计划的候选")
        query = db.query(CleanupSelection).filter(CleanupSelection.plan_id == plan.id)
        existing = {row.item_id for row in query.filter(CleanupSelection.item_id.in_(ids))}
        if request.selected:
            db.add_all([CleanupSelection(plan_id=plan.id, item_id=pid) for pid in ids - existing])
        else:
            query.filter(CleanupSelection.item_id.in_(ids)).delete(synchronize_session=False)
        db.commit()
        return {"selected_count": query.count()}
    return response_call(db, update)


@router.get("/plans/{plan_id}/groups/{group_id}/members", response_model=BaseResponse[dict])
def group_members(plan_id: UUID, group_id: int, offset: int = Query(0, ge=0), limit: int = Query(24, ge=1, le=100),
                  db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    def load():
        from app.db.models.toolbox import CleanupGroup, CleanupMember
        from app.db.models.photo import Photo
        get_plan(db, user.id, plan_id)
        group = db.query(CleanupGroup).filter_by(id=group_id, plan_id=plan_id).first()
        if not group:
            raise ValueError("分组不存在")
        query = db.query(CleanupMember.photo_id, CleanupMember.in_scope).join(Photo, Photo.id == CleanupMember.photo_id).filter(
            CleanupMember.plan_id == plan_id, CleanupMember.group_id == group_id,
            Photo.owner_id == user.id, Photo.is_deleted.is_(False))
        members = query.order_by(CleanupMember.photo_id).offset(offset).limit(limit).all()
        photos = {photo.id: photo for photo in db.query(Photo).filter(Photo.id.in_([pid for pid, _ in members]))}
        plan_items = {item.photo_id: item for item in db.query(ToolboxPlanItem).filter(
            ToolboxPlanItem.plan_id == plan_id, ToolboxPlanItem.photo_id.in_(list(photos)))}
        from app.db.models.toolbox import CleanupSelection
        selected = {item_id for (item_id,) in db.query(CleanupSelection.item_id).filter(
            CleanupSelection.plan_id == plan_id, CleanupSelection.item_id.in_([item.id for item in plan_items.values()]))}
        return {"total": query.count(), "representative_id": str(group.representative_id), "items": [
            {"photo_id": str(pid), "in_scope": inside, "source": photos[pid].file_path,
             "item": {**item_view(plan_items[pid]), "selected": plan_items[pid].id in selected} if pid in plan_items else None}
            for pid, inside in members]}
    return response_call(db, load)


@router.get("/plans/{plan_id}/export")
def export_plan(plan_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    import csv
    import io
    from fastapi.responses import StreamingResponse
    get_plan(db, user.id, plan_id)
    bind = db.get_bind()
    def stream():
        yield '\ufeff'
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        def emit(values):
            buffer.seek(0)
            buffer.truncate()
            writer.writerow(["'" + str(value) if str(value).startswith(('=', '+', '-', '@', '\t', '\r')) else str(value) for value in values])
            return buffer.getvalue()
        yield emit(["原路径", "目标", "状态", "说明"])
        with Session(bind) as session:
            cursor = 0
            while True:
                rows = session.query(ToolboxPlanItem).filter(ToolboxPlanItem.plan_id == plan_id,
                    ToolboxPlanItem.id > cursor).order_by(ToolboxPlanItem.id).limit(250).all()
                if not rows:
                    break
                for row in rows:
                    yield emit([row.source, row.target, row.status, row.reason])
                cursor = rows[-1].id
    return StreamingResponse(stream(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="toolbox-{plan_id}.csv"'})


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
