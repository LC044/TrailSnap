from __future__ import annotations

from collections import Counter, defaultdict
import base64
import json
from io import BytesIO
from html.parser import HTMLParser
from datetime import datetime, timedelta
from typing import Iterable
from uuid import UUID

from PIL import Image, ImageDraw, ImageOps
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session, joinedload

from app.db.models import AIArtifact
from app.db.models.album import Album, AlbumPhoto
from app.db.models.face import Face, FaceIdentity
from app.db.models.image_description import ImageDescription
from app.db.models.ocr import OCR
from app.db.models.photo import Photo
from app.db.models.photo_metadata import PhotoMetadata
from app.db.models.trip import FlightTicket, TrainTicket
from app.service.storage import get_available_photo_path, get_preview_path


class _StaticArtifactHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ignored_depth = 0
        self.visible_text: list[str] = []
        self.image_sources: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "template"}:
            self.ignored_depth += 1
        elif tag == "img" and not self.ignored_depth:
            source = dict(attrs).get("src")
            if source:
                self.image_sources.append(source)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "template"} and self.ignored_depth:
            self.ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self.ignored_depth and data.strip():
            self.visible_text.append(data.strip())


def _validate_static_artifact_html(html_content: str, photo_ids: list[str]) -> None:
    """Require useful server-rendered content so optional JS is progressive enhancement."""
    parser = _StaticArtifactHTMLParser()
    try:
        parser.feed(html_content)
    except Exception as exc:
        raise ValueError("HTML 无法解析") from exc
    if len("".join(parser.visible_text)) < 80:
        raise ValueError("HTML 必须在 DOM 中预渲染主要正文，不能仅由 JavaScript 动态生成")
    if photo_ids and not any(any(photo_id in source for photo_id in photo_ids) for source in parser.image_sources):
        raise ValueError("HTML 必须在 DOM 中预渲染至少一张作品真实照片，JavaScript 只能用于增强交互")


def _iso(value):
    return value.isoformat() if value else None


def _uuid_list(values: Iterable[str], limit: int) -> list[UUID]:
    parsed = []
    for value in values:
        try:
            item = UUID(str(value))
        except (ValueError, TypeError, AttributeError):
            continue
        if item not in parsed:
            parsed.append(item)
        if len(parsed) >= limit:
            break
    return parsed


def _string_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item]
    return []


def _normalize_artifact_content(content: dict | None) -> dict:
    """Normalize common model aliases into the editable artifact contract."""
    source = dict(content or {})
    normalized_sections = []
    for index, raw in enumerate(source.get("sections") or []):
        if not isinstance(raw, dict):
            continue
        section = dict(raw)
        photo_ids = section.get("photo_ids")
        if not isinstance(photo_ids, list):
            photo_ids = [section["photo_id"]] if section.get("photo_id") else []
        section["heading"] = str(
            section.get("heading") or section.get("title") or section.get("location") or f"第 {index + 1} 段"
        )
        section["body"] = str(
            section.get("body") or section.get("narrative") or section.get("story") or section.get("description") or ""
        )
        section["photo_ids"] = [str(value) for value in photo_ids if value]
        normalized_sections.append(section)
    source["sections"] = normalized_sections
    source["summary"] = str(source.get("summary") or "")
    return source


def photo_contexts(db: Session, user_id: str, photo_ids: list[str]) -> list[dict]:
    ids = _uuid_list(photo_ids, 30)
    rows = (
        db.query(Photo)
        .options(
            joinedload(Photo.metadata_info).joinedload(PhotoMetadata.scene),
            joinedload(Photo.image_description), joinedload(Photo.color_info), joinedload(Photo.tags), joinedload(Photo.albums),
            joinedload(Photo.faces).joinedload(Face.identity),
        )
        .filter(Photo.owner_id == user_id, Photo.is_deleted.is_(False), Photo.id.in_(ids))
        .all()
    )
    ocr_rows = db.query(OCR).filter(OCR.photo_id.in_([p.id for p in rows])).order_by(OCR.text_score.desc()).all()
    ocr_by_id = defaultdict(list)
    for row in ocr_rows:
        if row.text and len(ocr_by_id[str(row.photo_id)]) < 20:
            ocr_by_id[str(row.photo_id)].append({"text": row.text, "score": row.text_score})
    by_id = {str(p.id): p for p in rows}
    result = []
    for requested_id in ids:
        photo = by_id.get(str(requested_id))
        if not photo:
            continue
        meta, desc, color = photo.metadata_info, photo.image_description, photo.color_info
        people = sorted({
            f.identity.identity_name for f in photo.faces
            if not f.is_deleted and f.identity and not f.identity.is_deleted and not f.identity.is_hidden and f.identity.identity_name
        })
        result.append({
            "photo_id": str(photo.id), "filename": photo.filename, "photo_time": _iso(photo.photo_time),
            "media_type": photo.file_type.value if photo.file_type else None,
            "dimensions": {"width": photo.width, "height": photo.height},
            "orientation": "landscape" if photo.width and photo.height and photo.width > photo.height else "portrait" if photo.width and photo.height and photo.height > photo.width else "square",
            "location": {"country": meta.country, "province": meta.province, "city": meta.city, "district": meta.district, "address": meta.address, "scene": meta.scene.name if meta and meta.scene else None, "latitude": float(meta.latitude) if meta and meta.latitude is not None else None, "longitude": float(meta.longitude) if meta and meta.longitude is not None else None} if meta else None,
            "camera": {"make": meta.make, "model": meta.model, "shooting_params": meta.shooting_params} if meta else None,
            "exif": meta.exif_info[:2000] if meta and meta.exif_info else None,
            "description": desc.description if desc else None, "narrative": desc.narrative if desc else None,
            "quality_score": desc.quality_score if desc else None, "memory_score": desc.memory_score if desc else None,
            "tags": sorted(set(([t.tag_name for t in photo.tags]) + (_string_list(desc.tags) if desc else []))),
            "albums": [{"id": str(album.id), "name": album.name} for album in photo.albums],
            "people": people, "ocr": ocr_by_id.get(str(photo.id), []),
            "color": {"dominant_colors": color.dominant_colors, "brightness": color.brightness, "saturation": color.saturation, "emotion": color.emotion_hint} if color else None,
            "thumbnail_url": f"/api/medias/{photo.id}/thumbnail",
        })
    return result


def search_ocr_rows(db: Session, user_id: str, query: str, limit: int = 30) -> list[dict]:
    rows = (
        db.query(OCR, Photo)
        .join(Photo, Photo.id == OCR.photo_id)
        .filter(Photo.owner_id == user_id, Photo.is_deleted.is_(False), OCR.text.ilike(f"%{query}%"))
        .order_by(OCR.text_score.desc(), Photo.photo_time.desc())
        .limit(min(max(limit, 1), 50)).all()
    )
    return [{"photo_id": str(p.id), "photo_time": _iso(p.photo_time), "text": o.text, "confidence": o.text_score, "thumbnail_url": f"/api/medias/{p.id}/thumbnail"} for o, p in rows]


def trip_tickets(db: Session, user_id: str, start_date: str | None, end_date: str | None) -> list[dict]:
    start = datetime.strptime(start_date, "%Y-%m-%d") if start_date else None
    end = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1) if end_date else None
    result = []
    for model, kind in ((TrainTicket, "train"), (FlightTicket, "flight")):
        query = db.query(model).filter(model.owner_id == user_id)
        if start: query = query.filter(model.date_time >= start)
        if end: query = query.filter(model.date_time < end)
        for row in query.order_by(model.date_time).all():
            result.append({
                "ticket_id": row.id, "type": kind, "date_time": _iso(row.date_time),
                "code": row.train_code if kind == "train" else row.flight_code,
                "departure": row.departure_station if kind == "train" else row.departure_city,
                "arrival": row.arrival_station if kind == "train" else row.arrival_city,
                "photo_id": str(row.photo_id) if row.photo_id else None,
            })
    return sorted(result, key=lambda item: item["date_time"] or "")


def travel_timeline(db: Session, user_id: str, start_date: str | None, end_date: str | None) -> dict:
    query = db.query(Photo, PhotoMetadata).join(PhotoMetadata, Photo.id == PhotoMetadata.photo_id).filter(Photo.owner_id == user_id, Photo.is_deleted.is_(False), Photo.photo_time.isnot(None))
    if start_date: query = query.filter(Photo.photo_time >= datetime.strptime(start_date, "%Y-%m-%d"))
    if end_date: query = query.filter(Photo.photo_time < datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1))
    total_photos = query.order_by(None).count()
    groups = {}
    for photo, meta in query.order_by(Photo.photo_time).limit(2000).all():
        key = (photo.photo_time.date().isoformat(), meta.city or meta.province or meta.country or "未知地点")
        group = groups.setdefault(key, {"date": key[0], "location": key[1], "photo_count": 0, "photo_ids": []})
        group["photo_count"] += 1
        if len(group["photo_ids"]) < 12: group["photo_ids"].append(str(photo.id))
    return {"total_photos": total_photos, "truncated": total_photos > 2000, "segments": list(groups.values()), "tickets": trip_tickets(db, user_id, start_date, end_date)}


def discover_travel_periods(
    db: Session,
    user_id: str,
    start_date: str | None = None,
    end_date: str | None = None,
    min_photos: int = 12,
    max_results: int = 8,
) -> dict:
    """Discover deterministic, explainable travel candidates from dated locations.

    Consecutive shooting days separated by at most two empty days form one
    candidate. This intentionally proposes candidates instead of declaring a
    trip as fact; the Agent and user can narrow the result before writing.
    """
    query = (
        db.query(Photo, PhotoMetadata)
        .join(PhotoMetadata, Photo.id == PhotoMetadata.photo_id)
        .filter(
            Photo.owner_id == user_id,
            Photo.is_deleted.is_(False),
            Photo.photo_time.isnot(None),
            or_(
                PhotoMetadata.city.isnot(None),
                PhotoMetadata.province.isnot(None),
                PhotoMetadata.country.isnot(None),
            ),
        )
    )
    if start_date:
        query = query.filter(Photo.photo_time >= datetime.strptime(start_date, "%Y-%m-%d"))
    if end_date:
        query = query.filter(Photo.photo_time < datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1))

    rows = list(reversed(query.order_by(Photo.photo_time.desc()).limit(10_000).all()))
    days: dict = {}
    for photo, meta in rows:
        day = photo.photo_time.date()
        location = meta.city or meta.province or meta.country
        if not location:
            continue
        bucket = days.setdefault(day, {"date": day, "photo_ids": [], "locations": Counter()})
        if len(bucket["photo_ids"]) < 200:
            bucket["photo_ids"].append(str(photo.id))
        bucket["locations"][location] += 1

    segments = []
    for item in sorted(days.values(), key=lambda value: value["date"]):
        if not segments or (item["date"] - segments[-1][-1]["date"]).days > 3:
            segments.append([item])
        else:
            segments[-1].append(item)

    threshold = min(max(int(min_photos), 3), 1000)
    candidates = []
    all_tickets = trip_tickets(db, user_id, start_date, end_date)
    for segment in segments:
        photo_ids = []
        locations = Counter()
        for day in segment:
            photo_ids.extend(day["photo_ids"])
            locations.update(day["locations"])
        if len(photo_ids) < threshold:
            continue
        start = segment[0]["date"]
        end = segment[-1]["date"]
        segment_tickets = [
            ticket for ticket in all_tickets
            if ticket.get("date_time") and start.isoformat() <= ticket["date_time"][:10] <= end.isoformat()
        ]
        top_locations = [name for name, _ in locations.most_common(5)]
        candidates.append({
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "day_count": (end - start).days + 1,
            "shooting_day_count": len(segment),
            "photo_count": len(photo_ids),
            "locations": top_locations,
            "title_suggestion": " · ".join(top_locations[:2]) + "旅行",
            "photo_ids": photo_ids[:200],
            "ticket_ids": [str(ticket["ticket_id"]) for ticket in segment_tickets],
            "reason": "连续拍摄日期、地点聚合" + ("，并匹配到行程票据" if segment_tickets else ""),
        })

    candidates.sort(key=lambda item: (item["start_date"], item["photo_count"]), reverse=True)
    result_limit = min(max(int(max_results), 1), 12)
    return {
        "candidates": candidates[:result_limit],
        "candidate_count": len(candidates),
        "scanned_photo_count": len(rows),
        "truncated": len(rows) >= 10_000,
        "notice": "结果是基于连续日期和地点生成的候选，请在创建相册前由用户确认范围。",
    }


def album_health_report(
    db: Session,
    user_id: str,
    album_id: str | None = None,
    sample_limit: int = 8,
) -> dict:
    """Return an owner-scoped, read-only diagnosis of library hygiene."""
    owner_id = UUID(str(user_id))
    limit = min(max(int(sample_limit), 1), 20)
    album = None
    if album_id:
        try:
            parsed_album_id = UUID(str(album_id))
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValueError("无效的相册 ID") from exc
        album = db.query(Album).filter(Album.id == parsed_album_id, Album.owner_id == owner_id).first()
        if not album:
            raise ValueError("相册不存在或无权访问")

    def scoped_photos():
        query = db.query(Photo).filter(Photo.owner_id == owner_id, Photo.is_deleted.is_(False))
        if album:
            query = query.join(AlbumPhoto, AlbumPhoto.photo_id == Photo.id).filter(AlbumPhoto.album_id == album.id)
        return query

    def issue(key: str, label: str, query, recommendation: str, severity: str = "medium") -> dict:
        count = query.order_by(None).count()
        samples = [str(row[0]) for row in query.with_entities(Photo.id).order_by(Photo.photo_time.desc().nulls_last()).limit(limit).all()]
        return {
            "key": key, "label": label, "severity": severity, "count": count,
            "sample_photo_ids": samples, "recommendation": recommendation,
        }

    base = scoped_photos()
    issues = [
        issue("missing_time", "缺少拍摄时间", base.filter(Photo.photo_time.is_(None)), "可使用文件名推断时间工具，确认后再写入。", "high"),
        issue(
            "missing_location", "缺少地点", base.outerjoin(PhotoMetadata, PhotoMetadata.photo_id == Photo.id).filter(
                PhotoMetadata.city.is_(None), PhotoMetadata.province.is_(None),
                PhotoMetadata.country.is_(None), PhotoMetadata.latitude.is_(None), PhotoMetadata.longitude.is_(None),
            ), "结合相邻照片、票据和 OCR 推断候选地点，不应自动写入。",
        ),
        issue(
            "missing_description", "缺少 AI 视觉描述", base.outerjoin(ImageDescription, ImageDescription.photo_id == Photo.id).filter(
                or_(ImageDescription.id.is_(None), ImageDescription.description.is_(None))
            ), "运行视觉描述任务，提升自然语言检索和故事生成质量。", "low",
        ),
        issue(
            "missing_hash", "缺少文件指纹", base.filter(or_(Photo.md5.is_(None), Photo.md5 == "")),
            "先运行重复照片扫描补齐 MD5，再判断重复项。", "low",
        ),
    ]

    unassigned_count = None
    if not album:
        unassigned = base.filter(~db.query(AlbumPhoto.id).filter(AlbumPhoto.photo_id == Photo.id).exists())
        unassigned_issue = issue(
            "unassigned", "未加入任何相册", unassigned,
            "可按时间和地点分组，由 Agent 生成待确认的相册整理计划。",
        )
        issues.append(unassigned_issue)
        unassigned_count = unassigned_issue["count"]

    scoped_ids = base.with_entities(Photo.id).order_by(None).subquery()
    duplicate_rows = (
        db.query(Photo.md5, func.count(Photo.id).label("count"))
        .filter(Photo.id.in_(db.query(scoped_ids.c.id)), Photo.md5.isnot(None), Photo.md5 != "")
        .group_by(Photo.md5).having(func.count(Photo.id) > 1).order_by(func.count(Photo.id).desc()).all()
    )
    duplicate_groups = len(duplicate_rows)
    duplicate_extra = sum(int(row.count) - 1 for row in duplicate_rows)
    duplicate_samples = []
    if duplicate_rows:
        hashes = [row.md5 for row in duplicate_rows[:limit]]
        duplicate_samples = [str(row[0]) for row in base.with_entities(Photo.id).filter(Photo.md5.in_(hashes)).limit(limit).all()]
    issues.append({
        "key": "exact_duplicates", "label": "完全重复照片", "severity": "high",
        "count": duplicate_extra, "group_count": duplicate_groups,
        "sample_photo_ids": duplicate_samples,
        "recommendation": "请在工具箱手动复核后清理，Agent 不会自动删除原文件。",
    })

    album_rows: list[dict] = []
    if not album:
        rows = (
            db.query(Album.id, Album.name, Album.num_photos, Album.cover_id, func.count(AlbumPhoto.id).label("actual_count"))
            .outerjoin(AlbumPhoto, AlbumPhoto.album_id == Album.id)
            .filter(Album.owner_id == owner_id, Album.type == "user")
            .group_by(Album.id, Album.name, Album.num_photos, Album.cover_id).all()
        )
        album_rows = [{
            "id": row.id, "name": row.name, "num_photos": row.num_photos,
            "cover_id": row.cover_id, "actual_count": row.actual_count,
        } for row in rows]
    elif album.type == "user":
        actual = db.query(func.count(AlbumPhoto.id)).filter(AlbumPhoto.album_id == album.id).scalar() or 0
        album_rows = [{
            "id": album.id, "name": album.name, "num_photos": album.num_photos,
            "cover_id": album.cover_id, "actual_count": actual,
        }]
    empty_albums = [{"album_id": str(row["id"]), "name": row["name"]} for row in album_rows if int(row["actual_count"]) == 0]
    count_mismatches = [{
        "album_id": str(row["id"]), "name": row["name"],
        "stored_count": int(row["num_photos"] or 0), "actual_count": int(row["actual_count"]),
    } for row in album_rows if int(row["num_photos"] or 0) != int(row["actual_count"])]
    missing_covers = [{"album_id": str(row["id"]), "name": row["name"]} for row in album_rows if int(row["actual_count"]) > 0 and not row["cover_id"]]

    active_issues = [item for item in issues if item["count"] > 0]
    high_count = sum(1 for item in active_issues if item["severity"] == "high")
    album_issue_types = sum(bool(items) for items in (empty_albums, count_mismatches, missing_covers))
    return {
        "scope": {"type": "album" if album else "library", "album_id": str(album.id) if album else None, "album_name": album.name if album else None},
        "photo_count": base.order_by(None).count(),
        "health_score": max(0, 100 - high_count * 18 - max(0, len(active_issues) - high_count) * 7 - album_issue_types * 7),
        "issues": issues,
        "album_issues": {
            "empty_albums": empty_albums, "count_mismatches": count_mismatches, "missing_covers": missing_covers,
        },
        "summary": {
            "active_issue_types": len(active_issues) + album_issue_types, "high_priority_issue_types": high_count,
            "unassigned_photo_count": unassigned_count,
        },
        "notice": "这是只读体检。任何写入或删除都需要独立的预览和用户确认。",
    }


def investigate_memory_clues(
    db: Session,
    user_id: str,
    query_text: str,
    start_date: str | None = None,
    end_date: str | None = None,
    locations: list[str] | None = None,
    persons: list[str] | None = None,
    text_terms: list[str] | None = None,
    semantic_photo_ids: list[str] | None = None,
    max_events: int = 8,
) -> dict:
    """Fuse vague memory clues into explainable, owner-scoped event candidates."""
    owner_id = UUID(str(user_id))
    locations = list(dict.fromkeys(str(item).strip() for item in (locations or []) if str(item).strip()))[:8]
    persons = list(dict.fromkeys(str(item).strip() for item in (persons or []) if str(item).strip()))[:8]
    text_terms = list(dict.fromkeys(str(item).strip() for item in (text_terms or []) if str(item).strip()))[:12]
    semantic_ids = _uuid_list(semantic_photo_ids or [], 50)
    event_limit = min(max(int(max_events), 1), 12)

    def parse_date(value: str | None, label: str) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.strptime(value, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError(f"{label}格式必须为 YYYY-MM-DD") from exc

    start = parse_date(start_date, "开始日期")
    end = parse_date(end_date, "结束日期")
    if start and end and start > end:
        raise ValueError("开始日期不能晚于结束日期")
    if not any((start, end, locations, persons, text_terms, semantic_ids)):
        raise ValueError("至少需要日期、地点、人物、文字或语义照片中的一种可检索线索")

    base = (
        db.query(Photo)
        .options(
            joinedload(Photo.metadata_info).joinedload(PhotoMetadata.scene),
            joinedload(Photo.image_description),
            joinedload(Photo.faces).joinedload(Face.identity),
        )
        .outerjoin(PhotoMetadata, PhotoMetadata.photo_id == Photo.id)
        .outerjoin(ImageDescription, ImageDescription.photo_id == Photo.id)
        .filter(Photo.owner_id == owner_id, Photo.is_deleted.is_(False))
    )
    if start:
        base = base.filter(Photo.photo_time >= start)
    if end:
        base = base.filter(Photo.photo_time < end + timedelta(days=1))

    recall_conditions = []
    for location in locations:
        pattern = f"%{location}%"
        recall_conditions.append(or_(
            PhotoMetadata.country.ilike(pattern), PhotoMetadata.province.ilike(pattern),
            PhotoMetadata.city.ilike(pattern), PhotoMetadata.district.ilike(pattern),
            PhotoMetadata.address.ilike(pattern),
        ))
    for person in persons:
        recall_conditions.append(Photo.faces.any(and_(
            Face.is_deleted.is_(False),
            Face.identity.has(and_(
                FaceIdentity.owner_id == owner_id,
                FaceIdentity.is_deleted.is_(False),
                FaceIdentity.is_hidden.is_(False),
                FaceIdentity.identity_name.ilike(f"%{person}%"),
            )),
        )))
    for term in text_terms:
        pattern = f"%{term}%"
        recall_conditions.append(or_(
            ImageDescription.description.ilike(pattern), ImageDescription.narrative.ilike(pattern),
            db.query(OCR.id).filter(OCR.photo_id == Photo.id, OCR.text.ilike(pattern)).exists(),
        ))
    if semantic_ids:
        recall_conditions.append(Photo.id.in_(semantic_ids))
    if recall_conditions:
        base = base.filter(or_(*recall_conditions))

    total_candidates = base.order_by(None).count()
    photos = base.order_by(Photo.photo_time.desc().nulls_last()).limit(1000).all()
    photo_ids = [photo.id for photo in photos]
    ocr_by_photo: dict[str, list[str]] = defaultdict(list)
    if photo_ids:
        for photo_id, text in db.query(OCR.photo_id, OCR.text).filter(OCR.photo_id.in_(photo_ids)).all():
            if text and len(ocr_by_photo[str(photo_id)]) < 20:
                ocr_by_photo[str(photo_id)].append(text)

    semantic_set = {str(item) for item in semantic_ids}
    evidence_rows = []
    for photo in photos:
        meta, desc = photo.metadata_info, photo.image_description
        location_text = " ".join(filter(None, [
            meta.country if meta else None, meta.province if meta else None, meta.city if meta else None,
            meta.district if meta else None, meta.address if meta else None,
            meta.scene.name if meta and meta.scene else None,
        ]))
        people = sorted({
            face.identity.identity_name for face in photo.faces
            if not face.is_deleted and face.identity and not face.identity.is_deleted
            and not face.identity.is_hidden and face.identity.identity_name
        })
        description_text = " ".join(filter(None, [desc.description if desc else None, desc.narrative if desc else None]))
        ocr_text = " ".join(ocr_by_photo.get(str(photo.id), []))
        location_hits = [item for item in locations if item.lower() in location_text.lower()]
        person_hits = [item for item in persons if any(item.lower() in name.lower() for name in people)]
        description_hits = [item for item in text_terms if item.lower() in description_text.lower()]
        ocr_hits = [item for item in text_terms if item.lower() in ocr_text.lower()]
        matched_types = []
        score = 0
        if start or end:
            matched_types.append("time"); score += 1
        if location_hits:
            matched_types.append("location"); score += 3 + min(len(location_hits) - 1, 2)
        if person_hits:
            matched_types.append("person"); score += 4 + min(len(person_hits) - 1, 2)
        if description_hits:
            matched_types.append("description"); score += 2 + min(len(description_hits) - 1, 2)
        if ocr_hits:
            matched_types.append("ocr"); score += 3 + min(len(ocr_hits) - 1, 2)
        if str(photo.id) in semantic_set:
            matched_types.append("semantic"); score += 2
        evidence_rows.append({
            "photo_id": str(photo.id), "photo_time": _iso(photo.photo_time), "score": score,
            "matched_types": matched_types,
            "matched_clues": sorted(set(location_hits + person_hits + description_hits + ocr_hits)),
            "location": location_text or None, "people": people,
            "description": (desc.narrative or desc.description)[:240] if desc and (desc.narrative or desc.description) else None,
            "ocr_samples": ocr_by_photo.get(str(photo.id), [])[:3],
            "thumbnail_url": f"/api/medias/{photo.id}/thumbnail",
        })

    dated = sorted((row for row in evidence_rows if row["photo_time"]), key=lambda row: row["photo_time"])
    groups: list[list[dict]] = []
    for row in dated:
        current_time = datetime.fromisoformat(row["photo_time"])
        current_date = current_time.date()
        if not groups:
            groups.append([row])
            continue
        previous_time = datetime.fromisoformat(groups[-1][-1]["photo_time"])
        previous_date = previous_time.date()
        group_start = datetime.fromisoformat(groups[-1][0]["photo_time"]).date()
        same_day_long_gap = (
            current_date == previous_date
            and current_time - previous_time > timedelta(hours=6)
        )
        if (
            (current_date - previous_date).days <= 2
            and (current_date - group_start).days <= 6
            and not same_day_long_gap
        ):
            groups[-1].append(row)
        else:
            groups.append([row])

    events = []
    for group in groups:
        ranked = sorted(group, key=lambda row: (-row["score"], row["photo_time"]))
        clue_types = sorted(set(item for row in group for item in row["matched_types"] if item != "time"))
        locations_found = []
        people_found = []
        for row in ranked:
            if row["location"] and row["location"] not in locations_found:
                locations_found.append(row["location"])
            for person in row["people"]:
                if person not in people_found:
                    people_found.append(person)
        strongest = sorted((row["score"] for row in group), reverse=True)[:12]
        events.append({
            "start_date": group[0]["photo_time"][:10], "end_date": group[-1]["photo_time"][:10],
            "photo_count": len(group), "evidence_score": sum(strongest) + len(clue_types) * 5,
            "confidence": "high" if len(clue_types) >= 3 else "medium" if len(clue_types) >= 2 else "low",
            "matched_types": clue_types, "locations": locations_found[:8], "people": people_found[:8],
            "evidence_photos": ranked[:12],
        })
    events.sort(key=lambda item: (-item["evidence_score"], -item["photo_count"], item["start_date"]))
    unplaced = sorted((row for row in evidence_rows if not row["photo_time"]), key=lambda row: -row["score"])
    return {
        "query": query_text[:500], "total_candidate_photo_count": total_candidates,
        "candidate_photo_count": len(evidence_rows), "photos_truncated": total_candidates > len(evidence_rows),
        "candidate_event_count": len(events), "events": events[:event_limit],
        "events_truncated": len(events) > event_limit,
        "unplaced_photo_count": len(unplaced), "unplaced_evidence_photos": unplaced[:12],
        "search_clues": {
            "start_date": start_date, "end_date": end_date, "locations": locations,
            "persons": persons, "text_terms": text_terms, "semantic_photo_count": len(semantic_ids),
        },
        "notice": "这些是线索匹配得到的候选事件，不是已确认事实；请结合缩略图和完整照片上下文复核。",
    }


def select_representatives(db: Session, user_id: str, photo_ids: list[str], count: int) -> list[dict]:
    from app.service.moment.day_highlight_service import dedup_photo_ids

    ordered = _uuid_list(photo_ids, 200)
    deduped = dedup_photo_ids(db, UUID(str(user_id)), ordered)
    contexts = photo_contexts(db, user_id, [str(photo_id) for photo_id in deduped])
    count = min(max(count, 1), 16)
    selected, used_days, used_locations, used_people = [], Counter(), Counter(), Counter()
    remaining = list(contexts)
    while remaining and len(selected) < count:
        def score(item):
            quality = float(item.get("quality_score") or 0) / 100
            memory = float(item.get("memory_score") or 0) / 100
            day = (item.get("photo_time") or "")[:10]
            location = ((item.get("location") or {}).get("city") or (item.get("location") or {}).get("province") or "")
            people = item.get("people") or []
            diversity = (0.3 if not used_days[day] else 0) + (0.25 if location and not used_locations[location] else 0) + (0.15 if any(not used_people[p] for p in people) else 0)
            return quality * .45 + memory * .25 + diversity
        best = max(remaining, key=score)
        remaining.remove(best)
        day = (best.get("photo_time") or "")[:10]
        location = ((best.get("location") or {}).get("city") or (best.get("location") or {}).get("province") or "")
        used_days[day] += 1; used_locations[location] += 1
        for person in best.get("people") or []: used_people[person] += 1
        best["selection_reason"] = "兼顾画面质量、回忆价值与时间/地点/人物多样性"
        selected.append(best)
    return selected


def contact_sheet_content(db: Session, user_id: str, photo_ids: list[str]) -> list[dict]:
    """Return one compact numbered image as a multimodal tool-result block."""
    ids = _uuid_list(photo_ids, 16)
    photos = db.query(Photo).filter(Photo.owner_id == user_id, Photo.is_deleted.is_(False), Photo.id.in_(ids)).all()
    by_id = {str(photo.id): photo for photo in photos}
    cells = []
    resolved_ids = []
    for photo_id in ids:
        photo = by_id.get(str(photo_id))
        if not photo:
            continue
        path = get_preview_path(UUID(str(user_id)), photo.id) or get_available_photo_path(UUID(str(user_id)), photo.id, photo.file_path)
        if not path:
            continue
        try:
            with Image.open(path) as source:
                frame = source.convert("RGB")
                cell = ImageOps.fit(frame, (256, 256), method=Image.Resampling.LANCZOS)
        except Exception:
            continue
        cells.append(cell)
        resolved_ids.append(str(photo.id))
    if not cells:
        return [{"type": "text", "text": json.dumps({"type": "contact_sheet", "items": [], "warning": "没有可读取的缩略图"}, ensure_ascii=False)}]
    columns = 4
    rows = (len(cells) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * 256, rows * 286), "white")
    draw = ImageDraw.Draw(sheet)
    for index, cell in enumerate(cells):
        x, y = index % columns * 256, index // columns * 286
        sheet.paste(cell, (x, y))
        draw.rectangle((x, y + 256, x + 256, y + 286), fill="white")
        draw.text((x + 8, y + 263), f"#{index + 1}", fill="black")
    output = BytesIO()
    sheet.save(output, format="JPEG", quality=72, optimize=True)
    encoded = base64.b64encode(output.getvalue()).decode("ascii")
    mapping = {str(index + 1): photo_id for index, photo_id in enumerate(resolved_ids)}
    return [
        {"type": "text", "text": json.dumps({"type": "contact_sheet", "index_to_photo_id": mapping, "instruction": "请直接观察联系表中的画面，用编号比较构图、清晰度、内容和重复度。"}, ensure_ascii=False)},
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{encoded}"}},
    ]


def create_artifact(db: Session, user_id: str, session_id: str | None, artifact_type: str, title: str, content: dict, photo_ids: list[str], ticket_ids: list[str]) -> AIArtifact:
    normalized_photo_ids = [str(item) for item in _uuid_list(photo_ids, 100)]
    if len(normalized_photo_ids) != len(set(photo_ids[:100])):
        raise ValueError("包含无效的照片 ID")
    owned = db.query(Photo.id).filter(Photo.owner_id == user_id, Photo.is_deleted.is_(False), Photo.id.in_(normalized_photo_ids)).all()
    owned_ids = {str(row[0]) for row in owned}
    if set(normalized_photo_ids) - owned_ids:
        raise ValueError("包含不存在或无权访问的照片")
    requested_ticket_ids = list(dict.fromkeys(ticket_ids))[:50]
    owned_ticket_ids = {
        str(row[0]) for row in db.query(TrainTicket.id).filter(TrainTicket.owner_id == user_id, TrainTicket.id.in_(requested_ticket_ids)).all()
    } | {
        str(row[0]) for row in db.query(FlightTicket.id).filter(FlightTicket.owner_id == user_id, FlightTicket.id.in_(requested_ticket_ids)).all()
    }
    if set(requested_ticket_ids) - owned_ticket_ids:
        raise ValueError("包含不存在或无权访问的票据")
    row = AIArtifact(user_id=UUID(str(user_id)), artifact_type=artifact_type, title=title[:255], content_json=_normalize_artifact_content(content), source_photo_ids=normalized_photo_ids, source_ticket_ids=requested_ticket_ids, status="draft", created_by_session_id=UUID(session_id) if session_id else None)
    db.add(row); db.commit(); db.refresh(row)
    return row


def save_artifact_html(
    db: Session,
    user_id: str,
    artifact_id: str,
    html_content: str,
    style_name: str,
    custom_style: str | None,
    server_api_access: bool,
) -> AIArtifact:
    """Attach an agent-authored interactive page to an owned structured artifact."""
    if not html_content.strip():
        raise ValueError("HTML 内容不能为空")
    if len(html_content) > 500_000:
        raise ValueError("HTML 内容不能超过 500KB")
    try:
        parsed_id = UUID(str(artifact_id))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError("无效的作品 ID") from exc
    row = db.query(AIArtifact).filter(AIArtifact.id == parsed_id, AIArtifact.user_id == user_id).first()
    if not row:
        raise ValueError("作品不存在或无权访问")
    _validate_static_artifact_html(html_content, row.source_photo_ids or [])
    row.html_content = html_content
    row.html_config = {
        "style_name": (style_name or "custom")[:50],
        "custom_style": (custom_style or "")[:1000],
        "server_api_access": bool(server_api_access),
        "runtime": "sandbox-v1",
    }
    row.version += 1
    db.commit()
    db.refresh(row)
    return row


def artifact_context(db: Session, user_id: str, artifact_id: str) -> dict:
    try:
        parsed_id = UUID(str(artifact_id))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError("无效的作品 ID") from exc
    row = db.query(AIArtifact).filter(AIArtifact.id == parsed_id, AIArtifact.user_id == user_id).first()
    if not row:
        raise ValueError("作品不存在或无权访问")
    return {
        "id": str(row.id), "artifact_type": row.artifact_type, "title": row.title,
        "content": row.content_json, "photo_ids": row.source_photo_ids,
        "ticket_ids": row.source_ticket_ids, "html_config": row.html_config,
        "has_html": bool(row.html_content),
    }
