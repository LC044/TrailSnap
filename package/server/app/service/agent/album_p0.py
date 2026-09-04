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
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.db.models import AIArtifact
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
    row = AIArtifact(user_id=UUID(str(user_id)), artifact_type=artifact_type, title=title[:255], content_json=content, source_photo_ids=normalized_photo_ids, source_ticket_ids=requested_ticket_ids, status="draft", created_by_session_id=UUID(session_id) if session_id else None)
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
