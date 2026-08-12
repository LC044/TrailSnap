from datetime import date
from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.db.models.moment_day_caption import MomentDayCaption
from app.db.models.photo import Photo
from app.db.models.photo_metadata import PhotoMetadata
from app.db.models.scene import Scene
from app.db.sql import as_date, date_only


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


# ---------------------------------------------------------------------------
# 朋友圈日位置（不落库，按需从 photo_metadata 实时聚合）
# ---------------------------------------------------------------------------

def get_day_locations(
    db: Session,
    user_id: UUID,
    start_utc,
    end_utc,
    top_n_per_day: int = 3,
) -> List[dict]:
    """按用户本地时区聚合每一天的位置数据。

    - 时区边界由调用方通过 ``start_utc`` / ``end_utc`` 传入（一般来自
      ``day_caption_service.day_bounds_utc``），语义为 ``[start_utc, end_utc)``。
    - 每张照片按 "景区优先 → city → district → province" 的顺序取一个"标签"。
    - 同一天内按标签聚合，返回照片数最多的 Top N。

    返回结构（不落库、纯派生数据）::

        [
            {
                "day": date(2025, 8, 5),         # 用户本地日期
                "primary": "外滩",               # 该天首选位置（Top1）
                "level": "scene",                # scene / city / district / province
                "locations": [
                    {"name": "外滩",   "level": "scene", "count": 4},
                    {"name": "陆家嘴", "level": "scene", "count": 2},
                ],
            },
            ...
        ]

    未落到任何位置的天不会返回。
    """
    tz_col = Photo.photo_time
    day_expr = date_only(db, tz_col).label("day")

    # 名称：Scene.name > city > district > province（第一个非空的胜出）
    name_expr = func.coalesce(
        func.nullif(Scene.name, ""),
        func.nullif(PhotoMetadata.city, ""),
        func.nullif(PhotoMetadata.district, ""),
        func.nullif(PhotoMetadata.province, ""),
    ).label("name")

    # 级别：与 name_expr 保持同一优先级顺序
    level_expr = case(
        (func.nullif(Scene.name, "").isnot(None), "scene"),
        (func.nullif(PhotoMetadata.city, "").isnot(None), "city"),
        (func.nullif(PhotoMetadata.district, "").isnot(None), "district"),
        (func.nullif(PhotoMetadata.province, "").isnot(None), "province"),
        else_="unknown",
    ).label("level")

    rows = (
        db.query(
            day_expr,
            name_expr,
            level_expr,
            func.count(Photo.id).label("cnt"),
        )
        .join(PhotoMetadata, Photo.id == PhotoMetadata.photo_id)
        .outerjoin(Scene, PhotoMetadata.scene_id == Scene.id)
        .filter(
            Photo.owner_id == user_id,
            Photo.is_deleted.is_(False),
            Photo.photo_time.isnot(None),
            Photo.photo_time >= start_utc,
            Photo.photo_time < end_utc,
        )
        .group_by(day_expr, name_expr, level_expr)
        .having(name_expr.isnot(None))
        .order_by(day_expr, func.count(Photo.id).desc())
        .all()
    )

    # Python 侧按 day 聚合（SQL 已经按 day / count desc 排序）
    _LEVEL_RANK = {"scene": 0, "city": 1, "district": 2, "province": 3, "unknown": 4}
    buckets: dict = {}
    for r in rows:
        entry = buckets.setdefault(as_date(r.day), [])
        entry.append({"name": r.name, "level": r.level, "count": int(r.cnt)})

    result: List[dict] = []
    for d, items in buckets.items():
        # 同一天内：先按 (level_rank, -count) 排序 —— 景区永远排在城市前面，
        # 同 level 内再按照片数 desc 决定 primary。
        items.sort(key=lambda x: (_LEVEL_RANK.get(x["level"], 99), -x["count"]))
        top = items[:top_n_per_day]
        result.append({
            "day": d,
            "primary": top[0]["name"],
            "level": top[0]["level"],
            "locations": top,
        })

    # 按日期倒序（新的在前），与 list_captions 保持一致
    result.sort(key=lambda x: x["day"], reverse=True)
    return result
