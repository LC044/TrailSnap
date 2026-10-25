"""Associate train tickets with photos at both endpoints, using railway cities.

All writes belong to the caller's transaction. Only untouched system candidates
are refreshed; a user's decision freezes the candidate, including its fingerprint.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta

from sqlalchemy import or_
from sqlalchemy.orm import Session, selectinload

from app.db.models.memory import (Memory, MemoryEvidence, MemoryOrigin, MemoryPhoto,
                                  MemoryPlace, MemoryStatus, MemoryTicket)
from app.db.models.photo import ImageType, Photo
from app.db.models.photo_metadata import PhotoMetadata
from app.db.models.ticket_wallet import TicketDismissal
from app.db.models.trip import TrainTicket
from app.db.models.user import User

ALGORITHM_VERSION = "journey-v1-railway"
BEFORE_HOURS = 24
AFTER_HOURS = 48


def _city(value):
    return (value or "").strip().removesuffix("市")


def _station(value):
    return (value or "").strip().removesuffix("站")


def _fingerprint(ticket_id):
    return hashlib.sha256(f"journey:train:{ticket_id}".encode()).hexdigest()


def load_stations(names):
    # Deliberately lazy: unavailable railway configuration must not prevent
    # saving a ticket, importing a photo, or starting the main application.
    from railway.db.models.models import Station
    from railway.db.session import SessionLocal

    alias_names = getattr(Station, "alias_names", None)
    selected = [Station.station_name, Station.province, Station.city]
    if alias_names is not None:
        selected.append(alias_names)
        query_filter = or_(Station.station_name.in_(names), alias_names.isnot(None))
    else:
        query_filter = Station.station_name.in_(names)
    with SessionLocal() as railway:
        rows = railway.query(*selected).filter(query_filter).all()
    found = {}
    for row in rows:
        if not row.city or not row.province:
            continue
        # Newer railway schemas may include historical station aliases.
        names_for_row = [row.station_name]
        if alias_names is not None and len(row) > 3:
            names_for_row.extend(row[3] or [])
        for name in names_for_row:
            found.setdefault(_station(name), set()).add((row.province.strip(), _city(row.city)))
    # Duplicate names with conflicting geography are not safe to infer.
    return {name: next(iter(places)) for name, places in found.items() if len(places) == 1}


def _photos(db, owner_id, place, start, end, source_photo_ids):
    province, city = place
    # SQL limits the time and city before Python checks province. Require
    # province as well so identically named cities are never mixed.
    return db.query(Photo, PhotoMetadata).join(PhotoMetadata).filter(
        Photo.owner_id == owner_id, Photo.is_deleted.is_(False),
        Photo.photo_time >= start, Photo.photo_time <= end,
        PhotoMetadata.city.in_([city, city + "市"]),
        PhotoMetadata.province == province,
        or_(Photo.image_type.is_(None), Photo.image_type != ImageType.SCREENSHOT),
        Photo.id.notin_(source_photo_ids),
    ).order_by(Photo.photo_time, Photo.id).all()


def _editable(memory):
    return (memory.origin == MemoryOrigin.AUTO and memory.algorithm_version == ALGORITHM_VERSION
            and memory.status in (MemoryStatus.CANDIDATE, MemoryStatus.SUPERSEDED)
            and memory.version == 1 and memory.title_source == "system"
            and memory.cover_source == "system" and memory.story_source == "system"
            and all(not link.is_confirmed and link.source == "inferred" for link in memory.photo_links)
            and all(not link.is_confirmed and link.source == "inferred" for link in memory.tickets))


def discover(db: Session, owner_id, *, before_hours=BEFORE_HOURS, after_hours=AFTER_HOURS,
             start_time=None, end_time=None, max_candidates=200, _stations=None):
    """Return newly created candidates; refresh existing automatic candidates in place."""
    if not 1 <= before_hours <= 168 or not 1 <= after_hours <= 168:
        raise ValueError("行程照片时间窗口须在 1 至 168 小时内")
    db.query(User.id).filter(User.id == owner_id).with_for_update().first()
    query = db.query(TrainTicket).filter(TrainTicket.owner_id == owner_id)
    if start_time:
        query = query.filter(TrainTicket.date_time >= start_time - timedelta(hours=after_hours))
    if end_time:
        query = query.filter(TrainTicket.date_time <= end_time + timedelta(hours=before_hours))
    tickets = query.order_by(TrainTicket.date_time, TrainTicket.id).all()
    if start_time is None and end_time is None:
        # Ticket deletion removes polymorphic links. Retire only untouched
        # system candidates, keeping user-owned memories and their photos.
        live = {_fingerprint(t.id) for t in tickets}
        for orphan in db.query(Memory).filter(
            Memory.owner_id == owner_id, Memory.algorithm_version == ALGORITHM_VERSION,
            Memory.status == MemoryStatus.CANDIDATE,
        ).all():
            if orphan.candidate_fingerprint not in live and _editable(orphan):
                orphan.status = MemoryStatus.SUPERSEDED
    if not tickets:
        return []
    stations = _stations if _stations is not None else load_stations(
        {_station(value) for t in tickets for value in (t.departure_station, t.arrival_station)})
    source_photo_ids = [value for (value,) in db.query(TrainTicket.photo_id).filter(
        TrainTicket.owner_id == owner_id, TrainTicket.photo_id.isnot(None))]
    time_sources = {photo_id: (tasks or {}).get("ticket_time_sources", {}) for photo_id, tasks in
                    db.query(Photo.id, Photo.processed_tasks).filter(
                        Photo.owner_id == owner_id, Photo.id.in_(source_photo_ids))}
    existing = {m.candidate_fingerprint: m for m in db.query(Memory).options(
        selectinload(Memory.photo_links), selectinload(Memory.tickets),
        selectinload(Memory.places), selectinload(Memory.evidence),
    ).filter(Memory.owner_id == owner_id, Memory.candidate_fingerprint.in_(
        [_fingerprint(t.id) for t in tickets])).all()}
    created = []
    for ticket in tickets:
        fingerprint = _fingerprint(ticket.id)
        memory = existing.get(fingerprint)
        if memory and not _editable(memory):
            continue
        if memory and db.query(TicketDismissal.id).filter(
            TicketDismissal.memory_id == memory.id, TicketDismissal.ticket_type == "train",
            TicketDismissal.ticket_id == ticket.id,
        ).first():
            continue
        departure = stations.get(_station(ticket.departure_station))
        arrival = stations.get(_station(ticket.arrival_station))
        dt = ticket.date_time
        incomplete = time_sources.get(ticket.photo_id, {}).get(f"train:{ticket.id}")
        if incomplete or not isinstance(dt, datetime) or dt.year <= 1900 or not departure or not arrival:
            if memory:
                memory.status = MemoryStatus.SUPERSEDED
            continue
        duration = ticket.total_running_time or 0
        arrival_time = dt + timedelta(minutes=max(0, duration))
        sides = [
            ("departure", departure, dt - timedelta(hours=before_hours), dt),
            ("arrival", arrival, arrival_time, arrival_time + timedelta(hours=after_hours)),
        ]
        matches = [(side, place, start, end, _photos(db, owner_id, place, start, end, source_photo_ids))
                   for side, place, start, end in sides]
        photos = {photo.id: photo for _, _, _, _, rows in matches for photo, _ in rows}
        if not photos:
            if memory:
                memory.status = MemoryStatus.SUPERSEDED
            continue
        if memory is None:
            if len(created) >= max_candidates:
                continue
            memory = Memory(owner_id=owner_id, status=MemoryStatus.CANDIDATE, origin=MemoryOrigin.AUTO,
                            algorithm_version=ALGORITHM_VERSION, candidate_fingerprint=fingerprint,
                            title="", version=1, title_source="system", story_source="system",
                            cover_source="system")
            db.add(memory)
            created.append(memory)
        ordered = sorted(photos.values(), key=lambda p: (p.photo_time, str(p.id)))
        # Delete old unique links before replacing them (SQLAlchemy otherwise
        # inserts replacements before deleting the previous association rows).
        memory.photo_links.clear()
        memory.tickets.clear()
        memory.places.clear()
        memory.evidence.clear()
        db.flush()
        memory.status = MemoryStatus.CANDIDATE
        memory.title = f"{dt:%Y年%m月%d日} · {departure[1]} → {arrival[1]}"
        memory.start_time = min(dt, ordered[0].photo_time)
        memory.end_time = max(arrival_time, ordered[-1].photo_time)
        memory.time_source = "inferred"
        memory.confidence = 0.85 if all(rows for *_, rows in matches) else 0.7
        memory.cover_photo_id = ordered[0].id
        memory.updated_at = datetime.now()
        memory.photo_links = [MemoryPhoto(photo=p, source="inferred", confidence=memory.confidence,
                                         sort_order=i) for i, p in enumerate(ordered)]
        memory.tickets = [MemoryTicket(ticket_type="train", ticket_id=ticket.id, source="inferred",
                                      confidence=memory.confidence)]
        memory.places = [MemoryPlace(name=place[1], level="city", source="inferred", confidence=1.0)
                         for place in dict.fromkeys([departure, arrival])]
        memory.evidence = [MemoryEvidence(
            evidence_type="ticket", summary=f"{ticket.train_code}：{ticket.departure_station} → {ticket.arrival_station}",
            score=memory.confidence, source_refs=[ticket.id], algorithm_version=ALGORITHM_VERSION,
            payload={"ticket_id": ticket.id, "departure_time": dt.isoformat(),
                     "arrival_time": arrival_time.isoformat() if duration > 0 else None,
                     "after_anchor": "estimated_arrival" if duration > 0 else "departure"},
        )]
        for side, place, start, end, rows in matches:
            if rows:
                memory.evidence.append(MemoryEvidence(
                    evidence_type="place", summary=f"{'乘车前出发地' if side == 'departure' else '乘车后到达地'}：{place[1]}，{len(rows)} 张照片",
                    score=memory.confidence, source_refs=[str(p.id) for p, _ in rows[:20]],
                    algorithm_version=ALGORITHM_VERSION,
                    payload={"side": side, "province": place[0], "city": place[1],
                             "start": start.isoformat(), "end": end.isoformat(), "photo_count": len(rows)},
                ))
    db.flush()
    return created
