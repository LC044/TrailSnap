"""Execute only frozen plans; never rescan a scope during file mutation."""
import os
import shutil
import hashlib
import json
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import func

from app.db.models.album import Album, AlbumPhoto
from app.db.models.photo import Photo
from app.db.models.photo_metadata import PhotoMetadata
from app.db.models.task import Task, TaskType
from app.db.models.toolbox import ToolboxPlan, ToolboxPlanItem
from app.db.models.user import User
from app.schemas.toolbox import ToolConfig
from app.service.disk_budget import disk_budget
from app.service.storage_paths import apply_photo_reference
from app.service.toolbox_plans import file_fingerprint, fingerprint
from app.service.toolbox_scope import allowed_directory, canonical


def get_plan(db, owner_id, plan_id):
    plan = db.query(ToolboxPlan).filter(ToolboxPlan.id == plan_id, ToolboxPlan.owner_id == owner_id).first()
    if not plan:
        raise ValueError("操作计划不存在或无权限")
    return plan


def start_plan(db, user, plan_id, request):
    # A write lock also serializes confirmations on SQLite, where FOR UPDATE
    # is ignored. It does not change the user's active flag.
    db.query(User).filter(User.id == user.id).update({User.is_active: User.is_active}, synchronize_session=False)
    db.refresh(user)
    plan = get_plan(db, user.id, plan_id)
    db.refresh(plan)
    if plan.task_id and plan.status != "preview":
        db.commit()
        return plan
    if plan.status != "preview" or plan.version != request.version or plan.expires_at < datetime.utcnow():
        raise ValueError("预览已过期或已变化，请重新生成")
    if not request.confirmed:
        raise ValueError("请先确认已查看变更预览")
    if plan.kind == "cleanup":
        selected = set(request.selected_items or [])
        candidates = db.query(ToolboxPlanItem).filter(ToolboxPlanItem.plan_id == plan.id,
                                                     ToolboxPlanItem.status == "candidate").all()
        if not selected or not selected.issubset({row.id for row in candidates}):
            raise ValueError("请手动勾选范围内的清理候选")
        groups = {}
        for row in candidates:
            groups.setdefault(row.detail.get("group"), []).append(row)
        if plan.request["config"]["cleanup_mode"] == "duplicate":
            deleting_ids = [row.photo_id for row in candidates if row.id in selected]
            for rows in groups.values():
                if not any(row.id in selected for row in rows):
                    continue
                remaining = db.query(Photo.id).filter(Photo.owner_id == user.id, Photo.is_deleted.is_(False),
                    Photo.md5 == rows[0].detail.get("md5"), Photo.id.notin_(deleting_ids)).first()
                if not remaining:
                    raise ValueError("重复组必须至少保留一项")
        for row in candidates:
            row.status = "ready" if row.id in selected else "skipped"
            row.reason = "" if row.id in selected else "未勾选，保留"
    items = db.query(ToolboxPlanItem).filter(ToolboxPlanItem.plan_id == plan.id, ToolboxPlanItem.status == "ready").all()
    if not items:
        raise ValueError("没有需要执行的变更")
    paths = {canonical(row.source) for row in items}
    for row in items:
        paths.update(canonical(path) for path in row.detail.get("targets", []) if path)
        if plan.kind in {"organize", "rename", "undo"} and row.target:
            paths.add(canonical(row.target))
    active = db.query(ToolboxPlanItem).join(ToolboxPlan).filter(
        ToolboxPlan.owner_id == user.id, ToolboxPlan.status.in_(["queued", "running"]),
        ToolboxPlan.id != plan.id,
    )
    ids = {row.photo_id for row in items}
    for row in active:
        other_paths = {canonical(row.source), *(canonical(p) for p in row.detail.get("targets", []))}
        if row.target and row.plan_id != plan.id:
            other_paths.add(canonical(row.target))
        if row.photo_id in ids or paths & other_paths:
            raise ValueError("这些影像或目标路径正在被其他任务处理，请稍后重试")
    task_type = TaskType.BATCH_RENAME if plan.kind == "rename" else TaskType.ORGANIZE_PHOTOS
    task = Task(id=uuid4(), type=task_type.value, status="pending", priority=10000,
                owner_id=user.id, total_items=len(items), processed_items=0,
                payload={"toolbox_plan_id": str(plan.id)})
    db.add(task)
    db.flush()
    plan.task_id = task.id
    plan.status = "queued"
    if plan.kind == "rename":
        settings = dict(user.settings or {})
        preferences = dict(settings.get("toolbox") or {})
        recent = [plan.request["config"], *preferences.get("recent", [])]
        unique = []
        for value in recent:
            if value not in unique:
                unique.append(value)
        preferences["recent"] = unique[:5]
        preferences["version"] = preferences.get("version", 0) + 1
        settings["toolbox"] = preferences
        user.settings = settings
    db.commit()
    return plan


def copy_exclusive(source, target):
    """Never overwrite an existing destination, including a racing writer."""
    created = False
    before = file_fingerprint(source)
    try:
        with open(source, "rb") as src, open(target, "xb") as dst:
            created = True
            shutil.copyfileobj(src, dst, length=1024 * 1024)
        shutil.copystat(source, target)
        if file_fingerprint(source) != before:
            raise ValueError("复制过程中源文件发生变化")
    except Exception:
        if created:
            os.unlink(target)
        raise


def transfer(source, target, *, move):
    os.makedirs(os.path.dirname(target), exist_ok=True)
    if move:
        try:
            os.link(source, target)
        except OSError as error:
            import errno
            if error.errno not in {errno.EXDEV, errno.EPERM, errno.ENOTSUP}:
                raise
        else:
            try:
                os.unlink(source)
            except Exception:
                os.unlink(target)
                raise
            return
    copy_exclusive(source, target)
    if move:
        try:
            os.unlink(source)
        except Exception:
            os.unlink(target)
            raise


def clone_photo(db, photo, target):
    excluded = {"id", "file_path", "storage_root_id", "storage_relative_path", "filename", "backup_key", "processed_tasks"}
    values = {column.name: getattr(photo, column.name) for column in photo.__table__.columns if column.name not in excluded}
    clone = Photo(id=uuid4(), file_path=target, filename=os.path.basename(target), processed_tasks={}, **values)
    db.add(clone)
    if photo.metadata_info:
        values = {c.name: getattr(photo.metadata_info, c.name) for c in PhotoMetadata.__table__.columns
                  if c.name not in {"id", "photo_id"}}
        clone.metadata_info = PhotoMetadata(photo_id=clone.id, **values)
    clone.tags = list(photo.tags)
    clone.albums = list(photo.albums)
    return clone


def mutate_file(db, user, photo, item, config):
    target = item.target
    source = item.source
    allowed_directory(db, user, os.path.dirname(source))
    allowed_directory(db, user, os.path.dirname(target))
    transferred = False
    move = config.kind in {"rename", "undo"} or config.action == "move"
    try:
        output = photo if move else clone_photo(db, photo, target)
        output.file_path = target
        output.filename = os.path.basename(target)
        apply_photo_reference(output, db)
        if not move:
            db.add(Task(type=TaskType.GENERATE_THUMBNAIL, owner_id=user.id, priority=98,
                        payload={"photo_id": str(output.id)}, status="pending"))
        db.flush()
        if not move:
            from app.service.journey_queue import enqueue
            enqueue(db, user.id)
            for album in output.albums:
                album.num_photos = db.query(AlbumPhoto).filter(AlbumPhoto.album_id == album.id).count()
        from app.crud.album import trigger_conditional_albums_update
        trigger_conditional_albums_update(db, user.id, [output.id], commit=False)
        with disk_budget.slots(source, target):
            transfer(source, target, move=move)
        transferred = True
        item.status = "success"
        item.reason = ""
        item.detail = {**item.detail, "output_id": str(output.id), "output_fingerprint": file_fingerprint(target)}
        db.commit()
    except Exception:
        db.rollback()
        if transferred:
            with disk_budget.slots(source, target):
                if move:
                    transfer(target, source, move=True)
                elif os.path.exists(target):
                    os.unlink(target)
        raise


def mutate_albums(db, user, photo, item):
    outputs = []
    for name in item.detail["albums"]:
        album = db.query(Album).filter(Album.owner_id == user.id, Album.name == name, Album.type == "user").first()
        if not album:
            album = Album(id=uuid4(), owner_id=user.id, name=name, type="user", num_photos=0, cover_id=photo.id)
            db.add(album)
            db.flush()
        if not db.query(AlbumPhoto).filter(AlbumPhoto.album_id == album.id, AlbumPhoto.photo_id == photo.id).first():
            db.add(AlbumPhoto(album_id=album.id, photo_id=photo.id))
            album.num_photos = (album.num_photos or 0) + 1
        outputs.append(str(album.id))
    item.detail = {**item.detail, "album_ids": outputs}
    item.status = "success"
    db.commit()


def prepare_metadata_file(source, temporary, detail):
    import piexif
    exif = piexif.load(source)
    if detail.get("time"):
        stamp = datetime.fromisoformat(detail["time"]).strftime("%Y:%m:%d %H:%M:%S").encode()
        exif.setdefault("Exif", {})[piexif.ExifIFD.DateTimeOriginal] = stamp
        exif["Exif"][piexif.ExifIFD.DateTimeDigitized] = stamp
        exif.setdefault("0th", {})[piexif.ImageIFD.DateTime] = stamp
    for key, exif_key in (("make", piexif.ImageIFD.Make), ("model", piexif.ImageIFD.Model)):
        if detail.get(key):
            exif.setdefault("0th", {})[exif_key] = detail[key].encode("utf-8")
    copy_exclusive(source, temporary)
    piexif.insert(piexif.dump(exif), temporary)


def sync_metadata_record(db, photo, temporary, detail):
    from PIL import Image
    from app.utils.exif import get_exif_data
    from app.crud.album import trigger_conditional_albums_update
    if not photo.metadata_info:
        photo.metadata_info = PhotoMetadata(photo_id=photo.id)
    if detail.get("time"):
        photo.photo_time = datetime.fromisoformat(detail["time"])
        from app.service.journey_queue import enqueue
        enqueue(db, photo.owner_id)
    for key in ("make", "model"):
        if detail.get(key):
            setattr(photo.metadata_info, key, detail[key])
    with Image.open(temporary) as image:
        photo.metadata_info.exif_info = json.dumps(get_exif_data(image), default=str, ensure_ascii=False)
    with open(temporary, "rb") as file:
        photo.md5 = hashlib.file_digest(file, "md5").hexdigest()
    photo.size = os.path.getsize(temporary)
    db.flush()
    trigger_conditional_albums_update(db, photo.owner_id, [photo.id], commit=False)


def mutate_metadata(db, photo, item):
    """Keep an original copy until EXIF and the database commit both succeed."""
    path = item.source
    token = uuid4().hex
    temporary = path + f".toolbox-{token}.tmp"
    backup = path + f".toolbox-{token}.bak"
    replaced = False
    preserve_backup = False
    output_fingerprint = None
    try:
        prepare_metadata_file(path, temporary, item.detail)
        copy_exclusive(path, backup)
        sync_metadata_record(db, photo, temporary, item.detail)
        expected = {"size": item.fingerprint["size"], "mtime_ns": item.fingerprint["mtime_ns"]}
        if file_fingerprint(path) != expected:
            raise ValueError("EXIF 准备期间原文件发生变化")
        output_fingerprint = file_fingerprint(temporary)
        item.status = "success"
        item.detail = {**item.detail, "output_fingerprint": output_fingerprint}
        db.flush()
        os.replace(temporary, path)
        replaced = True
        db.commit()
    except Exception:
        db.rollback()
        if replaced:
            try:
                if file_fingerprint(path) != output_fingerprint:
                    raise ValueError("写入后文件被外部修改")
                os.replace(backup, path)
            except Exception as restore_error:
                preserve_backup = True
                raise ValueError(f"EXIF 回滚未完成，原片保存在 {backup}，请人工核对") from restore_error
        raise
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
        if not preserve_backup and os.path.exists(backup):
            os.unlink(backup)


async def execute_plan(worker, task, db):
    plan = get_plan(db, task.owner_id, UUID(task.payload["toolbox_plan_id"]))
    if plan.task_id != task.id or plan.status not in {"queued", "running"}:
        raise ValueError("任务未通过此计划的执行确认")
    user = db.get(User, task.owner_id)
    config = ToolConfig.model_validate(plan.request["config"]) if plan.kind != "undo" else None
    plan.status = "running"
    db.commit()
    items = db.query(ToolboxPlanItem).filter(ToolboxPlanItem.plan_id == plan.id,
                                            ToolboxPlanItem.status.in_(["ready", "running"])).order_by(ToolboxPlanItem.id).all()
    for item in items:
        db.refresh(plan)
        if plan.stop_requested:
            break
        try:
            photo = db.query(Photo).filter(Photo.id == item.photo_id, Photo.owner_id == task.owner_id,
                                           Photo.is_deleted.is_(False)).first()
            if not photo:
                raise ValueError("影像已删除或无权限")
            if canonical(photo.file_path) != canonical(item.source) or fingerprint(photo) != item.fingerprint:
                raise ValueError("原文件或影像信息已变化，请重新预览")
            if item.status == "running":
                raise ValueError("上次操作中断，需要人工核对文件状态")
            item.status = "running"
            db.commit()
            if plan.kind in {"organize", "rename", "undo"}:
                targets = item.detail.get("targets", [item.target])
                if len(targets) > 1:
                    # Each output has its own row and retry boundary.
                    raise ValueError("多副本计划需要拆分明细")
                mutate_file(db, user, photo, item, config if config else SimpleUndo())
            elif plan.kind == "album":
                mutate_albums(db, user, photo, item)
            elif plan.kind == "cleanup":
                from app.crud.photo import batch_soft_delete_photos
                if config.cleanup_mode == "duplicate":
                    pending_ids = db.query(ToolboxPlanItem.photo_id).filter(
                        ToolboxPlanItem.plan_id == plan.id, ToolboxPlanItem.status.in_(["ready", "running"]))
                    retained = db.query(Photo.id).filter(Photo.owner_id == user.id, Photo.is_deleted.is_(False),
                        Photo.md5 == item.detail.get("md5"), Photo.id.notin_(pending_ids)).first()
                    if not retained:
                        raise ValueError("重复组保留项已不存在，停止删除此项")
                batch_soft_delete_photos(db, [photo.id], user_id=user.id)
                item.status = "success"
                db.commit()
            else:
                allowed_directory(db, user, os.path.dirname(item.source))
                mutate_metadata(db, photo, item)
        except Exception as error:
            db.rollback()
            item.status = "failed"
            item.reason = str(error)
            db.commit()
        task.processed_items = db.query(ToolboxPlanItem).filter(
            ToolboxPlanItem.plan_id == plan.id, ToolboxPlanItem.status.in_(["success", "failed"])).count()
        db.commit()
    counts = dict(db.query(ToolboxPlanItem.status, func.count()).filter(
        ToolboxPlanItem.plan_id == plan.id).group_by(ToolboxPlanItem.status).all())
    plan.status = "stopped" if plan.stop_requested else (
        ("partial" if counts.get("success") else "failed") if counts.get("failed") else "completed")
    plan.finished_at = datetime.utcnow()
    plan.summary = {**plan.summary, "ready": 0, "running": 0, **counts}
    db.commit()
    return {"success_count": counts.get("success", 0), "failed_count": counts.get("failed", 0),
            "plan_id": str(plan.id), "status": "completed"}


class SimpleUndo:
    kind = "undo"
    action = "move"


def recovery_plan(db, user, original, *, undo=False):
    if original.status in {"queued", "running"}:
        raise ValueError("请等待原任务结束")
    if undo:
        if original.kind not in {"organize", "rename"} or original.request["config"].get("action") == "copy":
            raise ValueError("本版仅支持移动和重命名撤销；复制副本请手动核对")
        if not original.finished_at or original.finished_at + timedelta(hours=24) < datetime.utcnow():
            raise ValueError("已超过 24 小时撤销窗口")
    plan = ToolboxPlan(id=uuid4(), owner_id=user.id, kind="undo" if undo else original.kind, status="preview",
                       version=1, request=original.request, summary={}, expires_at=datetime.utcnow() + timedelta(minutes=30))
    db.add(plan)
    statuses = ["success"] if undo else (["failed", "ready"] if original.status == "stopped" else ["failed"])
    rows = db.query(ToolboxPlanItem).filter(ToolboxPlanItem.plan_id == original.id,
                                           ToolboxPlanItem.status.in_(statuses)).all()
    ready = 0
    for row in rows:
        source, target = (row.target, row.source) if undo else (row.source, row.target)
        item = ToolboxPlanItem(plan_id=plan.id, photo_id=row.photo_id, source=source, target=target,
                               status="ready", reason="", detail={**row.detail, "recovery_of": row.id},
                               fingerprint=row.fingerprint)
        try:
            photo = db.get(Photo, row.photo_id)
            if not photo or photo.owner_id != user.id or canonical(photo.file_path) != canonical(source):
                raise ValueError("影像位置已被后续操作改变")
            if undo:
                if file_fingerprint(source) != row.detail.get("output_fingerprint"):
                    raise ValueError("文件已被修改")
                item.fingerprint = fingerprint(photo)
                item.detail = {"recovery_of": row.id}
            if original.kind in {"rename", "organize"} and os.path.lexists(target):
                raise ValueError("恢复/重试目标已占用，不会覆盖")
            if not undo and fingerprint(photo) != row.fingerprint:
                raise ValueError("源影像已变化，请重新预览")
            ready += 1
        except (ValueError, OSError) as error:
            item.status, item.reason = "skipped", str(error)
        db.add(item)
    plan.summary = {"total": len(rows), "ready": ready, "skipped": len(rows) - ready}
    db.commit()
    return plan
