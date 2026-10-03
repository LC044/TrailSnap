"""Daily-frame business rules. All reads and mutations are owner scoped."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import date, datetime, time, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException
from sqlalchemy import Date, func, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.db.models.daily_frame import DailyFrame, DailyFrameCalendar, DailyFrameWork
from app.db.models.photo import FileType, Photo
from app.db.models.task import INTERACTIVE_TASK_PRIORITY, Task, TaskStatus, TaskType
from app.schemas.daily_frame import CalendarSettings, FilmCreate, FilmSettings, FrameSelection


def timezone(value: str) -> ZoneInfo:
    try:
        return ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise HTTPException(400, "请选择有效的 IANA 时区，例如 Asia/Shanghai") from exc


def today(calendar: DailyFrameCalendar) -> date:
    return datetime.now(timezone(calendar.timezone)).date()


def profile(db: Session, owner_id: UUID) -> DailyFrameCalendar:
    row = db.get(DailyFrameCalendar, owner_id)
    if row is None:
        raise HTTPException(409, "请先初始化一日一帧日历")
    return row


def settings(db: Session, owner_id: UUID) -> dict:
    from app.service.daily_frame_render import capabilities
    row = db.get(DailyFrameCalendar, owner_id)
    return {"initialized": row is not None, "timezone": row.timezone if row else None,
            "locked": bool(row and row.locked), "revision": row.revision if row else 0,
            "today": today(row).isoformat() if row else None, "export": capabilities()}


def initialize(db: Session, owner_id: UUID, payload: CalendarSettings) -> dict:
    timezone(payload.timezone)
    row = db.get(DailyFrameCalendar, owner_id)
    if row is None:
        db.add(DailyFrameCalendar(owner_id=owner_id, timezone=payload.timezone))
        try:
            db.commit()
        except IntegrityError:
            # First-use requests can arrive concurrently from the home card and page.
            db.rollback()
        return settings(db, owner_id)
    lock_calendar(db, owner_id)
    db.refresh(row)
    if row.locked and row.timezone != payload.timezone:
        raise HTTPException(409, "已有选帧，日历时区已固定")
    row.timezone = payload.timezone
    db.commit()
    return settings(db, owner_id)


def lock_calendar(db: Session, owner_id: UUID) -> DailyFrameCalendar:
    # An actual UPDATE also serializes writers on SQLite, where FOR UPDATE is ignored.
    result = db.execute(update(DailyFrameCalendar).where(DailyFrameCalendar.owner_id == owner_id)
                        .values(revision=DailyFrameCalendar.revision + 1))
    if result.rowcount != 1:
        raise HTTPException(409, "请先初始化一日一帧日历")
    row = profile(db, owner_id)
    db.refresh(row)
    return row


def check_range(start: date, end: date, calendar: DailyFrameCalendar, *, allow_future=False) -> None:
    if start.year < 1900 or end.year > 2200 or end < start or (end - start).days >= 366:
        raise HTTPException(400, "请选择最多 366 天的有效日期范围")
    if not allow_future and end > today(calendar):
        raise HTTPException(400, "不能选择未来日期")


def photo_day(photo: Photo, calendar: DailyFrameCalendar) -> date | None:
    if not photo.photo_time:
        return None
    value = photo.photo_time
    return value.astimezone(timezone(calendar.timezone)).date() if value.tzinfo else value.date()


def photo_query(db: Session, owner_id: UUID, start: date, end: date):
    # Existing photo_time is stored as local wall time (DateTime without timezone).
    return db.query(Photo).filter(Photo.owner_id == owner_id, Photo.is_deleted.is_(False),
                                 Photo.photo_time >= datetime.combine(start, time.min),
                                 Photo.photo_time < datetime.combine(end + timedelta(days=1), time.min))


def owned_photo(db: Session, owner_id: UUID, photo_id: UUID | None) -> Photo | None:
    if photo_id is None:
        return None
    return db.query(Photo).filter(Photo.id == photo_id, Photo.owner_id == owner_id,
                                 Photo.is_deleted.is_(False)).first()


def source_path(photo: Photo | None, mode: str) -> tuple[str | None, str | None]:
    if photo is None:
        return None, "素材已删除或不可访问"
    if not photo.file_path or not os.path.isfile(photo.file_path):
        return None, "源文件暂时不可读取，请检查图库连接"
    if mode == "motion":
        if photo.file_type == FileType.live_photo:
            from app.service.storage import get_live_photo_vide
            path = get_live_photo_vide(photo.file_path)
            if not path or not os.path.isfile(path):
                return None, "动态文件不可用，可更换为静态照片"
            return path, None
        if photo.file_type != FileType.video:
            return None, "这张照片没有动态片段"
    elif photo.file_type == FileType.video:
        return None, "视频需要选择动态片段"
    return photo.file_path, None


def serialize_photo(photo: Photo) -> dict:
    path, error = source_path(photo, "motion" if photo.file_type == FileType.video else "still")
    motion_available = False
    if photo.file_type in (FileType.video, FileType.live_photo):
        motion_available = source_path(photo, "motion")[1] is None
    return {"id": str(photo.id), "photo_time": photo.photo_time.isoformat() if photo.photo_time else None,
            "file_type": photo.file_type.value, "duration": photo.duration or 0,
            "available": path is not None, "reason": error, "has_motion": motion_available}


def serialize_frame(db: Session, row: DailyFrame, calendar: DailyFrameCalendar,
                    photo: Photo | None = None, *, loaded=False) -> dict:
    photo = photo if loaded else owned_photo(db, row.owner_id, row.photo_id)
    if photo is not None and (photo.owner_id != row.owner_id or photo.is_deleted):
        photo = None
    _, reason = source_path(photo, row.mode)
    available = not row.removed and reason is None
    return {"day": row.day.isoformat(), "photo_id": str(row.photo_id) if photo else None,
            "mode": row.mode, "start_seconds": row.start_seconds, "caption": row.caption,
            "version": row.version, "removed": row.removed, "available": available,
            "reason": reason if not row.removed else None,
            "date_changed": bool(photo and photo_day(photo, calendar) != row.day),
            "photo": serialize_photo(photo) if photo else None}


def frame(db: Session, owner_id: UUID, day: date) -> dict:
    calendar = profile(db, owner_id)
    row = db.query(DailyFrame).filter_by(owner_id=owner_id, day=day).first()
    return serialize_frame(db, row, calendar) if row else {"day": day.isoformat(), "version": 0, "removed": True}


def calendar_range(db: Session, owner_id: UUID, start: date, end: date) -> dict:
    calendar = profile(db, owner_id)
    check_range(start, end, calendar, allow_future=True)
    counts = {str(day): count for day, count in photo_query(db, owner_id, start, end)
              .with_entities(func.date(Photo.photo_time, type_=Date), func.count(Photo.id))
              .group_by(func.date(Photo.photo_time)).all()}
    rows = db.query(DailyFrame).filter(DailyFrame.owner_id == owner_id, DailyFrame.day >= start,
                                      DailyFrame.day <= end).all()
    photo_ids = [row.photo_id for row in rows if row.photo_id and not row.removed]
    photos = {p.id: p for p in db.query(Photo).filter(Photo.id.in_(photo_ids), Photo.owner_id == owner_id,
                                                    Photo.is_deleted.is_(False)).all()} if photo_ids else {}
    frames = {row.day.isoformat(): serialize_frame(db, row, calendar, photos.get(row.photo_id), loaded=True)
              for row in rows}
    days = []
    current = start
    now = today(calendar)
    while current <= end:
        key = current.isoformat()
        days.append({"day": key, "candidate_count": counts.get(key, 0), "future": current > now,
                     "frame": frames.get(key)})
        current += timedelta(days=1)
    return {"timezone": calendar.timezone, "today": now.isoformat(), "revision": calendar.revision, "days": days}


def candidates(db: Session, owner_id: UUID, day: date, skip: int, limit: int, kind: str = "all") -> dict:
    calendar = profile(db, owner_id)
    check_range(day, day, calendar)
    query = photo_query(db, owner_id, day, day)
    if kind == "still":
        query = query.filter(Photo.file_type != FileType.video)
    elif kind == "motion":
        query = query.filter(Photo.file_type.in_([FileType.video, FileType.live_photo]))
    total = query.count()
    rows = query.order_by(Photo.photo_time, Photo.id).offset(skip).limit(limit).all()
    return {"items": [serialize_photo(row) for row in rows], "total": total}


def validate_selection(db: Session, owner_id: UUID, day: date, payload: FrameSelection,
                       calendar: DailyFrameCalendar) -> Photo:
    check_range(day, day, calendar)
    photo = owned_photo(db, owner_id, payload.photo_id)
    if photo is None:
        raise HTTPException(404, "素材不存在")
    existing = db.query(DailyFrame).filter_by(owner_id=owner_id, day=day).first()
    # Date corrections don't prevent editing the already-selected source.
    if photo_day(photo, calendar) != day and not (
        existing and not existing.removed and existing.photo_id == photo.id
    ):
        raise HTTPException(400, "请选择在这一天拍摄的素材")
    path, reason = source_path(photo, payload.mode)
    if reason:
        raise HTTPException(400, reason)
    if payload.mode == "still" and payload.start_seconds != 0:
        raise HTTPException(400, "静态照片的片段起点必须为 0")
    if payload.mode == "motion":
        from app.service.daily_frame_render import probe_duration
        duration = probe_duration(path)
        if duration is None:
            raise HTTPException(400, "动态素材无法读取，请重试或更换素材")
        if payload.start_seconds > max(0, duration - 1) + 0.001:
            raise HTTPException(400, "一秒片段超出素材时长，请调整起点")
    return photo


def save(db: Session, owner_id: UUID, day: date, payload: FrameSelection, *, only_empty=False) -> dict:
    calendar = lock_calendar(db, owner_id)
    row = db.query(DailyFrame).filter_by(owner_id=owner_id, day=day).first()
    actual_version = row.version if row else 0
    if payload.version != actual_version or (only_empty and row and not row.removed):
        raise HTTPException(409, "这一天已在另一处更新，请刷新后再选择")
    validate_selection(db, owner_id, day, payload, calendar)
    if row is None:
        row = DailyFrame(owner_id=owner_id, day=day)
        db.add(row)
    row.photo_id, row.mode = payload.photo_id, payload.mode
    row.start_seconds, row.caption = payload.start_seconds, payload.caption
    row.version, row.removed = actual_version + 1, False
    calendar.locked = True
    db.commit()
    db.refresh(row)
    return serialize_frame(db, row, calendar)


def remove(db: Session, owner_id: UUID, day: date, version: int) -> dict:
    calendar = lock_calendar(db, owner_id)
    row = db.query(DailyFrame).filter_by(owner_id=owner_id, day=day).first()
    if not row or row.removed or row.version != version:
        raise HTTPException(409, "这一天已在另一处更新，请刷新")
    row.removed = True
    row.version += 1
    db.commit()
    return serialize_frame(db, row, calendar)


def undo_remove(db: Session, owner_id: UUID, day: date, version: int) -> dict:
    calendar = lock_calendar(db, owner_id)
    row = db.query(DailyFrame).filter_by(owner_id=owner_id, day=day).first()
    if not row or not row.removed or row.version != version or not row.photo_id:
        raise HTTPException(409, "这一天已变化，无法撤销")
    # Restore the prior date even if its source's timestamp was subsequently corrected.
    if source_path(owned_photo(db, owner_id, row.photo_id), row.mode)[1]:
        raise HTTPException(400, "原素材已不可用，请重新选择")
    row.removed = False
    row.version += 1
    db.commit()
    return serialize_frame(db, row, calendar)


def suggestions(db: Session, owner_id: UUID, start: date, end: date) -> dict:
    calendar = profile(db, owner_id)
    check_range(start, end, calendar, allow_future=True)
    if start.replace(day=1) != end.replace(day=1):
        raise HTTPException(400, "批量填充只能选择一个月份")
    existing = {r.day: r for r in db.query(DailyFrame).filter(DailyFrame.owner_id == owner_id,
                DailyFrame.day >= start, DailyFrame.day <= end).all()}
    selected = {}
    # Iterate in chunks rather than loading a whole month's original metadata.
    query = photo_query(db, owner_id, start, min(end, today(calendar))).options(joinedload(Photo.image_description))
    for photo in query.order_by(Photo.photo_time, Photo.id).yield_per(250):
        day = photo_day(photo, calendar)
        if day in existing and not existing[day].removed:
            continue
        mode = "motion" if photo.file_type == FileType.video else "still"
        if photo.file_type == FileType.live_photo and source_path(photo, "motion")[1] is None:
            mode = "motion"
        if source_path(photo, mode)[1]:
            continue
        score = photo.image_description.quality_score if photo.image_description else None
        rank = ({FileType.image: 0, FileType.live_photo: 1, FileType.video: 2}[photo.file_type],
                -(score if score is not None else -1), photo.photo_time, str(photo.id))
        if day not in selected or rank < selected[day][0]:
            selected[day] = (rank, photo, mode)
    return {"items": [{"day": day.isoformat(), "photo_id": str(p.id), "photo": serialize_photo(p),
                       "mode": mode, "start_seconds": 0, "caption": "",
                       "version": existing[day].version if day in existing else 0}
                      for day, (_, p, mode) in sorted(selected.items())],
            "preserved": sum(not r.removed for r in existing.values())}


def fingerprint(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
                          .encode("utf-8")).hexdigest()


def composition(db: Session, owner_id: UUID, payload: FilmSettings) -> dict:
    calendar = profile(db, owner_id)
    check_range(payload.start_date, payload.end_date, calendar)
    listing = calendar_range(db, owner_id, payload.start_date, payload.end_date)
    valid, invalid = [], []
    for day in listing["days"]:
        row = day["frame"]
        if row is None or row["removed"]:
            continue
        if not row["available"]:
            invalid.append({"day": row["day"], "reason": row["reason"]})
            continue
        valid.append({key: row[key] for key in ("day", "photo_id", "mode", "start_seconds", "caption", "version")})
    snapshot = {"settings": payload.model_dump(mode="json"), "timezone": calendar.timezone, "frames": valid}
    return {"snapshot": snapshot, "fingerprint": fingerprint(snapshot), "invalid": invalid,
            "empty_days": len(listing["days"]) - len(valid) - len(invalid), "duration": len(valid)}


def owned_work(db: Session, owner_id: UUID, work_id: UUID) -> DailyFrameWork:
    work = db.query(DailyFrameWork).filter(DailyFrameWork.id == work_id, DailyFrameWork.owner_id == owner_id,
                                         DailyFrameWork.deleted_at.is_(None)).first()
    if work is None:
        raise HTTPException(404, "作品不存在")
    return work


def create_work(db: Session, owner_id: UUID, payload: FilmCreate) -> DailyFrameWork:
    from app.service.daily_frame_render import capabilities
    caps = capabilities()
    if not caps["available"]:
        raise HTTPException(503, caps["reason"])
    lock_calendar(db, owner_id)
    film_settings = FilmSettings(**payload.model_dump(exclude={"fingerprint", "is_preview"}))
    plan = composition(db, owner_id, film_settings)
    if plan["fingerprint"] != payload.fingerprint:
        raise HTTPException(409, "选帧已变化，请更新预览后重新生成")
    if plan["invalid"] and not payload.skip_invalid:
        raise HTTPException(400, "请更换失效素材，或明确选择本次跳过")
    if not plan["duration"]:
        raise HTTPException(400, "先选至少一个有效瞬间")
    key = fingerprint({"snapshot": plan["snapshot"], "preview": payload.is_preview})
    work = db.query(DailyFrameWork).filter_by(owner_id=owner_id, fingerprint=key).first()
    if work and work.deleted_at is None:
        task = db.get(Task, work.task_id) if work.task_id else None
        if work.status == "ready" and work.output_path and os.path.isfile(work.output_path):
            db.commit()
            return work
        if work.status in ("queued", "processing") and task and task.status in ("pending", "processing"):
            db.commit()
            return work
    if work is None:
        work = DailyFrameWork(id=uuid4(), owner_id=owner_id, fingerprint=key, generation=0,
                              snapshot=plan["snapshot"], is_preview=payload.is_preview)
        db.add(work)
    work.deleted_at, work.status, work.error = None, "queued", None
    work.processed_items, work.output_path = 0, None
    work.generation += 1
    task = Task(id=uuid4(), type=TaskType.RENDER_DAILY_FRAME.value, owner_id=owner_id,
                priority=INTERACTIVE_TASK_PRIORITY, status=TaskStatus.PENDING.value,
                total_items=plan["duration"], payload={"work_id": str(work.id), "generation": work.generation})
    db.add(task)
    db.flush()
    work.task_id = task.id
    db.commit()
    from app.service.task_manager import TaskManager
    TaskManager.get_instance().start_worker_if_needed()
    return work


def serialize_work(db: Session, work: DailyFrameWork) -> dict:
    task = db.get(Task, work.task_id) if work.task_id else None
    status = work.status
    if status in ("processing", "queued") and not task:
        status = "failed"
    if status in ("processing", "queued") and task:
        status = {"pending": "queued", "processing": "processing", "failed": "failed", "cancelled": "cancelled"}
        status = status.get(task.status, work.status)
    available = work.status == "ready" and bool(work.output_path and os.path.isfile(work.output_path))
    if work.status == "ready" and not available:
        status = "missing"
    settings = work.snapshot["settings"]
    changed = False
    if work.status == "ready":
        try:
            current = composition(db, work.owner_id, FilmSettings(**settings))["snapshot"]
            changed = current != work.snapshot
        except HTTPException:
            changed = True
    # Snapshot photo ids/metadata are not exposed after source deletion.
    return {"id": str(work.id), "status": status, "is_preview": work.is_preview,
            "settings": settings, "duration": len(work.snapshot["frames"]),
            "days": [f["day"] for f in work.snapshot["frames"]],
            "processed_items": work.processed_items, "error": work.error or ("生成失败，请重试" if status == "failed" else None),
            "file_available": available, "calendar_changed": changed, "created_at": work.created_at.isoformat()}


def stop_work(db: Session, owner_id: UUID, work_id: UUID, *, delete=False) -> None:
    work = owned_work(db, owner_id, work_id)
    statement = update(DailyFrameWork).where(DailyFrameWork.id == work_id, DailyFrameWork.owner_id == owner_id,
                                             DailyFrameWork.deleted_at.is_(None))
    if not delete:
        statement = statement.where(DailyFrameWork.status.in_(["queued", "processing"]))
    values = {"status": "deleted" if delete else "cancelled"}
    if delete:
        values["deleted_at"] = datetime.now()
    result = db.execute(statement.values(**values).returning(DailyFrameWork.output_path)).first()
    if result is None:
        raise HTTPException(409, "作品状态已变化，请刷新")
    output = result[0]
    if work.task_id:
        db.query(Task).filter(Task.id == work.task_id, Task.owner_id == owner_id,
                              Task.status.in_(["pending", "processing"])).update({"status": "cancelled"})
    db.execute(update(DailyFrameWork).where(DailyFrameWork.id == work_id).values(output_path=None))
    db.commit()
    if output:
        from app.service.daily_frame_render import remove_output
        remove_output(owner_id, output)


def retry_work(db: Session, owner_id: UUID, work_id: UUID) -> DailyFrameWork:
    from app.service.daily_frame_render import capabilities
    if not capabilities()["available"]:
        raise HTTPException(503, capabilities()["reason"])
    lock_calendar(db, owner_id)
    work = owned_work(db, owner_id, work_id)
    if work.status in ("queued", "processing"):
        task = db.get(Task, work.task_id) if work.task_id else None
        if task and task.status in ("pending", "processing"):
            raise HTTPException(409, "作品正在生成")
    if work.status == "ready" and work.output_path and os.path.isfile(work.output_path):
        raise HTTPException(409, "作品已经生成，可直接下载")
    for item in work.snapshot["frames"]:
        reason = source_path(owned_photo(db, owner_id, UUID(item["photo_id"])), item["mode"])[1]
        if reason:
            raise HTTPException(400, f"{item['day']}：{reason}，请返回日历更换后重新制作")
    work.generation += 1
    work.status, work.error, work.processed_items = "queued", None, 0
    task = Task(id=uuid4(), type=TaskType.RENDER_DAILY_FRAME.value, owner_id=owner_id,
                priority=INTERACTIVE_TASK_PRIORITY, status="pending", total_items=len(work.snapshot["frames"]),
                payload={"work_id": str(work.id), "generation": work.generation})
    db.add(task)
    db.flush()
    work.task_id = task.id
    db.commit()
    from app.service.task_manager import TaskManager
    TaskManager.get_instance().start_worker_if_needed()
    return work
