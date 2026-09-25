"""Evidence-based timelines for one person or a pair of people."""

from collections import Counter, defaultdict
from datetime import datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import and_, exists, not_
from sqlalchemy.orm import Session

from app.db.models.face import Face, FaceIdentity
from app.db.models.memory import Memory, MemoryPhoto, MemoryStatus
from app.db.models.image_description import ImageDescription
from app.db.models.person_timeline import PersonTimelineHide
from app.db.models.photo import Photo

SOLO = UUID(int=0)


def scope(db: Session, owner_id: UUID, person_id: UUID, with_id: UUID | None):
    if with_id == person_id:
        raise HTTPException(status_code=400, detail="不能选择同一人物")
    ids = [person_id] + ([with_id] if with_id else [])
    people = db.query(FaceIdentity).filter(
        FaceIdentity.id.in_(ids), FaceIdentity.owner_id == owner_id,
        FaceIdentity.is_deleted.is_(False), FaceIdentity.is_hidden.is_(False),
    ).all()
    if len(people) != len(ids):
        raise HTTPException(status_code=404, detail="人物不存在或不可访问")
    first, second = sorted(ids, key=str) if with_id else (person_id, SOLO)
    return first, second, people


def photo_query(db: Session, owner_id: UUID, first: UUID, second: UUID, *, include_hidden=False):
    people = [first] + ([second] if second != SOLO else [])
    query = db.query(Photo).filter(
        Photo.owner_id == owner_id, Photo.is_deleted.is_(False), Photo.photo_time.isnot(None),
    )
    for person_id in people:
        query = query.filter(exists().where(and_(
            Face.photo_id == Photo.id, Face.face_identity_id == person_id, Face.is_deleted.is_(False),
        )))
    if not include_hidden:
        hidden = db.query(PersonTimelineHide).filter(
            PersonTimelineHide.owner_id == owner_id,
            PersonTimelineHide.person_a_id == first,
            PersonTimelineHide.person_b_id == second,
        ).subquery()
        query = query.filter(not_(exists().where(and_(
            hidden.c.start_at <= Photo.photo_time, hidden.c.end_at > Photo.photo_time,
        ))))
    return query


def photo_dict(photo: Photo) -> dict:
    return {
        "id": str(photo.id), "photo_time": photo.photo_time.isoformat(),
        "thumbnail_url": f"/api/medias/{photo.id}/thumbnail",
        "filename": photo.filename or "照片",
    }


def representatives(db: Session, rows: list) -> list:
    ids = [row.id for row in rows]
    scores = {}
    for offset in range(0, len(ids), 500):
        scored = db.query(ImageDescription.photo_id, ImageDescription.memory_score, ImageDescription.quality_score).filter(
            ImageDescription.photo_id.in_(ids[offset:offset + 500])
        ).all()
        scores.update({photo_id: float(memory or 0) * 0.6 + float(quality or 0) * 0.4
                       for photo_id, memory, quality in scored})
    ranked = sorted(rows, key=lambda row: scores.get(row.id, 0), reverse=True) if scores else []
    sampled = rows[:1] + rows[len(rows)//2:len(rows)//2+1] + rows[-1:]
    chosen = []
    days = set()
    for row in ranked + sampled + rows:
        if row.photo_time.date() not in days:
            chosen.append(row)
            days.add(row.photo_time.date())
        if len(chosen) == 3:
            break
    return chosen


def confirmed_memories(db: Session, owner_id: UUID, photo_ids: list[UUID]) -> list[dict]:
    if not photo_ids:
        return []
    by_id = {}
    for offset in range(0, len(photo_ids), 500):
        rows = db.query(Memory, MemoryPhoto.photo_id).join(
            MemoryPhoto, MemoryPhoto.memory_id == Memory.id
        ).filter(
            Memory.owner_id == owner_id, Memory.status == MemoryStatus.CONFIRMED,
            MemoryPhoto.photo_id.in_(photo_ids[offset:offset + 500]),
        ).all()
        for memory, photo_id in rows:
            title = memory.title or ""
            if any(term in title for term in ("春节", "中秋", "端午", "国庆", "元旦", "圣诞", "节日")):
                kind = "holiday"
            elif any(term in title for term in ("旅行", "出游", "旅游", "游玩")):
                kind = "travel"
            else:
                kind = "memory"
            item = by_id.setdefault(str(memory.id), {
                "id": str(memory.id), "title": memory.title,
                "start_time": memory.start_time.isoformat() if memory.start_time else None,
                "photo_ids": [], "source": "confirmed_memory", "kind": kind,
            })
            item["photo_ids"].append(str(photo_id))
    return sorted(by_id.values(), key=lambda item: item["start_time"] or "", reverse=True)


def timeline(db: Session, owner_id: UUID, first: UUID, second: UUID, people: list[FaceIdentity]) -> dict:
    # Select only IDs and timestamps. This is a full, uncapped summary; detailed photos are paged.
    rows = photo_query(db, owner_id, first, second).with_entities(Photo.id, Photo.photo_time).order_by(
        Photo.photo_time.desc(), Photo.id.desc()
    ).all()
    years: dict[int, list] = defaultdict(list)
    for row in rows:
        years[row.photo_time.year].append(row)
    cards = []
    for year, year_rows in sorted(years.items(), reverse=True):
        ordered = sorted(year_rows, key=lambda row: row.photo_time)
        groups = []
        for row in ordered:
            if (not groups or (row.photo_time.date() - groups[-1][-1].photo_time.date()).days > 2
                    or (row.photo_time.date() - groups[-1][0].photo_time.date()).days > 6):
                groups.append([])
            groups[-1].append(row)
        leading = max(groups, key=lambda group: (len(group), group[-1].photo_time))
        representative_rows = representatives(db, year_rows)
        cards.append({
            "year": year, "photo_count": len(year_rows),
            "representative_event": {
                "start_at": leading[0].photo_time.isoformat(),
                "end_at": leading[-1].photo_time.isoformat(),
                "photo_count": len(leading),
            },
            "representative_photos": [
                {"id": str(row.id), "thumbnail_url": f"/api/medias/{row.id}/thumbnail",
                 "photo_time": row.photo_time.isoformat()}
                for row in representative_rows
            ],
            "memories": confirmed_memories(db, owner_id, [row.id for row in year_rows])[:3],
        })
    names = {str(person.id): person.identity_name or "未命名人物" for person in people}
    month_counts = Counter(row.photo_time.strftime("%Y-%m") for row in rows) if second != SOLO else Counter()
    peak = month_counts.most_common(1)[0] if month_counts and max(month_counts.values()) >= 2 else None
    covers = {str(face.id): str(face.photo_id) for face in db.query(Face).filter(Face.id.in_(
        [person.default_face_id for person in people if person.default_face_id is not None]
    )).all()}
    identity_by_id = {str(person.id): person for person in people}
    return {
        "people": [{"id": str(pid), "name": names[str(pid)], "tags": identity_by_id[str(pid)].tags or [],
                    "avatar_url": f"/api/medias/{covers[str(identity_by_id[str(pid)].default_face_id)]}/thumbnail"
                    if str(identity_by_id[str(pid)].default_face_id) in covers else None}
                   for pid in ([first] + ([second] if second != SOLO else []))],
        "mode": "pair" if second != SOLO else "solo",
        "photo_count": len(rows), "year_count": len(cards), "years": cards,
        "first_photo": {"id": str(rows[-1].id), "photo_time": rows[-1].photo_time.isoformat()} if rows else None,
        "latest_photo": {"id": str(rows[0].id), "photo_time": rows[0].photo_time.isoformat()} if rows else None,
        "peak_month": {"month": peak[0], "count": peak[1]} if peak else None,
    }


def year_detail(db: Session, owner_id: UUID, first: UUID, second: UUID, year: int, skip: int, limit: int) -> dict:
    if year < 1900 or year > 2200:
        raise HTTPException(status_code=400, detail="年份无效")
    start, end = datetime(year, 1, 1), datetime(year + 1, 1, 1)
    query = photo_query(db, owner_id, first, second).filter(Photo.photo_time >= start, Photo.photo_time < end)
    total = query.count()
    photos = query.order_by(Photo.photo_time.desc(), Photo.id.desc()).offset(skip).limit(limit).all()
    return {"year": year, "total": total, "photos": [photo_dict(photo) for photo in photos],
            "memories": confirmed_memories(db, owner_id, [photo.id for photo in photos]),
            "next_skip": skip + len(photos) if skip + len(photos) < total else None}
