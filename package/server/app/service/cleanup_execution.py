"""Server-side cleanup selection and bounded recycle-bin execution."""
import asyncio
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import func
from sqlalchemy.orm import selectinload

from app.db.models.photo import Photo
from app.db.models.task import Task, TaskType
from app.db.models.user import User
from app.db.models.toolbox import ToolboxPlanItem, CleanupSelection, ToolboxPlan, CleanupGroup, CleanupMember


def start_cleanup(db, user, plan, request):
    if request.selected_items is not None:
        ids = set(request.selected_items)
        count = db.query(ToolboxPlanItem).filter(ToolboxPlanItem.plan_id == plan.id,
            ToolboxPlanItem.status == "candidate", ToolboxPlanItem.id.in_(ids)).count()
        if not ids or count != len(ids):
            raise ValueError("请手动勾选范围内的清理候选")
        db.query(CleanupSelection).filter_by(plan_id=plan.id).delete(synchronize_session=False)
        db.add_all([CleanupSelection(plan_id=plan.id, item_id=pid) for pid in ids])
        db.flush()
    selected = db.query(CleanupSelection.item_id).filter_by(plan_id=plan.id)
    query = db.query(ToolboxPlanItem).filter(ToolboxPlanItem.plan_id == plan.id, ToolboxPlanItem.id.in_(selected))
    count = query.count()
    if not count:
        raise ValueError("请手动勾选范围内的清理候选")
    # No giant NOT IN parameter list: use a correlated selected-item subquery.
    if plan.request["config"]["cleanup_mode"] == "duplicate":
        deleting = query.with_entities(ToolboxPlanItem.photo_id)
        cursor = 0
        while True:
            groups = db.query(CleanupGroup).filter(CleanupGroup.plan_id == plan.id,
                CleanupGroup.id > cursor, CleanupGroup.id.in_(db.query(CleanupMember.group_id).filter(
                    CleanupMember.plan_id == plan.id, CleanupMember.photo_id.in_(deleting))))
            rows = groups.order_by(CleanupGroup.id).limit(250).all()
            if not rows:
                break
            for row in rows:
                keeper = db.query(Photo.id).filter(Photo.owner_id == user.id, Photo.is_deleted.is_(False),
                    Photo.md5 == row.key, Photo.id.notin_(deleting)).first()
                if not keeper:
                    raise ValueError("重复组必须至少保留一项")
            cursor = rows[-1].id
    conflict = db.query(ToolboxPlanItem.id).join(ToolboxPlan).filter(
        ToolboxPlan.owner_id == user.id, ToolboxPlan.id != plan.id,
        ToolboxPlan.status.in_(["queued", "running"]),
        ToolboxPlanItem.photo_id.in_(query.with_entities(ToolboxPlanItem.photo_id))).first()
    if conflict:
        raise ValueError("这些影像正在被其他任务处理")
    query.update({ToolboxPlanItem.status: "ready", ToolboxPlanItem.reason: ""}, synchronize_session=False)
    task = Task(id=uuid4(), owner_id=user.id, type=TaskType.ORGANIZE_PHOTOS.value,
        status="pending", priority=10000, total_items=count, processed_items=0,
        payload={"toolbox_plan_id": str(plan.id)})
    db.add(task)
    db.flush()
    plan.task_id, plan.status = task.id, "queued"
    plan.stop_requested = False
    plan.summary = {**plan.summary, "ready": count}
    db.commit()
    return plan


def prepare_retry(db, plan):
    if plan.status in {"queued", "running", "preview"}:
        raise ValueError("请等待原任务结束")
    db.query(CleanupSelection).filter_by(plan_id=plan.id).delete(synchronize_session=False)
    cursor = 0
    while True:
        rows = db.query(ToolboxPlanItem).filter(ToolboxPlanItem.plan_id == plan.id,
            ToolboxPlanItem.status.in_(["ready", "failed"]), ToolboxPlanItem.id > cursor).order_by(ToolboxPlanItem.id).limit(250).all()
        if not rows:
            break
        for item in rows:
            item.detail = {**item.detail, "previous_failure": item.reason}
            item.status, item.reason = "candidate", "请重新勾选，执行时复核文件"
        cursor = rows[-1].id
        db.flush()
    plan.status, plan.stop_requested, plan.task_id = "preview", False, None
    plan.version += 1
    plan.expires_at = datetime.utcnow() + timedelta(days=7)
    plan.summary = {**plan.summary, "failed": 0, "ready": 0, "candidate": db.query(ToolboxPlanItem).filter_by(plan_id=plan.id, status="candidate").count()}
    db.commit()
    return plan


async def execute_cleanup(task, db, plan):
    from app.crud.photo import batch_soft_delete_photos
    from app.service.toolbox_plans import fingerprint
    from app.utils.hash import calculate_file_md5
    from app.service.toolbox_scope import canonical
    user = db.get(User, task.owner_id)
    plan.status = "running"
    db.commit()
    cursor = 0
    success = failed = 0
    while True:
        db.refresh(plan)
        if plan.stop_requested:
            break
        rows = db.query(ToolboxPlanItem).filter(ToolboxPlanItem.plan_id == plan.id,
            ToolboxPlanItem.status == "ready", ToolboxPlanItem.id > cursor).order_by(ToolboxPlanItem.id).limit(100).all()
        if not rows:
            break
        accepted = []
        from app.db.models.face import Face
        photos = {photo.id: photo for photo in db.query(Photo).options(selectinload(Photo.metadata_info),
            selectinload(Photo.tags), selectinload(Photo.faces).selectinload(Face.identity)).filter(
                Photo.id.in_([row.photo_id for row in rows]), Photo.owner_id == user.id, Photo.is_deleted.is_(False))}
        keepers = {}
        # The same user lock as confirmation serializes competing cleanup tasks.
        db.query(User).filter_by(id=user.id).update({User.is_active: User.is_active}, synchronize_session=False)
        for item in rows:
            try:
                photo = photos.get(item.photo_id)
                if not photo or canonical(photo.file_path) != canonical(item.source) or fingerprint(photo) != item.fingerprint:
                    raise ValueError("原文件或影像信息已变化，请重新扫描")
                if plan.request["config"]["cleanup_mode"] == "duplicate":
                    deleting = db.query(ToolboxPlanItem.photo_id).filter(ToolboxPlanItem.plan_id == plan.id,
                        ToolboxPlanItem.status.in_(["ready", "running"]))
                    md5 = item.detail["md5"]
                    if md5 not in keepers:
                        keeper = db.query(Photo).filter(Photo.owner_id == user.id, Photo.is_deleted.is_(False),
                            Photo.md5 == md5, Photo.id.notin_(deleting)).order_by(Photo.id).first()
                        keepers[md5] = bool(keeper and calculate_file_md5(keeper.file_path) == md5)
                    # Re-read bytes: cached hashes cannot authorize deleting a
                    # changed original or the last accessible copy.
                    if not keepers[md5] or calculate_file_md5(photo.file_path) != md5:
                        raise ValueError("重复组保留项或文件内容已变化")
                accepted.append(item)
            except (ValueError, OSError) as error:
                item.status, item.reason = "failed", str(error)
                failed += 1
        if accepted:
            # CRUD handles DB invalidation and recycle-bin side effects once per batch.
            for item in accepted:
                item.status = "success"
            batch_soft_delete_photos(db, [item.photo_id for item in accepted], user_id=user.id)
            success += len(accepted)
        cursor = rows[-1].id
        task.processed_items = success + failed
        db.commit()
        await asyncio.sleep(0)
    counts = dict(db.query(ToolboxPlanItem.status, func.count()).filter_by(plan_id=plan.id).group_by(ToolboxPlanItem.status).all())
    plan.status = "stopped" if plan.stop_requested else "partial" if counts.get("failed") else "completed"
    # Selection belongs to one execution batch; remaining candidates stay selectable.
    db.query(CleanupSelection).filter_by(plan_id=plan.id).delete(synchronize_session=False)
    if counts.get("candidate") and not plan.stop_requested:
        plan.status = "preview"
    plan.finished_at = datetime.utcnow()
    plan.summary = {**plan.summary, **counts, "candidate": counts.get("candidate", 0), "ready": counts.get("ready", 0), "running": 0}
    db.commit()
    return {"status": "completed", "success_count": counts.get("success", 0), "failed_count": counts.get("failed", 0)}
