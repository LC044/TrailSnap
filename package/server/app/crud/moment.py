from datetime import date
from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models.moment_day_caption import MomentDayCaption


def list_captions(
    db: Session,
    user_id: UUID,
    scope_type: str,
    scope_id: Optional[str],
    start: date,
    end: date,
) -> List[MomentDayCaption]:
    """列出某用户在给定 scope 下指定日期区间的日文案。"""
    q = db.query(MomentDayCaption).filter(
        MomentDayCaption.user_id == user_id,
        MomentDayCaption.scope_type == scope_type,
        MomentDayCaption.day >= start,
        MomentDayCaption.day <= end,
    )
    if scope_id is None:
        q = q.filter(MomentDayCaption.scope_id.is_(None))
    else:
        q = q.filter(MomentDayCaption.scope_id == scope_id)
    return q.order_by(MomentDayCaption.day.desc()).all()


def get_caption(
    db: Session,
    user_id: UUID,
    scope_type: str,
    scope_id: Optional[str],
    day: date,
) -> Optional[MomentDayCaption]:
    q = db.query(MomentDayCaption).filter(
        MomentDayCaption.user_id == user_id,
        MomentDayCaption.scope_type == scope_type,
        MomentDayCaption.day == day,
    )
    if scope_id is None:
        q = q.filter(MomentDayCaption.scope_id.is_(None))
    else:
        q = q.filter(MomentDayCaption.scope_id == scope_id)
    return q.one_or_none()


def upsert_caption(
    db: Session,
    user_id: UUID,
    scope_type: str,
    scope_id: Optional[str],
    day: date,
    caption: str,
    source: str,
    model_name: Optional[str] = None,
    photo_count: int = 0,
) -> MomentDayCaption:
    obj = get_caption(db, user_id, scope_type, scope_id, day)
    if obj is None:
        obj = MomentDayCaption(
            user_id=user_id,
            scope_type=scope_type,
            scope_id=scope_id,
            day=day,
            caption=caption,
            source=source,
            model_name=model_name,
            photo_count=photo_count,
        )
        db.add(obj)
    else:
        obj.caption = caption
        obj.source = source
        if model_name is not None:
            obj.model_name = model_name
        if photo_count:
            obj.photo_count = photo_count
    db.commit()
    db.refresh(obj)
    return obj


def delete_caption(
    db: Session,
    user_id: UUID,
    scope_type: str,
    scope_id: Optional[str],
    day: date,
) -> bool:
    obj = get_caption(db, user_id, scope_type, scope_id, day)
    if obj is None:
        return False
    db.delete(obj)
    db.commit()
    return True
