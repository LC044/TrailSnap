from typing import List, Optional, Any, Dict
from uuid import UUID
from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.db.models.notification import (
    Notification,
    NotificationType,
    NotificationLevel,
)


def _serialize(n: Notification) -> Dict[str, Any]:
    return {
        "id": str(n.id),
        "user_id": str(n.user_id),
        "type": n.type,
        "level": n.level,
        "title": n.title,
        "body": n.body,
        "ref_type": n.ref_type,
        "ref_id": n.ref_id,
        "read": bool(n.read),
        "created_at": n.created_at.isoformat() if n.created_at else None,
        "read_at": n.read_at.isoformat() if n.read_at else None,
    }


def list_notifications(
    db: Session,
    user_id: UUID,
    type: Optional[str] = None,
    unread: Optional[bool] = None,
    limit: int = 50,
    before_id: Optional[UUID] = None,
) -> List[Notification]:
    """游标分页查询当前用户的通知，按创建时间倒序。"""
    q = db.query(Notification).filter(Notification.user_id == user_id)
    if type:
        q = q.filter(Notification.type == type)
    if unread is True:
        q = q.filter(Notification.read.is_(False))
    elif unread is False:
        q = q.filter(Notification.read.is_(True))
    if before_id is not None:
        before = db.query(Notification).filter(Notification.id == before_id).first()
        if before is not None and before.created_at is not None:
            q = q.filter(Notification.created_at < before.created_at)
    q = q.order_by(desc(Notification.created_at), desc(Notification.id))
    return q.limit(max(1, min(limit, 200))).all()


def unread_count(db: Session, user_id: UUID) -> int:
    return (
        db.query(Notification)
        .filter(Notification.user_id == user_id, Notification.read.is_(False))
        .count()
    )


def create_notification(
    db: Session,
    user_id: UUID,
    type: str,
    title: str,
    body: Optional[Dict[str, Any]] = None,
    level: str = NotificationLevel.INFO.value,
    ref_type: Optional[str] = None,
    ref_id: Optional[str] = None,
    commit: bool = True,
) -> Notification:
    obj = Notification(
        user_id=user_id,
        type=type,
        level=level,
        title=title,
        body=body,
        ref_type=ref_type,
        ref_id=ref_id,
        read=False,
    )
    db.add(obj)
    if commit:
        db.commit()
        db.refresh(obj)
    else:
        db.flush()
    return obj


def mark_read(db: Session, user_id: UUID, notif_id: UUID) -> bool:
    """标记单条已读。带 user_id 校验防越权。返回是否命中。"""
    obj = (
        db.query(Notification)
        .filter(Notification.id == notif_id, Notification.user_id == user_id)
        .first()
    )
    if not obj:
        return False
    if not obj.read:
        obj.read = True
        obj.read_at = datetime.utcnow()
        db.commit()
    return True


def mark_all_read(db: Session, user_id: UUID) -> int:
    rows = (
        db.query(Notification)
        .filter(Notification.user_id == user_id, Notification.read.is_(False))
        .all()
    )
    now = datetime.utcnow()
    for r in rows:
        r.read = True
        r.read_at = now
    db.commit()
    return len(rows)
