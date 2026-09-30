"""Owner-scoped life chapters; membership is derived from current photo dates."""

from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import distinct, func, or_
from sqlalchemy.orm import Session

from app.db.models.chapter import LifeChapter
from app.db.models.face import Face, FaceIdentity
from app.db.models.image_description import ImageDescription
from app.db.models.memory import Memory, MemoryPhoto, MemoryStatus
from app.db.models.photo import FileType, ImageType, Photo
from app.db.models.photo_metadata import PhotoMetadata
from app.schemas.chapter import ChapterDefinition, ChapterMerge, ChapterSplit, ChapterUpdate


def _photo_query(db: Session, owner_id: UUID, start: date, end: date | None):
    query = db.query(Photo).filter(
        Photo.owner_id == owner_id,
        Photo.is_deleted.is_(False),
        Photo.photo_time.isnot(None),
        Photo.photo_time >= datetime.combine(start, time.min),
    )
    if end:
        query = query.filter(Photo.photo_time < datetime.combine(end + timedelta(days=1), time.min))
    return query


def _owned(db: Session, owner_id: UUID, chapter_id: UUID, *, manage: bool = False) -> LifeChapter:
    row = db.query(LifeChapter).filter(
        LifeChapter.id == chapter_id, LifeChapter.owner_id == owner_id,
        LifeChapter.status != "deleted", LifeChapter.status != "superseded",
    ).first()
    if not row:
        raise HTTPException(404, "章节不存在")
    if row.is_hidden and not manage:
        raise HTTPException(404, "章节不存在")
    return row


def _check_version(row: LifeChapter, version: int) -> None:
    if row.version != version:
        raise HTTPException(409, "章节已变化，请刷新后重试")


def _validate_cover(db: Session, owner_id: UUID, cover_id: UUID | None, start: date, end: date | None) -> None:
    if cover_id and not _photo_query(db, owner_id, start, end).filter(Photo.id == cover_id).first():
        raise HTTPException(400, "封面必须是本章节时间内的有效照片")


def _cover(db: Session, row: LifeChapter) -> str | None:
    if row.cover_photo_id and _photo_query(db, row.owner_id, row.start_date, row.end_date).filter(Photo.id == row.cover_photo_id).first():
        return str(row.cover_photo_id)
    candidates = _photo_query(db, row.owner_id, row.start_date, row.end_date).filter(
        or_(Photo.image_type.is_(None), Photo.image_type != ImageType.SCREENSHOT)
    )
    camera = candidates.filter(Photo.image_type == ImageType.CAMERA)
    if camera.first():
        candidates = camera
    midpoint = row.start_date + ((row.end_date or date.today()) - row.start_date) / 2
    photo = candidates.filter(Photo.photo_time >= datetime.combine(midpoint, time.min)).order_by(
        Photo.photo_time.asc(), Photo.id.asc()).first()
    if not photo:
        photo = candidates.order_by(Photo.photo_time.desc(), Photo.id.desc()).first()
    if not photo:
        photo = _photo_query(db, row.owner_id, row.start_date, row.end_date).order_by(Photo.photo_time.asc()).first()
    return str(photo.id) if photo else None


def serialize(db: Session, row: LifeChapter, *, count: bool = True) -> dict:
    evidence = [dict(item) for item in (row.evidence or [])]
    evidence_ids = {photo_id for item in evidence for photo_id in item.get("photo_ids", [])}
    if evidence_ids:
        valid_ids = {str(photo_id) for (photo_id,) in _photo_query(
            db, row.owner_id, row.start_date, row.end_date
        ).filter(Photo.id.in_([UUID(photo_id) for photo_id in evidence_ids])).with_entities(Photo.id).all()}
        for item in evidence:
            item["photo_ids"] = [photo_id for photo_id in item.get("photo_ids", []) if photo_id in valid_ids]
    result = {
        "id": str(row.id), "status": row.status, "origin": row.origin,
        "is_hidden": row.is_hidden, "title": row.title, "summary": row.summary,
        "summary_source": row.summary_source or "user",
        "start_date": row.start_date.isoformat(),
        "end_date": row.end_date.isoformat() if row.end_date else None,
        "cover_photo_id": _cover(db, row), "evidence": evidence,
        "version": row.version, "source_ids": row.source_ids or [],
    }
    if count:
        result["photo_count"] = _photo_query(db, row.owner_id, row.start_date, row.end_date).count()
        result["event_count"] = _events_query(db, row).count()
    return result


def list_owned(db: Session, owner_id: UUID, *, status: str = "confirmed", hidden: bool = False,
               reveal: bool = False, skip: int = 0, limit: int = 20) -> dict:
    if status not in {"confirmed", "candidate", "ignored"}:
        raise HTTPException(400, "无效的章节状态")
    query = db.query(LifeChapter).filter(LifeChapter.owner_id == owner_id, LifeChapter.status == status)
    query = query.filter(LifeChapter.is_hidden.is_(hidden if status == "confirmed" else False))
    total = query.count()
    rows = query.order_by(LifeChapter.start_date.asc(), LifeChapter.id.asc()).offset(skip).limit(limit).all()
    if hidden and not reveal:
        items = [{"id": str(row.id), "status": row.status, "origin": row.origin,
                  "is_hidden": True, "title": "已隐藏的章节", "summary": None,
                  "start_date": "", "end_date": None, "cover_photo_id": None,
                  "evidence": [], "photo_count": 0, "event_count": 0,
                  "version": row.version, "source_ids": []} for row in rows]
    else:
        items = [serialize(db, row) for row in rows]
    return {"items": items, "total": total, "skip": skip, "limit": limit}


def get(db: Session, owner_id: UUID, chapter_id: UUID, *, manage: bool = False) -> dict:
    row = _owned(db, owner_id, chapter_id, manage=manage)
    result = serialize(db, row)
    result["years"] = sorted({int(year) for (year,) in _photo_query(
        db, owner_id, row.start_date, row.end_date
    ).with_entities(func.extract('year', Photo.photo_time)).distinct().all()}
        | {int(year) for year in (row.diary_entries or {})
           if row.start_date.year <= int(year) <= (row.end_date or date.today()).year})
    result["diary_entries"] = diary_entries(db, row)
    result["people"] = people(db, row)
    result["places"] = places(db, row)
    result["events"] = events(db, row, 0, 6)["items"]
    return result


def diary_entries(db: Session, row: LifeChapter) -> dict:
    entries = {year: dict(entry) for year, entry in (row.diary_entries or {}).items()}
    photo_ids = {UUID(id) for entry in entries.values() for id in entry.get("source_photo_ids", [])}
    memory_ids = {UUID(id) for entry in entries.values() for id in entry.get("source_memory_ids", [])}
    valid_photos = {str(id): when.year for id, when in _photo_query(db, row.owner_id, row.start_date, row.end_date)
                    .filter(Photo.id.in_(photo_ids)).with_entities(Photo.id, Photo.photo_time).all()} if photo_ids else {}
    valid_memories = {str(id) for (id,) in _events_query(db, row).filter(Memory.id.in_(memory_ids))
                      .with_entities(Memory.id).all()} if memory_ids else set()
    for year, entry in entries.items():
        entry["source_photo_ids"] = [id for id in entry.get("source_photo_ids", []) if valid_photos.get(id) == int(year)]
        entry["source_memory_ids"] = [id for id in entry.get("source_memory_ids", []) if id in valid_memories]
    return entries


def photos(db: Session, row: LifeChapter, skip: int, limit: int, year: int | None = None) -> dict:
    query = _photo_query(db, row.owner_id, row.start_date, row.end_date)
    if year:
        query = query.filter(Photo.photo_time >= datetime(year, 1, 1), Photo.photo_time < datetime(year + 1, 1, 1))
    total = query.count()
    rows = query.order_by(Photo.photo_time.asc(), Photo.id.asc()).offset(skip).limit(limit).all()
    def item(p: Photo) -> dict:
        return {"id": str(p.id), "filename": p.filename,
                "photo_time": p.photo_time.isoformat(), "file_type": p.file_type.value,
                "width": p.width, "height": p.height}
    result = {"items": [item(photo) for photo in rows], "total": total}
    if year and skip == 0 and total:
        year_start = max(row.start_date, date(year, 1, 1))
        year_end = min(row.end_date or date.today(), date(year, 12, 31))
        midpoint = year_start + (year_end - year_start) / 2
        preferred = query.filter(or_(Photo.image_type.is_(None), Photo.image_type != ImageType.SCREENSHOT))
        featured = preferred.filter(Photo.photo_time >= datetime.combine(midpoint, time.min)).order_by(
            Photo.photo_time.asc(), Photo.id.asc()).first()
        if not featured:
            featured = preferred.order_by(Photo.photo_time.desc(), Photo.id.desc()).first()
        result["featured"] = item(featured or rows[0])
        result["representatives"] = [item(photo) for photo in representative_photos(db, row, year)]
    return result


def representative_photos(db: Session, row: LifeChapter, year: int | None = None) -> list[Photo]:
    """Sample across the entire range, rather than the first burst of photos."""
    query = _photo_query(db, row.owner_id, row.start_date, row.end_date)
    if year:
        query = query.filter(Photo.photo_time >= datetime(year, 1, 1), Photo.photo_time < datetime(year + 1, 1, 1))
    preferred = query.filter(or_(Photo.image_type.is_(None), Photo.image_type != ImageType.SCREENSHOT))
    if not preferred.first():
        preferred = query
    camera = preferred.filter(Photo.image_type == ImageType.CAMERA, Photo.file_type == FileType.image)
    if camera.count() >= 6:
        preferred = camera
    months = preferred.with_entities(func.extract('year', Photo.photo_time).label('year'),
                                    func.extract('month', Photo.photo_time).label('month')).distinct().order_by('year', 'month').all()
    size = min(6, len(months))
    offsets = sorted({round((len(months) - 1) * index / max(1, size - 1)) for index in range(size)})
    selected = []
    for offset in offsets:
        sample_year, month = (int(value) for value in months[offset])
        next_month = datetime(sample_year + (month == 12), month % 12 + 1, 1)
        sample = preferred.filter(Photo.photo_time >= datetime(sample_year, month, 1), Photo.photo_time < next_month).outerjoin(
            ImageDescription, ImageDescription.photo_id == Photo.id
        ).order_by(
            (Photo.file_type == FileType.image).desc(),
            (func.coalesce(ImageDescription.memory_score, 0) + func.coalesce(ImageDescription.quality_score, 0)).desc(),
            Photo.photo_time.asc(), Photo.id.asc(),
        ).first()
        if sample:
            selected.append(sample)
    return selected


def _events_query(db: Session, row: LifeChapter, year: int | None = None):
    photos = _photo_query(db, row.owner_id, row.start_date, row.end_date)
    if year:
        photos = photos.filter(Photo.photo_time >= datetime(year, 1, 1), Photo.photo_time < datetime(year + 1, 1, 1))
    photo_ids = photos.with_entities(Photo.id).subquery()
    return db.query(Memory).join(MemoryPhoto, MemoryPhoto.memory_id == Memory.id).join(
        photo_ids, photo_ids.c.id == MemoryPhoto.photo_id
    ).filter(Memory.owner_id == row.owner_id, Memory.status == MemoryStatus.CONFIRMED).distinct()


def events(db: Session, row: LifeChapter, skip: int, limit: int, year: int | None = None) -> dict:
    query = _events_query(db, row, year)
    total = query.count()
    items = query.order_by(Memory.start_time.asc().nullslast(), Memory.id.asc()).offset(skip).limit(limit).all()
    return {"items": [{"id": str(m.id), "title": m.title,
                       "start_time": m.start_time.isoformat() if m.start_time else None,
                       "cover_photo_id": str(m.cover_photo_id) if m.cover_photo_id else None}
                      for m in items], "total": total}


def people(db: Session, row: LifeChapter) -> list[dict]:
    photo_ids = _photo_query(db, row.owner_id, row.start_date, row.end_date).with_entities(Photo.id).subquery()
    rows = db.query(FaceIdentity.id, FaceIdentity.identity_name, func.count(distinct(Face.photo_id))).join(
        Face, Face.face_identity_id == FaceIdentity.id
    ).join(photo_ids, photo_ids.c.id == Face.photo_id).filter(
        FaceIdentity.owner_id == row.owner_id, FaceIdentity.is_deleted.is_(False),
        FaceIdentity.is_hidden.is_(False), Face.is_deleted.is_(False),
    ).group_by(FaceIdentity.id, FaceIdentity.identity_name).order_by(
        func.count(distinct(Face.photo_id)).desc()
    ).limit(20).all()
    return [{"id": str(id), "name": name or "未命名人物", "photo_count": count} for id, name, count in rows]


def places(db: Session, row: LifeChapter) -> list[dict]:
    photo_ids = _photo_query(db, row.owner_id, row.start_date, row.end_date).with_entities(Photo.id).subquery()
    rows = db.query(PhotoMetadata.country, PhotoMetadata.province, PhotoMetadata.city,
                    func.count(PhotoMetadata.photo_id)).join(
        photo_ids, photo_ids.c.id == PhotoMetadata.photo_id
    ).filter(PhotoMetadata.city.isnot(None), PhotoMetadata.city != "").group_by(
        PhotoMetadata.country, PhotoMetadata.province, PhotoMetadata.city
    ).order_by(func.count(PhotoMetadata.photo_id).desc()).limit(20).all()
    return [{"name": " · ".join(s for s in [country, province, city] if s), "photo_count": count}
            for country, province, city, count in rows]


def preview(db: Session, owner_id: UUID, start: date, end: date | None,
            chapter_id: UUID | None = None) -> dict:
    if end and end < start:
        raise HTTPException(400, "结束日期不能早于开始日期")
    new_query = _photo_query(db, owner_id, start, end)
    photo_count = new_query.count()
    # Spread suggestions across the range instead of showing only the first burst of photos.
    sample_query = new_query.filter(Photo.image_type == ImageType.CAMERA)
    sample_count = sample_query.count()
    if not sample_count:
        sample_query = new_query.filter(or_(Photo.image_type.is_(None), Photo.image_type != ImageType.SCREENSHOT))
        sample_count = sample_query.count()
    if not sample_count:
        sample_query, sample_count = new_query, photo_count
    offsets = sorted({round((sample_count - 1) * index / 7) for index in range(min(8, sample_count))})
    samples = [sample_query.with_entities(Photo.id).order_by(Photo.photo_time.asc(), Photo.id.asc())
               .offset(offset).first() for offset in offsets]
    month_rows = new_query.with_entities(
        func.extract('year', Photo.photo_time).label('year'),
        func.extract('month', Photo.photo_time).label('month'),
        func.count(Photo.id),
    ).group_by('year', 'month').order_by('year', 'month').all()
    result = {"photo_count": photo_count,
              "preview_photo_ids": [str(sample[0]) for sample in samples if sample],
              "month_counts": [{"month": f"{int(year):04d}-{int(month):02d}", "count": count}
                               for year, month, count in month_rows]}
    if chapter_id:
        row = _owned(db, owner_id, chapter_id, manage=True)
        old = _photo_query(db, owner_id, row.start_date, row.end_date)
        result["previous_photo_count"] = old.count()
        old_ids = old.with_entities(Photo.id).subquery()
        new_ids = new_query.with_entities(Photo.id).subquery()
        result["added_photo_count"] = new_query.filter(~Photo.id.in_(db.query(old_ids.c.id))).count()
        result["removed_photo_count"] = old.filter(~Photo.id.in_(db.query(new_ids.c.id))).count()
        result["version"] = row.version
    return result


def cover_options(db: Session, owner_id: UUID, start: date, end: date | None,
                  skip: int, limit: int) -> dict:
    if end and end < start:
        raise HTTPException(400, "结束日期不能早于开始日期")
    query = _photo_query(db, owner_id, start, end)
    rows = query.order_by(Photo.photo_time.desc(), Photo.id.desc()).offset(skip).limit(limit).all()
    return {"items": [{"id": str(photo.id), "photo_time": photo.photo_time.isoformat()}
                      for photo in rows], "total": query.count()}


def _write(db: Session, row: LifeChapter, values: dict, version: int):
    updated = db.query(LifeChapter).filter(
        LifeChapter.id == row.id, LifeChapter.owner_id == row.owner_id, LifeChapter.version == version
    ).update({**values, "version": version + 1, "updated_at": datetime.now()}, synchronize_session=False)
    if not updated:
        db.rollback()
        raise HTTPException(409, "章节已变化，请刷新后重试")
    db.commit()
    db.refresh(row)
    return row


def create(db: Session, owner_id: UUID, data: ChapterDefinition) -> LifeChapter:
    _validate_cover(db, owner_id, data.cover_photo_id, data.start_date, data.end_date)
    row = LifeChapter(owner_id=owner_id, status="confirmed", origin="manual",
                      title=data.title.strip(), summary=data.summary, summary_source=data.summary_source,
                      diary_entries={year: entry.model_dump(mode="json") for year, entry in (data.diary_entries or {}).items()},
                      start_date=data.start_date, end_date=data.end_date,
                      cover_photo_id=data.cover_photo_id, confirmed_at=datetime.now())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update(db: Session, owner_id: UUID, chapter_id: UUID, data: ChapterUpdate) -> LifeChapter:
    row = _owned(db, owner_id, chapter_id, manage=True)
    _validate_cover(db, owner_id, data.cover_photo_id, data.start_date, data.end_date)
    values = {"title": data.title.strip(), "summary": data.summary, "summary_source": data.summary_source,
                            "start_date": data.start_date, "end_date": data.end_date,
                            "cover_photo_id": data.cover_photo_id}
    if data.diary_entries is not None:
        values["diary_entries"] = {year: entry.model_dump(mode="json") for year, entry in data.diary_entries.items()}
    return _write(db, row, values, data.version)


def transition(db: Session, owner_id: UUID, chapter_id: UUID, action: str, version: int) -> LifeChapter:
    row = _owned(db, owner_id, chapter_id, manage=True)
    allowed = {"confirm": ("candidate", {"status": "confirmed", "confirmed_at": datetime.now()}),
               "ignore": ("candidate", {"status": "ignored"}),
               "restore": ("ignored", {"status": "candidate"}),
               "hide": ("confirmed", {"is_hidden": True}),
               "unhide": ("confirmed", {"is_hidden": False})}
    if action not in allowed or row.status != allowed[action][0]:
        raise HTTPException(400, "当前状态不能执行此操作")
    return _write(db, row, allowed[action][1], version)


def delete(db: Session, owner_id: UUID, chapter_id: UUID, version: int) -> None:
    row = _owned(db, owner_id, chapter_id, manage=True)
    _write(db, row, {"status": "deleted", "deleted_at": datetime.now()}, version)


def merge(db: Session, owner_id: UUID, data: ChapterMerge) -> LifeChapter:
    if len(set(data.chapter_ids)) != len(data.chapter_ids):
        raise HTTPException(400, "章节不能重复选择")
    rows = [_owned(db, owner_id, id, manage=True) for id in data.chapter_ids]
    if any(row.status not in {"candidate", "confirmed"} for row in rows):
        raise HTTPException(400, "只能合并建议或正式章节")
    for row in rows:
        _check_version(row, data.versions.get(row.id, -1))
    start = min(row.start_date for row in rows)
    ends = [row.end_date for row in rows]
    end = max(ends) if all(ends) else None
    if data.start_date != start or data.end_date != end:
        raise HTTPException(400, "合并范围必须覆盖全部来源章节")
    _validate_cover(db, owner_id, data.cover_photo_id, start, end)
    confirmed = any(row.status == "confirmed" for row in rows)
    merged_entries = {}
    for source in rows:
        for year, entry in (source.diary_entries or {}).items():
            previous = merged_entries.get(year)
            if previous and previous.get("body") != entry.get("body"):
                body = "\n\n".join(text for text in (previous.get("body"), entry.get("body")) if text)
                if len(body) > 1000:
                    raise HTTPException(400, f"{year} 年的两段日记合计超过1000字，请先调整文字再合并")
                merged_entries[year] = {
                    "title": previous.get("title") or entry.get("title", ""), "body": body,
                    "source": "ai" if previous.get("source") == entry.get("source") == "ai" else "user",
                    "source_photo_ids": list(dict.fromkeys(previous.get("source_photo_ids", []) + entry.get("source_photo_ids", [])))[:12],
                    "source_memory_ids": list(dict.fromkeys(previous.get("source_memory_ids", []) + entry.get("source_memory_ids", [])))[:8],
                }
            else:
                merged_entries[year] = dict(entry)
    new = LifeChapter(owner_id=owner_id, origin="manual", status="confirmed" if confirmed else "candidate",
                      title=data.title.strip(), summary=data.summary, summary_source=data.summary_source,
                      diary_entries=merged_entries,
                      start_date=start, end_date=end,
                      cover_photo_id=data.cover_photo_id, is_hidden=any(row.is_hidden for row in rows),
                      source_ids=[str(row.id) for row in rows],
                      confirmed_at=datetime.now() if confirmed else None)
    db.add(new)
    for row in rows:
        updated = db.query(LifeChapter).filter(
            LifeChapter.id == row.id, LifeChapter.owner_id == owner_id,
            LifeChapter.version == data.versions[row.id], LifeChapter.status == row.status,
        ).update({"status": "superseded", "version": row.version + 1}, synchronize_session=False)
        if not updated:
            db.rollback()
            raise HTTPException(409, "来源章节已变化，请刷新后重试")
    db.commit()
    db.refresh(new)
    return new


def split(db: Session, owner_id: UUID, chapter_id: UUID, data: ChapterSplit) -> list[LifeChapter]:
    row = _owned(db, owner_id, chapter_id, manage=True)
    _check_version(row, data.version)
    if row.status not in {"candidate", "confirmed"}:
        raise HTTPException(400, "当前章节不能拆分")
    if (data.split_date <= row.start_date or data.split_date > date.today()
            or (row.end_date and data.split_date > row.end_date)):
        raise HTTPException(400, "拆分日期必须在章节范围内")
    rows = [LifeChapter(owner_id=owner_id, status=row.status, origin="manual", is_hidden=row.is_hidden,
                        title=title.strip(), start_date=start, end_date=end,
                        diary_entries={year: entry for year, entry in (row.diary_entries or {}).items()
                                       if start.year <= int(year) <= (end or date.today()).year},
                        source_ids=[str(row.id)], confirmed_at=datetime.now() if row.status == "confirmed" else None)
            for title, start, end in ((data.first_title, row.start_date, data.split_date - timedelta(days=1)),
                                      (data.second_title, data.split_date, row.end_date))]
    db.add_all(rows)
    updated = db.query(LifeChapter).filter(
        LifeChapter.id == row.id, LifeChapter.owner_id == owner_id,
        LifeChapter.version == data.version, LifeChapter.status == row.status,
    ).update({"status": "superseded", "version": row.version + 1}, synchronize_session=False)
    if not updated:
        db.rollback()
        raise HTTPException(409, "来源章节已变化，请刷新后重试")
    db.commit()
    return rows


def year_links(db: Session, owner_id: UUID, years: list[int]) -> dict[str, list[dict]]:
    if not years:
        return {}
    rows = db.query(LifeChapter).filter(LifeChapter.owner_id == owner_id,
        LifeChapter.status == "confirmed", LifeChapter.is_hidden.is_(False),
        LifeChapter.start_date <= date(max(years), 12, 31),
    ).all()
    result = {}
    for year in years:
        result[str(year)] = []
        for row in rows:
            if (row.start_date.year <= year and (row.end_date is None or row.end_date.year >= year)
                    and _photo_query(db, owner_id, row.start_date, row.end_date).filter(
                        Photo.photo_time >= datetime(year, 1, 1),
                        Photo.photo_time < datetime(year + 1, 1, 1),
                    ).with_entities(Photo.id).first()):
                result[str(year)].append({"id": str(row.id), "title": row.title})
    return result


def _similar_suppressed(row: LifeChapter, start: date, end: date, title: str, evidence_type: str) -> bool:
    if row.status not in {"ignored", "deleted"} and not row.is_hidden:
        return False
    if not row.evidence or row.evidence[0].get("type") != evidence_type:
        return False
    if row.title.split("影像")[0] != title.split("影像")[0]:
        return False
    other_end = row.end_date or end
    overlap = max(0, (min(other_end, end) - max(row.start_date, start)).days + 1)
    union = (max(other_end, end) - min(row.start_date, start)).days + 1
    return overlap / union >= 0.8


def discover(db: Session, owner_id: UUID, max_candidates: int = 10) -> list[LifeChapter]:
    """Find neutral city/year suggestions from dated photos; never infer life events."""
    rows = db.query(Photo.id, Photo.photo_time, PhotoMetadata.country,
                    PhotoMetadata.province, PhotoMetadata.city).outerjoin(
        PhotoMetadata, PhotoMetadata.photo_id == Photo.id
    ).filter(Photo.owner_id == owner_id, Photo.is_deleted.is_(False),
             Photo.photo_time.isnot(None), or_(Photo.image_type.is_(None), Photo.image_type != ImageType.SCREENSHOT)).order_by(
        Photo.photo_time.asc()).yield_per(1000)
    annual = defaultdict(lambda: {"months": set(), "photos": 0, "first": None, "last": None, "examples": {}})
    monthly = defaultdict(lambda: defaultdict(set))
    monthly_counts = defaultdict(Counter)
    monthly_examples = defaultdict(dict)
    for photo_id, taken, country, province, city in rows:
        year, month = taken.year, taken.month
        item = annual[year]
        item["months"].add(month)
        item["photos"] += 1
        item["first"] = min(item["first"] or taken.date(), taken.date())
        item["last"] = max(item["last"] or taken.date(), taken.date())
        item["examples"].setdefault(month, photo_id)
        if city:
            place = (country or "", province or "", city.strip())
            monthly[(year, month)][place].add(taken.date())
            monthly_counts[(year, month)][place] += 1
            monthly_examples[(year, month)].setdefault(place, photo_id)
    proposals = []
    by_city = defaultdict(list)
    for (year, month), days in monthly.items():
        all_days = set().union(*days.values())
        for place, active in days.items():
            if len(all_days) >= 3 and len(active) / len(all_days) >= 0.6:
                by_city[place].append((year, month))
    for place, months in by_city.items():
        months.sort()
        groups = []
        for month in months:
            if not groups or month[0] * 12 + month[1] - (groups[-1][-1][0] * 12 + groups[-1][-1][1]) > 3:
                groups.append([])
            groups[-1].append(month)
        for group in groups:
            first, last = group[0], group[-1]
            if len(group) < 4 or last[0] * 12 + last[1] - (first[0] * 12 + first[1]) < 5:
                continue
            start = date(first[0], first[1], 1)
            end = (date(last[0] + (last[1] == 12), last[1] % 12 + 1, 1) - timedelta(days=1))
            title = f"{place[2]}影像 · {first[0]}—{last[0]}"
            city_count = sum(monthly_counts[month][place] for month in group)
            located_count = sum(sum(monthly_counts[month].values()) for month in group)
            proposals.append((start, end, title, {
                "type": "place",
                "summary": f"{len(group)} 个月的主要拍摄城市为{place[2]}；这些月份中 {city_count}/{located_count} 张带城市定位的照片位于此地",
                "qualified_months": len(group), "city_photo_count": city_count,
                "located_photo_count": located_count,
                "photo_ids": [str(monthly_examples[month][place]) for month in group[:6]],
            }))
    for year, item in annual.items():
        if len(item["months"]) >= 4 and item["photos"] >= 30:
            proposals.append((item["first"], item["last"], f"{year} 年的影像",
                              {"type": "time", "summary": f"这一年有 {item['photos']} 张照片，覆盖 {len(item['months'])} 个月",
                               "photo_count": item["photos"], "active_months": len(item["months"]),
                               "photo_ids": [str(item["examples"][month]) for month in sorted(item["examples"])[:6]]}))
    existing = db.query(LifeChapter).filter(LifeChapter.owner_id == owner_id).all()
    created = []
    for start, end, title, evidence in sorted(proposals, key=lambda x: (x[0], x[2])):
        fingerprint = hashlib.sha256(f"{evidence['type']}:{title}:{start}:{end}".encode()).hexdigest()
        if any(row.candidate_fingerprint == fingerprint or (
            row.status == "confirmed" and row.start_date <= start and
            (row.end_date is None or row.end_date >= end)
        ) or _similar_suppressed(row, start, end, title, evidence["type"]) for row in existing):
            continue
        row = LifeChapter(owner_id=owner_id, title=title[:80], status="candidate", origin="auto",
                          start_date=start, end_date=end, evidence=[evidence], candidate_fingerprint=fingerprint)
        db.add(row)
        created.append(row)
        existing.append(row)
        if len(created) >= max_candidates:
            break
    db.commit()
    return created
