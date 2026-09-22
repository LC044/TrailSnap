"""Memory domain service: discovery, lifecycle, merge and split."""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from datetime import datetime, timedelta
from typing import Iterable
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.db.models.face import Face, FaceIdentity
from app.db.models.image_description import ImageDescription
from app.db.models.memory import (
    Memory,
    MemoryEvidence,
    MemoryOrigin,
    MemoryPerson,
    MemoryPhoto,
    MemoryPlace,
    MemoryRelation,
    MemoryStatus,
    MemoryTicket,
)
from app.db.models.photo import ImageType, Photo
from app.db.models.photo_metadata import PhotoMetadata
from app.db.models.trip import FlightTicket, TrainTicket
from app.schemas.memory import MemoryCreate, MemorySplitRequest, MemoryUpdate


ALGORITHM_VERSION = "memory-v2-location"
ACTIVE_STATUSES = (MemoryStatus.CANDIDATE, MemoryStatus.CONFIRMED, MemoryStatus.ARCHIVED)


def _normalize_ai_story(value: str) -> str:
    story = re.sub(r"<think>[\s\S]*?</think>", "", value, flags=re.IGNORECASE).strip()
    story = re.sub(r"^#{1,6}\s*[^\n]*\n+", "", story).strip()
    if len(story) <= 420:
        return story
    window = story[:420]
    endings = [window.rfind(mark) for mark in "。！？"]
    cutoff = max(endings)
    if cutoff >= 180:
        return window[:cutoff + 1].strip()
    return window.rstrip("，,；;：: ") + "。"


def get_owned(db: Session, memory_id: UUID | str, owner_id: UUID | str, *, for_update: bool = False) -> Memory | None:
    query = db.query(Memory).filter(
        Memory.id == memory_id,
        Memory.owner_id == owner_id,
        Memory.status != MemoryStatus.DELETED,
    )
    if for_update:
        query = query.populate_existing().with_for_update()
    return query.first()


def _require_owned(db: Session, memory_id: UUID | str, owner_id: UUID | str, *, for_update: bool = False) -> Memory:
    memory = get_owned(db, memory_id, owner_id, for_update=for_update)
    if not memory:
        raise HTTPException(status_code=404, detail="记忆不存在")
    return memory


def _owned_photos(db: Session, owner_id: UUID | str, photo_ids: Iterable[UUID | str]) -> list[Photo]:
    ids = list(dict.fromkeys(photo_ids))
    if not ids:
        return []
    photos = db.query(Photo).filter(
        Photo.id.in_(ids), Photo.owner_id == owner_id, Photo.is_deleted.is_(False)
    ).all()
    if len(photos) != len(ids):
        raise HTTPException(status_code=400, detail="部分照片不存在或不属于当前用户")
    by_id = {str(photo.id): photo for photo in photos}
    return [by_id[str(photo_id)] for photo_id in ids]


def _photo_dict(photo: Photo) -> dict:
    metadata = photo.metadata_info
    return {
        "id": str(photo.id),
        "filename": photo.filename,
        "photo_time": photo.photo_time.isoformat() if photo.photo_time else None,
        "file_type": photo.file_type.value if photo.file_type else None,
        "width": photo.width,
        "height": photo.height,
        "city": metadata.city if metadata else None,
        "province": metadata.province if metadata else None,
    }


def _ticket_dict(db: Session, link: MemoryTicket) -> dict:
    if link.ticket_type == "train":
        row = db.query(TrainTicket).filter(TrainTicket.id == link.ticket_id).first()
        if not row:
            return {"type": "train", "id": link.ticket_id}
        return {
            "type": "train", "id": row.id, "code": row.train_code,
            "from": row.departure_station, "to": row.arrival_station,
            "date_time": row.date_time.isoformat(), "confirmed": link.is_confirmed,
        }
    row = db.query(FlightTicket).filter(FlightTicket.id == link.ticket_id).first()
    if not row:
        return {"type": "flight", "id": link.ticket_id}
    return {
        "type": "flight", "id": row.id, "code": row.flight_code,
        "from": row.departure_city, "to": row.arrival_city,
        "date_time": row.date_time.isoformat(), "confirmed": link.is_confirmed,
    }


def serialize(db: Session, memory: Memory, *, detail: bool = False) -> dict:
    photo_links = sorted(
        memory.photo_links,
        key=lambda link: (link.photo.photo_time or datetime.min, link.sort_order),
    )
    data = {
        "id": str(memory.id),
        "status": memory.status.value,
        "origin": memory.origin.value,
        "title": memory.title,
        "title_source": memory.title_source,
        "story": memory.story,
        "story_source": memory.story_source,
        "story_generation_status": memory.story_generation_status or "idle",
        "story_generation_started_at": memory.story_generation_started_at.isoformat() if memory.story_generation_started_at else None,
        "story_generation_error": memory.story_generation_error,
        "cover_photo_id": str(memory.cover_photo_id) if memory.cover_photo_id else None,
        "start_time": memory.start_time.isoformat() if memory.start_time else None,
        "end_time": memory.end_time.isoformat() if memory.end_time else None,
        "time_source": memory.time_source,
        "confidence_level": "strong" if (memory.confidence or 0) >= 0.75 else "review",
        "photo_count": len(photo_links),
        "places": [
            {"id": place.id, "name": place.name, "level": place.level, "confirmed": place.is_confirmed}
            for place in memory.places
        ],
        "people": [
            {
                "id": str(person.face_identity_id),
                "name": person.identity.identity_name or "未命名人物",
                "default_face_id": person.identity.default_face_id,
                "confirmed": person.is_confirmed,
            }
            for person in memory.people
        ],
        "evidence": [
            {"id": item.id, "type": item.evidence_type, "summary": item.summary, "score": item.score}
            for item in memory.evidence
        ],
        "created_at": memory.created_at.isoformat(),
        "updated_at": memory.updated_at.isoformat(),
        "confirmed_at": memory.confirmed_at.isoformat() if memory.confirmed_at else None,
        "ignored_at": memory.ignored_at.isoformat() if memory.ignored_at else None,
        "version": memory.version,
    }
    if detail:
        data["photos"] = [_photo_dict(link.photo) for link in photo_links]
        data["tickets"] = [_ticket_dict(db, ticket) for ticket in memory.tickets]
    else:
        data["preview_photo_ids"] = [str(link.photo_id) for link in photo_links[:4]]
    return data


def list_owned(
    db: Session,
    owner_id: UUID | str,
    status: MemoryStatus,
    skip: int = 0,
    limit: int = 20,
) -> tuple[list[Memory], int]:
    query = db.query(Memory).filter(Memory.owner_id == owner_id, Memory.status == status)
    total = query.count()
    rows = (
        query.options(
            joinedload(Memory.photo_links).joinedload(MemoryPhoto.photo).joinedload(Photo.metadata_info),
            joinedload(Memory.people).joinedload(MemoryPerson.identity),
            joinedload(Memory.places), joinedload(Memory.evidence),
        )
        .order_by(Memory.start_time.desc().nullslast(), Memory.updated_at.desc())
        .offset(skip).limit(limit).all()
    )
    return rows, total


def get_detail(db: Session, memory_id: UUID | str, owner_id: UUID | str) -> Memory:
    row = (
        db.query(Memory)
        .options(
            joinedload(Memory.photo_links).joinedload(MemoryPhoto.photo).joinedload(Photo.metadata_info),
            joinedload(Memory.people).joinedload(MemoryPerson.identity),
            joinedload(Memory.places), joinedload(Memory.tickets), joinedload(Memory.evidence),
        )
        .filter(Memory.id == memory_id, Memory.owner_id == owner_id, Memory.status != MemoryStatus.DELETED)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="记忆不存在")
    return row


def _set_photos(memory: Memory, photos: list[Photo], *, source: str, confirmed: bool) -> None:
    memory.photo_links.clear()
    for index, photo in enumerate(sorted(photos, key=lambda item: item.photo_time or datetime.min)):
        memory.photo_links.append(MemoryPhoto(
            photo=photo, source=source, is_confirmed=confirmed, sort_order=index,
        ))


def _set_people(db: Session, memory: Memory, owner_id: UUID | str, person_ids: list[UUID], *, confirmed: bool) -> None:
    if not person_ids:
        memory.people.clear()
        return
    identities = db.query(FaceIdentity).filter(
        FaceIdentity.id.in_(person_ids), FaceIdentity.owner_id == owner_id,
        FaceIdentity.is_deleted.is_(False),
    ).all()
    if len(identities) != len(set(person_ids)):
        raise HTTPException(status_code=400, detail="部分人物不存在或不属于当前用户")
    memory.people = [MemoryPerson(identity=item, source="user", is_confirmed=confirmed) for item in identities]


def _set_places(memory: Memory, place_names: list[str], *, confirmed: bool) -> None:
    names = list(dict.fromkeys(name.strip() for name in place_names if name.strip()))
    memory.places = [
        MemoryPlace(name=name, level="custom", source="user", is_confirmed=confirmed)
        for name in names
    ]


def _set_tickets(db: Session, memory: Memory, owner_id: UUID | str, refs: list[dict], *, confirmed: bool) -> None:
    links: list[MemoryTicket] = []
    for ref in refs:
        kind = ref.get("type")
        ticket_id = ref.get("id")
        if kind not in {"train", "flight"} or not ticket_id:
            raise HTTPException(status_code=400, detail="票据引用格式错误")
        model = TrainTicket if kind == "train" else FlightTicket
        if not db.query(model).filter(model.id == ticket_id, model.owner_id == owner_id).first():
            raise HTTPException(status_code=400, detail="票据不存在或不属于当前用户")
        links.append(MemoryTicket(
            ticket_type=kind, ticket_id=ticket_id, source="user", is_confirmed=confirmed,
        ))
    memory.tickets = links


def create(db: Session, owner_id: UUID, payload: MemoryCreate) -> Memory:
    photos = _owned_photos(db, owner_id, payload.photo_ids)
    times = [photo.photo_time for photo in photos if photo.photo_time]
    memory = Memory(
        owner_id=owner_id,
        status=MemoryStatus.CONFIRMED,
        origin=MemoryOrigin(payload.origin),
        title=payload.title.strip(), title_source="user",
        story=payload.story, story_source="user" if payload.story else "system",
        cover_photo_id=payload.cover_photo_id or photos[0].id, cover_source="user",
        start_time=payload.start_time or (min(times) if times else None),
        end_time=payload.end_time or (max(times) if times else None),
        time_source="confirmed", confirmed_at=datetime.now(), confidence=1.0,
    )
    _set_photos(memory, photos, source="user_added", confirmed=True)
    _set_places(memory, payload.place_names, confirmed=True)
    _set_people(db, memory, owner_id, payload.person_ids, confirmed=True)
    _set_tickets(db, memory, owner_id, payload.ticket_refs, confirmed=True)
    db.add(memory)
    db.commit()
    return get_detail(db, memory.id, owner_id)


def update(db: Session, memory: Memory, owner_id: UUID, payload: MemoryUpdate) -> Memory:
    values = payload.model_dump(exclude_unset=True)
    if "title" in values:
        memory.title = values.pop("title").strip()
        memory.title_source = "user"
    if "story" in values:
        memory.story = values.pop("story")
        memory.story_source = "user"
    if "cover_photo_id" in values:
        cover_id = values.pop("cover_photo_id")
        if cover_id and not any(link.photo_id == cover_id for link in memory.photo_links):
            raise HTTPException(status_code=400, detail="封面必须属于记忆照片")
        memory.cover_photo_id = cover_id
        memory.cover_source = "user"
    if "start_time" in values or "end_time" in values:
        if "start_time" in values:
            memory.start_time = values.pop("start_time")
        if "end_time" in values:
            memory.end_time = values.pop("end_time")
        memory.time_source = "confirmed"
    if memory.start_time and memory.end_time and memory.start_time > memory.end_time:
        raise HTTPException(status_code=400, detail="开始时间不能晚于结束时间")
    if "place_names" in values:
        _set_places(memory, values.pop("place_names") or [], confirmed=True)
    if "person_ids" in values:
        _set_people(db, memory, owner_id, values.pop("person_ids") or [], confirmed=True)
    if "ticket_refs" in values:
        _set_tickets(db, memory, owner_id, values.pop("ticket_refs") or [], confirmed=True)
    memory.version += 1
    db.commit()
    return get_detail(db, memory.id, owner_id)


def change_status(db: Session, memory: Memory, status: MemoryStatus) -> Memory:
    now = datetime.now()
    memory.status = status
    memory.version += 1
    if status == MemoryStatus.CONFIRMED:
        memory.confirmed_at = now
        for link in memory.photo_links:
            link.is_confirmed = True
    elif status == MemoryStatus.IGNORED:
        memory.ignored_at = now
    elif status == MemoryStatus.DELETED:
        memory.deleted_at = now
    db.commit()
    return memory


def add_photos(db: Session, memory: Memory, owner_id: UUID, photo_ids: list[UUID]) -> Memory:
    photos = _owned_photos(db, owner_id, photo_ids)
    existing = {link.photo_id for link in memory.photo_links}
    next_order = max((link.sort_order for link in memory.photo_links), default=-1) + 1
    for photo in photos:
        if photo.id not in existing:
            memory.photo_links.append(MemoryPhoto(
                photo=photo, source="user_added", is_confirmed=True, sort_order=next_order,
            ))
            next_order += 1
    memory.version += 1
    db.commit()
    return get_detail(db, memory.id, owner_id)


def remove_photos(db: Session, memory: Memory, owner_id: UUID, photo_ids: list[UUID]) -> Memory:
    remove_set = set(photo_ids)
    remaining = [link for link in memory.photo_links if link.photo_id not in remove_set]
    if not remaining:
        raise HTTPException(status_code=400, detail="记忆至少保留一张照片")
    memory.photo_links = remaining
    if memory.cover_photo_id in remove_set:
        memory.cover_photo_id = remaining[0].photo_id
        memory.cover_source = "system"
    memory.version += 1
    db.commit()
    return get_detail(db, memory.id, owner_id)


def _fingerprint(photo_ids: list[UUID]) -> str:
    raw = "|".join(sorted(str(photo_id) for photo_id in photo_ids))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _choose_cover(db: Session, photo_ids: list[UUID]) -> UUID:
    scored = (
        db.query(ImageDescription.photo_id, ImageDescription.memory_score, ImageDescription.quality_score)
        .filter(ImageDescription.photo_id.in_(photo_ids)).all()
    )
    if not scored:
        return photo_ids[0]
    return max(scored, key=lambda row: float(row.memory_score or 0) + float(row.quality_score or 0)).photo_id


def _retire_legacy_candidates(db: Session, owner_id: UUID) -> int:
    """Remove unconfirmed candidates produced by older, location-optional rules."""
    rows = db.query(Memory).filter(
        Memory.owner_id == owner_id,
        Memory.status == MemoryStatus.CANDIDATE,
        Memory.origin == MemoryOrigin.AUTO,
        Memory.algorithm_version != ALGORITHM_VERSION,
    ).all()
    now = datetime.now()
    for row in rows:
        row.status = MemoryStatus.DELETED
        row.deleted_at = now
        row.candidate_fingerprint = None
    if rows:
        db.flush()
    return len(rows)


def _enrich_people(db: Session, memory: Memory, owner_id: UUID, photo_ids: list[UUID]) -> None:
    rows = (
        db.query(Face.face_identity_id, func.count(Face.id).label("count"))
        .join(FaceIdentity, FaceIdentity.id == Face.face_identity_id)
        .filter(
            Face.photo_id.in_(photo_ids), Face.face_identity_id.isnot(None), Face.is_deleted.is_(False),
            FaceIdentity.owner_id == owner_id, FaceIdentity.is_deleted.is_(False), FaceIdentity.is_hidden.is_(False),
        )
        .group_by(Face.face_identity_id).order_by(func.count(Face.id).desc()).limit(5).all()
    )
    memory.people = [
        MemoryPerson(face_identity_id=row.face_identity_id, source="inferred", confidence=min(1.0, row.count / max(1, len(photo_ids))))
        for row in rows
    ]
    if rows:
        memory.evidence.append(MemoryEvidence(
            evidence_type="people", summary=f"{len(rows)} 位人物在这段照片中重复出现",
            score=0.7, source_refs=[str(row.face_identity_id) for row in rows],
            payload={"counts": [row.count for row in rows]}, algorithm_version=ALGORITHM_VERSION,
        ))


def _attach_tickets(db: Session, memory: Memory, owner_id: UUID) -> None:
    if not memory.start_time or not memory.end_time:
        return
    start = memory.start_time - timedelta(hours=24)
    end = memory.end_time + timedelta(hours=6)
    trains = db.query(TrainTicket).filter(
        TrainTicket.owner_id == owner_id, TrainTicket.date_time >= start, TrainTicket.date_time <= end,
    ).all()
    flights = db.query(FlightTicket).filter(
        FlightTicket.owner_id == owner_id, FlightTicket.date_time >= start, FlightTicket.date_time <= end,
    ).all()
    for ticket in trains:
        memory.tickets.append(MemoryTicket(ticket_type="train", ticket_id=ticket.id, source="inferred", confidence=0.75))
    for ticket in flights:
        memory.tickets.append(MemoryTicket(ticket_type="flight", ticket_id=ticket.id, source="inferred", confidence=0.75))
    count = len(trains) + len(flights)
    if count:
        memory.evidence.append(MemoryEvidence(
            evidence_type="ticket", summary=f"发现 {count} 张时间相符的行程票据",
            score=0.75,
            source_refs=[str(row.id) for row in trains + flights],
            payload={"train": len(trains), "flight": len(flights)}, algorithm_version=ALGORITHM_VERSION,
        ))


def discover(
    db: Session,
    owner_id: UUID,
    *,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    min_photos: int = 5,
    max_candidates: int = 50,
) -> list[Memory]:
    _retire_legacy_candidates(db, owner_id)
    query = (
        db.query(Photo, PhotoMetadata)
        .join(PhotoMetadata, PhotoMetadata.photo_id == Photo.id)
        .filter(
            Photo.owner_id == owner_id,
            Photo.is_deleted.is_(False),
            Photo.photo_time.isnot(None),
            PhotoMetadata.city.isnot(None),
            PhotoMetadata.city != "",
            or_(Photo.image_type.is_(None), Photo.image_type != ImageType.SCREENSHOT),
        )
    )
    if start_time:
        query = query.filter(Photo.photo_time >= start_time)
    if end_time:
        query = query.filter(Photo.photo_time <= end_time)
    rows = query.order_by(Photo.photo_time.asc()).all()
    if not rows:
        return []

    segments: list[list[tuple[Photo, PhotoMetadata | None]]] = []
    current: list[tuple[Photo, PhotoMetadata | None]] = []
    for row in rows:
        photo, metadata = row
        if current:
            previous_photo, previous_metadata = current[-1]
            gap = photo.photo_time - previous_photo.photo_time
            same_city = metadata.city == previous_metadata.city
            segment_span = photo.photo_time - current[0][0].photo_time
            should_split = not same_city or gap > timedelta(hours=18) or segment_span > timedelta(days=7)
            if should_split:
                segments.append(current)
                current = []
        current.append(row)
    if current:
        segments.append(current)

    created: list[Memory] = []
    for segment in segments:
        if len(segment) < min_photos or len(created) >= max_candidates:
            continue
        photo_ids = [photo.id for photo, _ in segment]
        fingerprint = _fingerprint(photo_ids)
        if db.query(Memory.id).filter(Memory.owner_id == owner_id, Memory.candidate_fingerprint == fingerprint).first():
            continue
        cities = Counter(metadata.city for _, metadata in segment if metadata and metadata.city)
        city = cities.most_common(1)[0][0] if cities else None
        start = segment[0][0].photo_time
        end = segment[-1][0].photo_time
        date_label = start.strftime("%Y 年 %m 月 %d 日")
        if start.date() != end.date():
            date_label = f"{start.strftime('%Y 年 %m 月 %d 日')}至{end.strftime('%m 月 %d 日')}"
        title = f"{date_label} · {city}" if city else f"{date_label}的记忆"
        place_ratio = (cities[city] / len(segment)) if city else 0
        confidence = min(0.92, 0.62 + min(len(segment), 30) / 300 + place_ratio * 0.2)
        memory = Memory(
            owner_id=owner_id, status=MemoryStatus.CANDIDATE, origin=MemoryOrigin.AUTO,
            title=title, title_source="system", start_time=start, end_time=end,
            confidence=confidence, algorithm_version=ALGORITHM_VERSION,
            candidate_fingerprint=fingerprint, cover_photo_id=_choose_cover(db, photo_ids),
        )
        for index, (photo, _) in enumerate(segment):
            memory.photo_links.append(MemoryPhoto(photo=photo, source="inferred", confidence=confidence, sort_order=index))
        memory.evidence.append(MemoryEvidence(
            evidence_type="time",
            summary=f"{len(segment)} 张照片在 {date_label} 连续拍摄",
            score=0.8, source_refs=[str(photo_id) for photo_id in photo_ids[:20]],
            payload={"photo_count": len(segment)}, algorithm_version=ALGORITHM_VERSION,
        ))
        if city:
            memory.places.append(MemoryPlace(
                name=city, level="city", source="inferred", confidence=place_ratio,
            ))
            memory.evidence.append(MemoryEvidence(
                evidence_type="place", summary=f"{cities[city]} 张照片位于{city}",
                score=place_ratio, source_refs=[str(photo.id) for photo, metadata in segment if metadata and metadata.city == city][:20],
                payload={"city": city, "count": cities[city]}, algorithm_version=ALGORITHM_VERSION,
            ))
        _enrich_people(db, memory, owner_id, photo_ids)
        _attach_tickets(db, memory, owner_id)
        db.add(memory)
        created.append(memory)
    db.commit()
    return [get_detail(db, memory.id, owner_id) for memory in created]


async def generate_story(db: Session, memory: Memory, owner_id: UUID, *, tone: str) -> Memory:
    """Generate a grounded story for a confirmed memory using the configured chat model."""
    memory = _require_owned(db, memory.id, owner_id, for_update=True)
    if memory.status != MemoryStatus.CONFIRMED:
        raise HTTPException(status_code=400, detail="只有已确认的记忆可以生成故事")
    now = datetime.now()
    if memory.story_generation_status == "generating" and memory.story_generation_started_at:
        if now - memory.story_generation_started_at < timedelta(minutes=5):
            raise HTTPException(status_code=409, detail="记忆故事正在生成，请稍候")
    from langchain_core.messages import HumanMessage, SystemMessage
    from app.core.config_manager import config_manager
    from app.service.agent.service import FixedChatOpenAI

    settings = config_manager.get_user_config(owner_id, db).ai
    connection_id = settings.chat_connection_id or settings.analysis_connection_id
    model_name = settings.chat_model_name or settings.analysis_model_name
    if not connection_id or not model_name:
        raise HTTPException(status_code=400, detail="请先在系统设置中配置 AI 对话模型")
    connection = next((item for item in settings.connections if item.id == connection_id), None)
    if not connection or not connection.enable or not connection.api_key:
        raise HTTPException(status_code=400, detail="当前 AI 连接不可用，请检查系统设置")

    memory.story_generation_status = "generating"
    memory.story_generation_started_at = now
    memory.story_generation_error = None
    db.commit()

    photo_ids = [link.photo_id for link in memory.photo_links]
    descriptions = db.query(ImageDescription).filter(ImageDescription.photo_id.in_(photo_ids)).all()
    description_lines = []
    for item in descriptions[:40]:
        text = item.narrative or item.description
        if text:
            description_lines.append(f"- {text.strip()}")
    facts = {
        "标题": memory.title,
        "时间": f"{memory.start_time or '未知'} 至 {memory.end_time or '未知'}",
        "地点": "、".join(place.name for place in memory.places) or "未知",
        "人物": "、".join(person.identity.identity_name or "未命名人物" for person in memory.people) or "未确认",
        "照片数量": len(photo_ids),
    }
    prompt = "\n".join(f"{key}：{value}" for key, value in facts.items())
    if description_lines:
        prompt += "\n照片中可核实的画面：\n" + "\n".join(description_lines)
    prompt += f"\n\n请以{tone}的语气写一段 150 至 300 字的中文记忆故事。"

    llm = FixedChatOpenAI(
        model=model_name,
        api_key=connection.api_key,
        base_url=connection.api_base or None,
        temperature=0.7,
        timeout=60,
        max_completion_tokens=1000,
    )
    try:
        response = await llm.ainvoke([
            SystemMessage(content="你是私人相册故事编辑。只能使用提供的事实，不得虚构人物关系、活动、感受或地点。直接输出故事正文，不要标题和解释。"),
            HumanMessage(content=prompt),
        ])
        story = response.content if isinstance(response.content, str) else str(response.content)
        story = _normalize_ai_story(story)
        if not story:
            raise HTTPException(status_code=502, detail="AI 未返回故事内容")
        memory.story = story
        memory.story_source = "system"
        memory.story_generation_status = "idle"
        memory.story_generation_started_at = None
        memory.story_generation_error = None
        memory.version += 1
        db.commit()
        return get_detail(db, memory.id, owner_id)
    except BaseException as exc:
        db.rollback()
        failed = _require_owned(db, memory.id, owner_id, for_update=True)
        failed.story_generation_status = "failed"
        failed.story_generation_started_at = None
        failed.story_generation_error = str(getattr(exc, "detail", exc))[:1000]
        db.commit()
        raise


def merge(db: Session, owner_id: UUID, memory_ids: list[UUID], *, title: str | None, story: str | None, cover_photo_id: UUID | None) -> Memory:
    unique_ids = list(dict.fromkeys(memory_ids))
    if len(unique_ids) < 2:
        raise HTTPException(status_code=400, detail="至少选择两段记忆")
    sources = db.query(Memory).filter(
        Memory.id.in_(unique_ids), Memory.owner_id == owner_id, Memory.status.in_(ACTIVE_STATUSES)
    ).with_for_update().all()
    if len(sources) != len(unique_ids):
        raise HTTPException(status_code=400, detail="部分记忆不存在或不可合并")
    photo_ids = list(dict.fromkeys(link.photo_id for source in sources for link in source.photo_links))
    photos = _owned_photos(db, owner_id, photo_ids)
    if cover_photo_id and cover_photo_id not in set(photo_ids):
        raise HTTPException(status_code=400, detail="封面必须属于合并后的照片")
    confirmed = any(source.status == MemoryStatus.CONFIRMED for source in sources)
    merged = Memory(
        owner_id=owner_id, status=MemoryStatus.CONFIRMED if confirmed else MemoryStatus.CANDIDATE,
        origin=MemoryOrigin.MANUAL,
        title=(title or next((source.title for source in sources if source.title_source == "user"), sources[0].title)).strip(),
        title_source="user" if title else "system", story=story,
        story_source="user" if story else "system",
        cover_photo_id=cover_photo_id or next((source.cover_photo_id for source in sources if source.cover_source == "user"), sources[0].cover_photo_id),
        cover_source="user" if cover_photo_id else "system",
        start_time=min((source.start_time for source in sources if source.start_time), default=None),
        end_time=max((source.end_time for source in sources if source.end_time), default=None),
        time_source="confirmed", confidence=1.0 if confirmed else 0.75,
        confirmed_at=datetime.now() if confirmed else None,
    )
    _set_photos(merged, photos, source="user_added", confirmed=confirmed)
    place_names = list(dict.fromkeys(place.name for source in sources for place in source.places))
    _set_places(merged, place_names, confirmed=confirmed)
    db.add(merged)
    db.flush()
    for source in sources:
        source.status = MemoryStatus.SUPERSEDED
        source.version += 1
        db.add(MemoryRelation(memory_id=merged.id, related_memory_id=source.id, relation_type="merged_from"))
    db.commit()
    return get_detail(db, merged.id, owner_id)


def split(db: Session, owner_id: UUID, memory_id: UUID, payload: MemorySplitRequest) -> list[Memory]:
    source = _require_owned(db, memory_id, owner_id, for_update=True)
    if source.status not in ACTIVE_STATUSES:
        raise HTTPException(status_code=400, detail="当前状态不能拆分")
    source_ids = {link.photo_id for link in source.photo_links}
    requested_ids = {photo_id for part in payload.parts for photo_id in part.photo_ids}
    if requested_ids != source_ids:
        raise HTTPException(status_code=400, detail="拆分必须完整分配原记忆中的全部照片")
    created: list[Memory] = []
    for part in payload.parts:
        photos = _owned_photos(db, owner_id, part.photo_ids)
        times = [photo.photo_time for photo in photos if photo.photo_time]
        item = Memory(
            owner_id=owner_id, status=source.status, origin=MemoryOrigin.MANUAL,
            title=part.title.strip(), title_source="user",
            cover_photo_id=photos[0].id, cover_source="system",
            start_time=min(times) if times else None, end_time=max(times) if times else None,
            time_source="confirmed", confidence=source.confidence,
            confirmed_at=datetime.now() if source.status == MemoryStatus.CONFIRMED else None,
        )
        _set_photos(item, photos, source="user_added", confirmed=source.status == MemoryStatus.CONFIRMED)
        db.add(item)
        db.flush()
        db.add(MemoryRelation(memory_id=item.id, related_memory_id=source.id, relation_type="split_from"))
        created.append(item)
    source.status = MemoryStatus.SUPERSEDED
    source.version += 1
    db.commit()
    return [get_detail(db, item.id, owner_id) for item in created]
