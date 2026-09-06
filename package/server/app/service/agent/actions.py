"""Confirmed and reversible write operations for the album Agent."""

from datetime import datetime, timedelta, timezone
from typing import Iterable
from uuid import UUID

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.db.models.agent import AgentSession
from app.db.models.agent_action import AgentActionPlan
from app.db.models.ai_artifact import AIArtifact
from app.db.models.album import Album, AlbumPhoto
from app.db.models.image_description import ImageDescription
from app.db.models.photo import FileType, ImageType, Photo
from app.db.models.tag import PhotoTag, PhotoTagRelation
from app.db.models.task import INTERACTIVE_TASK_PRIORITY, Task, TaskStatus, TaskType


MAX_PLAN_PHOTOS = 500
MAX_PLAN_TAGS = 10
PLAN_TTL_DAYS = 7
MAX_REPAIR_ITEMS = 100
MAX_METADATA_REPAIR_PHOTOS = 500


def _uuid(value) -> UUID:
    try:
        return UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError("无效的 ID") from exc


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _owned_photos(db: Session, user_id, photo_ids: Iterable) -> list[Photo]:
    ids = list(dict.fromkeys(_uuid(value) for value in photo_ids))
    if not ids or len(ids) > MAX_PLAN_PHOTOS:
        raise ValueError(f"照片数量必须在 1 到 {MAX_PLAN_PHOTOS} 之间")
    rows = db.query(Photo).filter(
        Photo.id.in_(ids), Photo.owner_id == _uuid(user_id), Photo.is_deleted.is_(False)
    ).all()
    if len(rows) != len(ids):
        raise ValueError("部分照片不存在或不属于当前用户")
    by_id = {row.id: row for row in rows}
    return [by_id[item] for item in ids]


def _normalize_tags(tags: Iterable[str] | None) -> list[str]:
    result = []
    for value in tags or []:
        name = str(value).strip()
        if name and name not in result:
            if len(name) > 50:
                raise ValueError("标签名称不能超过 50 个字符")
            result.append(name)
    if len(result) > MAX_PLAN_TAGS:
        raise ValueError(f"一次最多添加 {MAX_PLAN_TAGS} 个标签")
    return result


def get_owned_plan(db: Session, user_id, plan_id, for_update: bool = False) -> AgentActionPlan | None:
    try:
        plan_uuid = _uuid(plan_id)
    except ValueError:
        return None
    query = db.query(AgentActionPlan).filter(
        AgentActionPlan.id == plan_uuid, AgentActionPlan.user_id == _uuid(user_id)
    )
    if for_update:
        query = query.with_for_update()
    return query.first()


def list_owned_plans(db: Session, user_id, session_id=None, status=None, limit: int = 50):
    expire_stale_plans(db, user_id)
    query = db.query(AgentActionPlan).filter(AgentActionPlan.user_id == _uuid(user_id))
    if session_id:
        query = query.filter(AgentActionPlan.session_id == _uuid(session_id))
    if status:
        query = query.filter(AgentActionPlan.status == status)
    return query.order_by(AgentActionPlan.created_at.desc()).limit(min(max(limit, 1), 100)).all()


def expire_stale_plans(db: Session, user_id) -> int:
    """Persist expiry so history and execution observe the same terminal state."""
    now = datetime.now(timezone.utc)
    rows = db.query(AgentActionPlan).filter(
        AgentActionPlan.user_id == _uuid(user_id),
        AgentActionPlan.status == "proposed",
        AgentActionPlan.expires_at.isnot(None),
        AgentActionPlan.expires_at <= now,
    ).all()
    for row in rows:
        row.status = "expired"
        row.error_message = "操作计划已过期，请重新生成"
    if rows:
        db.commit()
    return len(rows)


def mark_plan_failed(db: Session, user_id, plan_id, message: str) -> AgentActionPlan | None:
    """Record a failed confirmation after the caller has rolled back mutations."""
    plan = get_owned_plan(db, user_id, plan_id, for_update=True)
    if not plan or plan.status != "proposed":
        return plan
    plan.status = "failed"
    plan.failed_at = datetime.now(timezone.utc)
    plan.attempt_count = int(plan.attempt_count or 0) + 1
    plan.error_message = str(message)[:2000]
    db.commit()
    db.refresh(plan)
    return plan


def propose_album_plan(
    db: Session,
    user_id,
    session_id,
    name: str,
    description: str | None,
    photo_ids: list,
    cover_photo_id=None,
    tags: list[str] | None = None,
    album_id=None,
    artifact_id=None,
    summary: str | None = None,
) -> AgentActionPlan:
    owner_id = _uuid(user_id)
    clean_name = str(name).strip()
    if not clean_name or len(clean_name) > 100:
        raise ValueError("相册名称不能为空且不能超过 100 个字符")
    photos = _owned_photos(db, owner_id, photo_ids)
    selected_ids = [photo.id for photo in photos]
    cover_id = _uuid(cover_photo_id) if cover_photo_id else selected_ids[0]
    if cover_id not in set(selected_ids):
        raise ValueError("封面必须来自计划收录的照片")

    target_album = None
    if album_id:
        target_album = db.query(Album).filter(Album.id == _uuid(album_id), Album.owner_id == owner_id).first()
        if not target_album:
            raise ValueError("目标相册不存在或无权修改")
        if target_album.type != "user":
            raise ValueError("Agent P1 只支持整理普通相册")

    if session_id:
        session = db.query(AgentSession).filter(AgentSession.id == _uuid(session_id), AgentSession.user_id == owner_id).first()
        if not session:
            raise ValueError("会话不存在或无权访问")

    artifact = None
    if artifact_id:
        artifact = db.query(AIArtifact).filter(
            AIArtifact.id == _uuid(artifact_id), AIArtifact.user_id == owner_id
        ).first()
        if not artifact:
            raise ValueError("旅行日志不存在或无权访问")

    clean_tags = _normalize_tags(tags)
    sample = [{
        "photo_id": str(photo.id),
        "thumbnail_url": f"/api/medias/{photo.id}/thumbnail?size=small",
        "photo_time": photo.photo_time.isoformat() if photo.photo_time else None,
    } for photo in photos[:12]]
    operations = {
        "album_id": str(target_album.id) if target_album else None,
        "name": clean_name,
        "description": description,
        "photo_ids": [str(value) for value in selected_ids],
        "cover_photo_id": str(cover_id),
        "tags": clean_tags,
        "artifact_id": str(artifact.id) if artifact else None,
    }
    preview = {
        "mode": "update" if target_album else "create",
        "album_name": clean_name,
        "current_album_name": target_album.name if target_album else None,
        "photo_count": len(selected_ids),
        "cover_photo_id": str(cover_id),
        "tags": clean_tags,
        "artifact_id": str(artifact.id) if artifact else None,
        "artifact_title": artifact.title if artifact else None,
        "artifact_url": f"/agent/artifacts/{artifact.id}" if artifact else None,
        "sample_photos": sample,
        "notice": "只创建或更新相册关系和标签，不删除、移动或重命名原始照片。",
    }
    row = AgentActionPlan(
        user_id=owner_id,
        session_id=_uuid(session_id) if session_id else None,
        plan_type="album_organize",
        title=f"整理相册：{clean_name}",
        summary=(summary or f"将 {len(selected_ids)} 张照片整理到“{clean_name}”并添加 {len(clean_tags)} 个标签。"),
        operations=operations,
        preview=preview,
        status="proposed",
        expires_at=datetime.now(timezone.utc) + timedelta(days=PLAN_TTL_DAYS),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def find_album_repair_candidates(db: Session, user_id, album_id=None) -> list[dict]:
    """Find deterministic, reversible album-structure repairs without mutating data."""
    owner_id = _uuid(user_id)
    album_query = db.query(Album).filter(Album.owner_id == owner_id, Album.type == "user")
    if album_id:
        album_query = album_query.filter(Album.id == _uuid(album_id))
    albums = album_query.order_by(Album.create_time.desc()).all()
    if album_id and not albums:
        raise ValueError("相册不存在或无权访问")

    album_ids = [album.id for album in albums]
    count_by_album = dict(
        db.query(AlbumPhoto.album_id, func.count(AlbumPhoto.id))
        .join(Photo, Photo.id == AlbumPhoto.photo_id)
        .filter(
            AlbumPhoto.album_id.in_(album_ids),
            Photo.owner_id == owner_id,
            Photo.is_deleted.is_(False),
        )
        .group_by(AlbumPhoto.album_id)
        .all()
    ) if album_ids else {}
    albums_with_valid_cover = {
        row[0] for row in (
            db.query(Album.id)
            .join(AlbumPhoto, AlbumPhoto.album_id == Album.id)
            .join(Photo, Photo.id == AlbumPhoto.photo_id)
            .filter(
                Album.id.in_(album_ids),
                AlbumPhoto.photo_id == Album.cover_id,
                Photo.owner_id == owner_id,
                Photo.is_deleted.is_(False),
            )
            .all()
        )
    } if album_ids else set()

    candidates: list[dict] = []
    for album in albums:
        actual_count = int(count_by_album.get(album.id, 0))
        stored_count = int(album.num_photos or 0)
        if stored_count != actual_count:
            candidates.append({
                "id": f"album_count:{album.id}",
                "kind": "album_count",
                "album_id": str(album.id),
                "album_name": album.name,
                "before": stored_count,
                "after": actual_count,
                "label": f"修正“{album.name}”的照片计数：{stored_count} → {actual_count}",
            })

        cover_invalid = bool(album.cover_id and album.id not in albums_with_valid_cover)
        if actual_count and (not album.cover_id or cover_invalid):
            recommended = (
                db.query(Photo)
                .join(AlbumPhoto, AlbumPhoto.photo_id == Photo.id)
                .outerjoin(ImageDescription, ImageDescription.photo_id == Photo.id)
                .filter(
                    AlbumPhoto.album_id == album.id,
                    Photo.owner_id == owner_id,
                    Photo.is_deleted.is_(False),
                )
                .order_by(
                    func.coalesce(ImageDescription.quality_score, 0).desc(),
                    func.coalesce(ImageDescription.memory_score, 0).desc(),
                    Photo.photo_time.desc(),
                    Photo.id,
                )
                .first()
            )
            if not recommended:
                continue
            candidates.append({
                "id": f"album_cover:{album.id}",
                "kind": "album_cover",
                "album_id": str(album.id),
                "album_name": album.name,
                "before": str(album.cover_id) if album.cover_id else None,
                "after": str(recommended.id),
                "thumbnail_url": f"/api/medias/{recommended.id}/thumbnail?size=small",
                "reason": "当前封面不属于相册" if cover_invalid else "当前没有封面",
                "label": f"为“{album.name}”设置推荐封面",
            })
        if len(candidates) >= MAX_REPAIR_ITEMS:
            break
    return candidates[:MAX_REPAIR_ITEMS]


def _repair_preview(candidates: list[dict], selected_ids: list[str]) -> dict:
    selected_set = set(selected_ids)
    selected = [item for item in candidates if item["id"] in selected_set]
    return {
        "mode": "repair",
        "repair_count": len(selected),
        "candidate_count": len(candidates),
        "affected_album_count": len({item["album_id"] for item in selected}),
        "repairs": candidates,
        "selected_repair_ids": [item["id"] for item in selected],
        "notice": "只修正相册计数和封面引用，不删除、移动、重命名或改写原始照片。执行后可撤销。",
    }


def find_album_metadata_repair_candidates(db: Session, user_id, album_id=None) -> list[dict]:
    """Find bounded, owner-scoped metadata jobs that can be safely queued."""
    owner_id = _uuid(user_id)
    album = None
    if album_id:
        album = db.query(Album).filter(
            Album.id == _uuid(album_id), Album.owner_id == owner_id
        ).first()
        if not album:
            raise ValueError("相册不存在或无权访问")

    def scoped_query():
        query = db.query(Photo).filter(Photo.owner_id == owner_id, Photo.is_deleted.is_(False))
        if album:
            query = query.join(AlbumPhoto, AlbumPhoto.photo_id == Photo.id).filter(AlbumPhoto.album_id == album.id)
        return query

    description_query = (
        scoped_query()
        .outerjoin(ImageDescription, ImageDescription.photo_id == Photo.id)
        .filter(
            Photo.file_type != FileType.video,
            or_(Photo.image_type.is_(None), Photo.image_type != ImageType.SCREENSHOT),
            or_(ImageDescription.id.is_(None), ImageDescription.description.is_(None), ImageDescription.description == ""),
        )
    )
    hash_query = scoped_query().filter(or_(Photo.md5.is_(None), Photo.md5 == ""))

    candidates = []
    for key, kind, label, query in (
        ("metadata_description", "visual_description", "生成缺失的 AI 视觉描述", description_query),
        ("metadata_hash", "file_hash", "计算缺失的文件指纹", hash_query),
    ):
        count = query.order_by(None).count()
        if not count:
            continue
        rows = query.order_by(Photo.photo_time.desc(), Photo.id).limit(MAX_METADATA_REPAIR_PHOTOS).all()
        candidates.append({
            "id": key,
            "kind": kind,
            "label": label,
            "count": count,
            "queued_count": len(rows),
            "truncated": count > len(rows),
            "photo_ids": [str(photo.id) for photo in rows],
            "sample_photos": [{
                "photo_id": str(photo.id),
                "thumbnail_url": f"/api/medias/{photo.id}/thumbnail?size=small",
            } for photo in rows[:8]],
        })
    return candidates


def _metadata_repair_preview(candidates: list[dict], selected_ids: list[str]) -> dict:
    selected_set = set(selected_ids)
    selected = [item for item in candidates if item["id"] in selected_set]
    samples = []
    seen_sample_ids = set()
    for item in selected:
        for sample in item.get("sample_photos") or []:
            if sample["photo_id"] not in seen_sample_ids and len(samples) < 12:
                samples.append(sample)
                seen_sample_ids.add(sample["photo_id"])
    return {
        "mode": "metadata_repair",
        "repair_count": len(selected),
        "candidate_count": len(candidates),
        "photo_count": sum(int(item.get("queued_count") or 0) for item in selected),
        "repairs": candidates,
        "selected_repair_ids": [item["id"] for item in selected],
        "sample_photos": samples,
        "reversible": False,
        "notice": f"确认后将创建后台任务；单类最多处理 {MAX_METADATA_REPAIR_PHOTOS} 张照片。不会删除、移动或重命名原始文件。AI 描述和文件指纹写入不可撤销，但可重新生成。",
    }


def propose_album_metadata_repair_plan(
    db: Session,
    user_id,
    session_id=None,
    album_id=None,
    repair_ids: list[str] | None = None,
    summary: str | None = None,
) -> AgentActionPlan:
    owner_id = _uuid(user_id)
    if session_id:
        session = db.query(AgentSession).filter(
            AgentSession.id == _uuid(session_id), AgentSession.user_id == owner_id
        ).first()
        if not session:
            raise ValueError("会话不存在或无权访问")
    candidates = find_album_metadata_repair_candidates(db, owner_id, album_id)
    if not candidates:
        raise ValueError("当前范围没有可批量补齐的 AI 描述或文件指纹")
    candidate_ids = [item["id"] for item in candidates]
    selected_ids = candidate_ids if repair_ids is None else list(dict.fromkeys(str(value) for value in repair_ids))
    if not selected_ids or not set(selected_ids).issubset(set(candidate_ids)):
        raise ValueError("修复项不存在或已不在当前体检范围")
    preview = _metadata_repair_preview(candidates, selected_ids)
    row = AgentActionPlan(
        user_id=owner_id,
        session_id=_uuid(session_id) if session_id else None,
        plan_type="album_metadata_repair",
        title="补齐相册 AI 数据" if not album_id else "补齐相册 AI 数据与文件指纹",
        summary=summary or f"准备为 {preview['photo_count']} 个照片处理项创建后台任务。",
        operations={"album_id": str(album_id) if album_id else None, "repairs": candidates, "selected_repair_ids": preview["selected_repair_ids"]},
        preview=preview,
        status="proposed",
        expires_at=datetime.now(timezone.utc) + timedelta(days=PLAN_TTL_DAYS),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def propose_album_repair_plan(
    db: Session,
    user_id,
    session_id=None,
    album_id=None,
    repair_ids: list[str] | None = None,
    summary: str | None = None,
) -> AgentActionPlan:
    owner_id = _uuid(user_id)
    if session_id:
        session = db.query(AgentSession).filter(
            AgentSession.id == _uuid(session_id), AgentSession.user_id == owner_id
        ).first()
        if not session:
            raise ValueError("会话不存在或无权访问")

    candidates = find_album_repair_candidates(db, owner_id, album_id)
    if not candidates:
        raise ValueError("当前范围没有可由 Agent 安全修复的相册结构问题")
    candidate_ids = [item["id"] for item in candidates]
    selected_ids = candidate_ids if repair_ids is None else list(dict.fromkeys(str(value) for value in repair_ids))
    if not selected_ids or not set(selected_ids).issubset(set(candidate_ids)):
        raise ValueError("修复项不存在或已不在当前体检范围")

    preview = _repair_preview(candidates, selected_ids)
    title = "修复相册结构" if not album_id else f"修复相册：{candidates[0]['album_name']}"
    row = AgentActionPlan(
        user_id=owner_id,
        session_id=_uuid(session_id) if session_id else None,
        plan_type="album_repair",
        title=title,
        summary=summary or f"准备修复 {preview['affected_album_count']} 个相册中的 {preview['repair_count']} 项结构问题。",
        operations={"repairs": candidates, "selected_repair_ids": preview["selected_repair_ids"]},
        preview=preview,
        status="proposed",
        expires_at=datetime.now(timezone.utc) + timedelta(days=PLAN_TTL_DAYS),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_repair_plan_selection(db: Session, user_id, plan_id, selected_repair_ids: list[str]) -> AgentActionPlan:
    plan = get_owned_plan(db, user_id, plan_id, for_update=True)
    if not plan:
        raise ValueError("操作计划不存在")
    if plan.status != "proposed":
        raise ValueError("只有待确认的修复计划可以调整")
    if plan.expires_at and _as_utc(plan.expires_at) <= datetime.now(timezone.utc):
        plan.status = "expired"
        plan.error_message = "操作计划已过期，请重新生成"
        db.commit()
        raise ValueError(plan.error_message)
    if plan.plan_type not in {"album_repair", "album_metadata_repair"}:
        raise ValueError("该计划不支持调整修复范围")
    candidates = (plan.operations or {}).get("repairs") or []
    candidate_ids = {item.get("id") for item in candidates}
    selected = list(dict.fromkeys(str(value) for value in selected_repair_ids))
    if not selected:
        raise ValueError("请至少选择一个修复项")
    if not set(selected).issubset(candidate_ids):
        raise ValueError("包含无效的修复项")
    plan.operations = {**(plan.operations or {}), "selected_repair_ids": selected}
    plan.preview = (
        _repair_preview(candidates, selected)
        if plan.plan_type == "album_repair"
        else _metadata_repair_preview(candidates, selected)
    )
    db.commit()
    db.refresh(plan)
    return plan


def _execute_album_repair(db: Session, owner_id: UUID, plan: AgentActionPlan) -> AgentActionPlan:
    operations = plan.operations or {}
    selected_ids = set(operations.get("selected_repair_ids") or [])
    repairs = [item for item in operations.get("repairs") or [] if item.get("id") in selected_ids]
    if not repairs:
        raise ValueError("修复计划没有选中的修复项")

    validated = []
    for repair in repairs:
        album = db.query(Album).filter(
            Album.id == _uuid(repair.get("album_id")), Album.owner_id == owner_id, Album.type == "user"
        ).first()
        if not album:
            raise ValueError("待修复相册不存在或不可修改")
        kind = repair.get("kind")
        if kind == "album_count":
            actual = (
                db.query(func.count(AlbumPhoto.id))
                .join(Photo, Photo.id == AlbumPhoto.photo_id)
                .filter(
                    AlbumPhoto.album_id == album.id,
                    Photo.owner_id == owner_id,
                    Photo.is_deleted.is_(False),
                )
                .scalar() or 0
            )
            if int(album.num_photos or 0) != int(repair.get("before")) or int(actual) != int(repair.get("after")):
                raise ValueError(f"“{album.name}”的照片计数已变化，请重新体检")
            validated.append((repair, album, int(repair["after"])))
        elif kind == "album_cover":
            current_cover = str(album.cover_id) if album.cover_id else None
            if current_cover != repair.get("before"):
                raise ValueError(f"“{album.name}”的封面已变化，请重新体检")
            target_id = _uuid(repair.get("after"))
            belongs = (
                db.query(AlbumPhoto.id)
                .join(Photo, Photo.id == AlbumPhoto.photo_id)
                .filter(
                    AlbumPhoto.album_id == album.id,
                    AlbumPhoto.photo_id == target_id,
                    Photo.owner_id == owner_id,
                    Photo.is_deleted.is_(False),
                )
                .first()
            )
            if not belongs:
                raise ValueError(f"“{album.name}”的推荐封面已不在相册中，请重新体检")
            validated.append((repair, album, target_id))
        else:
            raise ValueError("修复计划包含不支持的操作")

    undo_repairs = []
    for repair, album, value in validated:
        if repair["kind"] == "album_count":
            album.num_photos = value
        else:
            album.cover_id = value
        undo_repairs.append({
            "id": repair["id"], "kind": repair["kind"], "album_id": str(album.id),
            "before": repair.get("before"), "applied_after": repair.get("after"),
        })

    affected_ids = list(dict.fromkeys(item["album_id"] for item in undo_repairs))
    plan.undo_data = {"repairs": undo_repairs}
    plan.result = {
        "applied_repair_count": len(undo_repairs),
        "affected_album_count": len(affected_ids),
        "affected_album_ids": affected_ids,
    }
    plan.status = "executed"
    plan.attempt_count = int(plan.attempt_count or 0) + 1
    plan.error_message = None
    plan.executed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(plan)
    return plan


def _execute_album_metadata_repair(db: Session, owner_id: UUID, plan: AgentActionPlan) -> AgentActionPlan:
    operations = plan.operations or {}
    selected_ids = set(operations.get("selected_repair_ids") or [])
    repairs = [item for item in operations.get("repairs") or [] if item.get("id") in selected_ids]
    if not repairs:
        raise ValueError("修复计划没有选中的修复项")

    task_groups = []
    for repair in repairs:
        photo_ids = [_uuid(value) for value in repair.get("photo_ids") or []]
        photos = db.query(Photo).filter(
            Photo.id.in_(photo_ids), Photo.owner_id == owner_id, Photo.is_deleted.is_(False)
        ).all()
        by_id = {photo.id: photo for photo in photos}
        ordered_photos = [by_id[value] for value in photo_ids if value in by_id]
        if len(ordered_photos) != len(photo_ids):
            raise ValueError("部分待处理照片已不存在，请重新体检")

        album_id = operations.get("album_id")
        if album_id and photo_ids:
            member_count = db.query(func.count(AlbumPhoto.id)).filter(
                AlbumPhoto.album_id == _uuid(album_id), AlbumPhoto.photo_id.in_(photo_ids)
            ).scalar() or 0
            if int(member_count) != len(photo_ids):
                raise ValueError("相册照片范围已变化，请重新体检")

        # The plan may sit for days before confirmation. Recheck the desired
        # state so newly completed work is never overwritten or duplicated.
        if repair.get("kind") == "visual_description":
            described_ids = {
                value for (value,) in db.query(ImageDescription.photo_id).filter(
                    ImageDescription.photo_id.in_(photo_ids),
                    ImageDescription.description.isnot(None),
                    ImageDescription.description != "",
                ).all()
            }
            ordered_photos = [photo for photo in ordered_photos if photo.id not in described_ids]
        elif repair.get("kind") == "file_hash":
            ordered_photos = [photo for photo in ordered_photos if not photo.md5]

        task_ids: list[str] = []
        reused_count = 0
        if repair.get("kind") == "visual_description":
            active = db.query(Task).filter(
                Task.owner_id == owner_id,
                Task.type == TaskType.VISUAL_DESCRIPTION,
                Task.status.in_([TaskStatus.PENDING, TaskStatus.PROCESSING]),
            ).all()
            active_by_photo = {
                str((task.payload or {}).get("photo_id")): task for task in active
                if (task.payload or {}).get("photo_id")
            }
            for photo in ordered_photos:
                existing = active_by_photo.get(str(photo.id))
                if existing:
                    task_ids.append(str(existing.id))
                    reused_count += 1
                    continue
                task = Task(
                    type=TaskType.VISUAL_DESCRIPTION,
                    status=TaskStatus.PENDING,
                    priority=INTERACTIVE_TASK_PRIORITY,
                    owner_id=owner_id,
                    payload={
                        "photo_id": str(photo.id), "file_path": photo.file_path,
                        "force": True, "only_if_missing": True,
                        "source": "album_doctor", "action_plan_id": str(plan.id),
                    },
                )
                db.add(task)
                db.flush()
                task_ids.append(str(task.id))
        elif repair.get("kind") == "file_hash":
            task = Task(
                type=TaskType.FIND_DUPLICATE_PHOTOS,
                status=TaskStatus.PENDING,
                priority=INTERACTIVE_TASK_PRIORITY,
                owner_id=owner_id,
                payload={
                    "photo_ids": [str(photo.id) for photo in ordered_photos],
                    "source": "album_doctor", "action_plan_id": str(plan.id),
                },
            )
            db.add(task)
            db.flush()
            task_ids.append(str(task.id))
        else:
            raise ValueError("修复计划包含不支持的后台任务")
        task_groups.append({
            "kind": repair["kind"], "label": repair["label"],
            "photo_ids": [str(photo.id) for photo in ordered_photos],
            "task_ids": task_ids, "reused_task_count": reused_count,
        })

    plan.undo_data = None
    plan.result = {
        "task_ids": [task_id for group in task_groups for task_id in group["task_ids"]],
        "task_groups": task_groups,
        "queued_item_count": sum(len(group["photo_ids"]) for group in task_groups),
        "reversible": False,
    }
    plan.status = "executed"
    plan.attempt_count = int(plan.attempt_count or 0) + 1
    plan.error_message = None
    plan.executed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(plan)
    return plan


def get_metadata_repair_progress(db: Session, user_id, plan_id) -> dict:
    plan = get_owned_plan(db, user_id, plan_id)
    if not plan:
        raise ValueError("操作计划不存在")
    if plan.plan_type != "album_metadata_repair" or plan.status != "executed":
        raise ValueError("该计划没有可查询的后台修复进度")
    owner_id = _uuid(user_id)
    groups = (plan.result or {}).get("task_groups") or []
    all_task_ids = [_uuid(value) for group in groups for value in group.get("task_ids") or []]
    tasks = db.query(Task).filter(Task.id.in_(all_task_ids), Task.owner_id == owner_id).all() if all_task_ids else []
    task_by_id = {str(task.id): task for task in tasks}

    group_results = []
    total_items = completed_items = active_items = failed_items = 0
    for group in groups:
        photo_ids = [_uuid(value) for value in group.get("photo_ids") or []]
        total = len(photo_ids)
        if group.get("kind") == "visual_description":
            completed = db.query(func.count(func.distinct(ImageDescription.photo_id))).filter(
                ImageDescription.photo_id.in_(photo_ids),
                ImageDescription.description.isnot(None),
                ImageDescription.description != "",
            ).scalar() or 0
        else:
            completed = db.query(func.count(Photo.id)).filter(
                Photo.id.in_(photo_ids), Photo.owner_id == owner_id,
                Photo.md5.isnot(None), Photo.md5 != "",
            ).scalar() or 0
        group_tasks = [task_by_id[value] for value in group.get("task_ids") or [] if value in task_by_id]
        active = sum(task.status in {TaskStatus.PENDING, TaskStatus.PROCESSING, TaskStatus.PENDING.value, TaskStatus.PROCESSING.value} for task in group_tasks)
        failed = sum(task.status in {TaskStatus.FAILED, TaskStatus.FAILED.value} for task in group_tasks)
        remaining = max(0, total - int(completed))
        status = "completed" if remaining == 0 else "processing" if active else "needs_attention" if failed or not active else "pending"
        group_results.append({
            "kind": group.get("kind"), "label": group.get("label"), "status": status,
            "total_items": total, "completed_items": int(completed),
            "remaining_items": remaining, "active_tasks": active, "failed_tasks": failed,
        })
        total_items += total
        completed_items += int(completed)
        active_items += active
        failed_items += failed
    remaining_items = max(0, total_items - completed_items)
    status = "completed" if remaining_items == 0 else "processing" if active_items else "needs_attention"
    return {
        "plan_id": str(plan.id), "status": status,
        "total_items": total_items, "completed_items": completed_items,
        "remaining_items": remaining_items, "failed_tasks": failed_items,
        "progress_percent": round(completed_items * 100 / total_items) if total_items else 100,
        "groups": group_results,
        "recheck": {
            "missing_description": next((item["remaining_items"] for item in group_results if item["kind"] == "visual_description"), 0),
            "missing_hash": next((item["remaining_items"] for item in group_results if item["kind"] == "file_hash"), 0),
        },
    }


def execute_plan(db: Session, user_id, plan_id) -> AgentActionPlan:
    plan = get_owned_plan(db, user_id, plan_id, for_update=True)
    if not plan:
        raise ValueError("操作计划不存在")
    if plan.status != "proposed":
        raise ValueError("只有待确认的计划可以执行")
    now = datetime.now(timezone.utc)
    if plan.expires_at and _as_utc(plan.expires_at) <= now:
        plan.status = "expired"
        plan.error_message = "操作计划已过期，请重新生成"
        db.commit()
        raise ValueError(plan.error_message)
    owner_id = _uuid(user_id)
    if plan.plan_type == "album_repair":
        return _execute_album_repair(db, owner_id, plan)
    if plan.plan_type == "album_metadata_repair":
        return _execute_album_metadata_repair(db, owner_id, plan)
    if plan.plan_type != "album_organize":
        raise ValueError("不支持的操作计划类型")

    op = plan.operations or {}
    photos = _owned_photos(db, owner_id, op.get("photo_ids") or [])
    photo_ids = [photo.id for photo in photos]
    cover_id = _uuid(op.get("cover_photo_id"))
    if cover_id not in set(photo_ids):
        raise ValueError("封面照片不在计划范围内")

    album_id = op.get("album_id")
    created_album = not bool(album_id)
    if created_album:
        album = Album(
            name=op["name"], description=op.get("description"), type="user",
            owner_id=owner_id, cover_id=cover_id, num_photos=0,
        )
        db.add(album)
        db.flush()
        album_before = None
    else:
        album = db.query(Album).filter(Album.id == _uuid(album_id), Album.owner_id == owner_id).first()
        if not album or album.type != "user":
            raise ValueError("目标相册不存在或不可修改")
        album_before = {
            "name": album.name, "description": album.description,
            "cover_photo_id": str(album.cover_id) if album.cover_id else None,
        }
        album.name = op["name"]
        album.description = op.get("description")
        album.cover_id = cover_id

    existing_photo_ids = {
        value for (value,) in db.query(AlbumPhoto.photo_id).filter(
            AlbumPhoto.album_id == album.id, AlbumPhoto.photo_id.in_(photo_ids)
        ).all()
    }
    added_photo_ids = [value for value in photo_ids if value not in existing_photo_ids]
    db.add_all([AlbumPhoto(album_id=album.id, photo_id=value) for value in added_photo_ids])
    # SessionLocal intentionally disables autoflush in production. Flush the
    # association rows before deriving the persisted counter.
    db.flush()
    album.num_photos = db.query(func.count(AlbumPhoto.id)).filter(AlbumPhoto.album_id == album.id).scalar()

    tag_changes = []
    created_tag_ids = []
    for tag_name in _normalize_tags(op.get("tags")):
        tag = db.query(PhotoTag).filter(PhotoTag.tag_name == tag_name, PhotoTag.owner_id == owner_id).first()
        if not tag:
            tag = PhotoTag(tag_name=tag_name, type="custom", owner_id=owner_id)
            db.add(tag)
            db.flush()
            created_tag_ids.append(str(tag.id))
        existing = {
            relation.photo_id: relation for relation in db.query(PhotoTagRelation).filter(
                PhotoTagRelation.tag_id == tag.id, PhotoTagRelation.photo_id.in_(photo_ids)
            ).all()
        }
        for photo_id in photo_ids:
            relation = existing.get(photo_id)
            if relation and not relation.is_deleted:
                continue
            if relation:
                tag_changes.append({
                    "relation_id": relation.id, "created": False,
                    "was_deleted": True, "previous_confidence": relation.confidence,
                })
                relation.is_deleted = False
                relation.confidence = 1.0
            else:
                relation = PhotoTagRelation(photo_id=photo_id, tag_id=tag.id, confidence=1.0, is_deleted=False)
                db.add(relation)
                db.flush()
                tag_changes.append({"relation_id": relation.id, "created": True})

    plan.undo_data = {
        "created_album": created_album,
        "album_id": str(album.id),
        "album_before": album_before,
        "added_photo_ids": [str(value) for value in added_photo_ids],
        "tag_changes": tag_changes,
        "created_tag_ids": created_tag_ids,
    }
    plan.result = {
        "album_id": str(album.id), "album_url": f"/album/{album.id}",
        "album_name": album.name, "added_photo_count": len(added_photo_ids),
        "tag_relation_count": len(tag_changes),
        "artifact_id": op.get("artifact_id"),
        "artifact_url": f"/agent/artifacts/{op['artifact_id']}" if op.get("artifact_id") else None,
    }
    plan.status = "executed"
    plan.attempt_count = int(plan.attempt_count or 0) + 1
    plan.error_message = None
    plan.executed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(plan)
    return plan


def reject_plan(db: Session, user_id, plan_id) -> AgentActionPlan:
    """Record an explicit user rejection without applying any operation."""
    plan = get_owned_plan(db, user_id, plan_id, for_update=True)
    if not plan:
        raise ValueError("操作计划不存在")
    if plan.status != "proposed":
        raise ValueError("只有待确认的计划可以拒绝")
    plan.status = "rejected"
    plan.error_message = None
    db.commit()
    db.refresh(plan)
    return plan


def undo_plan(db: Session, user_id, plan_id) -> AgentActionPlan:
    plan = get_owned_plan(db, user_id, plan_id, for_update=True)
    if not plan:
        raise ValueError("操作计划不存在")
    if plan.status != "executed":
        raise ValueError("只有已执行的计划可以撤销")
    if plan.plan_type == "album_metadata_repair":
        raise ValueError("AI 描述和文件指纹任务不可撤销；可在任务失败后重试或重新生成")
    undo = plan.undo_data or {}
    if plan.plan_type == "album_repair":
        owner_id = _uuid(user_id)
        validated = []
        for repair in undo.get("repairs") or []:
            album = db.query(Album).filter(
                Album.id == _uuid(repair.get("album_id")), Album.owner_id == owner_id, Album.type == "user"
            ).first()
            if not album:
                raise ValueError("已修复的相册不存在，无法安全撤销")
            if repair.get("kind") == "album_count":
                if int(album.num_photos or 0) != int(repair.get("applied_after")):
                    raise ValueError(f"“{album.name}”的照片计数之后又被修改，无法安全撤销")
            elif repair.get("kind") == "album_cover":
                current = str(album.cover_id) if album.cover_id else None
                if current != repair.get("applied_after"):
                    raise ValueError(f"“{album.name}”的封面之后又被修改，无法安全撤销")
            else:
                raise ValueError("撤销数据包含不支持的操作")
            validated.append((repair, album))
        for repair, album in validated:
            if repair["kind"] == "album_count":
                album.num_photos = int(repair["before"])
            else:
                album.cover_id = _uuid(repair["before"]) if repair.get("before") else None
        plan.status = "undone"
        plan.undone_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(plan)
        return plan
    if plan.plan_type != "album_organize":
        raise ValueError("不支持的操作计划类型")
    album_id = _uuid(undo.get("album_id"))

    for change in undo.get("tag_changes") or []:
        relation = db.query(PhotoTagRelation).filter(PhotoTagRelation.id == change.get("relation_id")).first()
        if not relation:
            continue
        if change.get("created"):
            db.delete(relation)
        else:
            relation.is_deleted = bool(change.get("was_deleted"))
            relation.confidence = change.get("previous_confidence", relation.confidence)

    db.flush()
    for tag_id in undo.get("created_tag_ids") or []:
        tag_uuid = _uuid(tag_id)
        has_relations = db.query(PhotoTagRelation.id).filter(PhotoTagRelation.tag_id == tag_uuid).first()
        if not has_relations:
            db.query(PhotoTag).filter(PhotoTag.id == tag_uuid, PhotoTag.owner_id == _uuid(user_id)).delete(synchronize_session=False)

    album = db.query(Album).filter(Album.id == album_id, Album.owner_id == _uuid(user_id)).first()
    if undo.get("created_album"):
        if album:
            db.delete(album)
    elif album:
        before = undo.get("album_before") or {}
        album.name = before.get("name", album.name)
        album.description = before.get("description")
        album.cover_id = _uuid(before["cover_photo_id"]) if before.get("cover_photo_id") else None
        added_ids = [_uuid(value) for value in undo.get("added_photo_ids") or []]
        if added_ids:
            db.query(AlbumPhoto).filter(
                AlbumPhoto.album_id == album.id, AlbumPhoto.photo_id.in_(added_ids)
            ).delete(synchronize_session=False)
        db.flush()
        album.num_photos = db.query(func.count(AlbumPhoto.id)).filter(AlbumPhoto.album_id == album.id).scalar()

    plan.status = "undone"
    plan.undone_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(plan)
    return plan
