"""Confirmed and reversible write operations for the album Agent."""

from datetime import datetime, timedelta, timezone
from typing import Iterable
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models.agent import AgentSession
from app.db.models.agent_action import AgentActionPlan
from app.db.models.ai_artifact import AIArtifact
from app.db.models.album import Album, AlbumPhoto
from app.db.models.photo import Photo
from app.db.models.tag import PhotoTag, PhotoTagRelation


MAX_PLAN_PHOTOS = 500
MAX_PLAN_TAGS = 10
PLAN_TTL_DAYS = 7


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
    if plan.plan_type != "album_organize":
        raise ValueError("不支持的操作计划类型")

    owner_id = _uuid(user_id)
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


def undo_plan(db: Session, user_id, plan_id) -> AgentActionPlan:
    plan = get_owned_plan(db, user_id, plan_id, for_update=True)
    if not plan:
        raise ValueError("操作计划不存在")
    if plan.status != "executed":
        raise ValueError("只有已执行的计划可以撤销")
    undo = plan.undo_data or {}
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
