"""Owned ticket browsing and atomic, bidirectional album/memory associations."""
from datetime import datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db.models.album import Album, AlbumPhoto
from app.db.models.memory import Memory, MemoryStatus, MemoryTicket, MemoryPhoto
from app.db.models.photo import Photo
from app.db.models.trip import TrainTicket, FlightTicket
from app.db.models.ticket_wallet import AlbumTicket, TicketDismissal

MODELS = {"train": TrainTicket, "flight": FlightTicket}


def validate_photo(db, owner_id, photo_id):
    if photo_id and not db.query(Photo).filter(Photo.id == photo_id, Photo.owner_id == owner_id, Photo.is_deleted.is_(False)).first():
        raise HTTPException(404, "原票图片不存在或无权访问")


def import_records(db, owner_id, records):
    """Legacy transport arrays and versioned wallet exports use one owned importer."""
    from app.schemas.train_ticket import TrainTicketCreate
    from app.schemas.flight_ticket import FlightTicketCreate
    success = updated = 0
    errors = []
    for index, source in enumerate(records):
        try:
            if not isinstance(source, dict):
                raise ValueError("票据必须是对象")
            kind = source.get("type") or "train"
            if kind not in MODELS:
                raise ValueError("不支持的票据类型")
            values = {key: value for key, value in source.items() if value is not None}
            # Empty optional CSV cells are absent; required string fields may be empty.
            for field in ("photo_id", "berth_type", "discount_type", "total_running_time", "total_mileage"):
                if values.get(field) == "":
                    values.pop(field)
            schema = TrainTicketCreate if kind == "train" else FlightTicketCreate
            data = schema.model_validate(values).model_dump()
            validate_photo(db, owner_id, data.get("photo_id"))
            ticket_id = source.get("id")
            if ticket_id:
                UUID(str(ticket_id))
            model = MODELS[kind]
            existing = db.query(model).filter(model.id == ticket_id).first() if ticket_id else None
            if existing and existing.owner_id != owner_id:
                raise ValueError("无法导入此票据 ID")
            was_updated = existing is not None
            if existing:
                for key, value in data.items():
                    setattr(existing, key, value)
            else:
                if ticket_id:
                    data["id"] = ticket_id
                db.add(model(**data, owner_id=owner_id))
            db.commit()
            success += 1
            updated += int(was_updated)
        except Exception:
            db.rollback()
            errors.append(f"第 {index + 1} 行无效、类型不支持或无权访问")
    return {"total": len(records), "success": success, "failed": len(errors), "details": {"updated": updated, "created": success - updated, "errors": errors}}


def owned_ticket(db, owner_id, kind, ticket_id):
    model = MODELS.get(kind)
    row = db.query(model).filter(model.id == ticket_id, model.owner_id == owner_id).first() if model else None
    if row is None:
        raise HTTPException(404, "票据不存在或无权访问")
    return row


def owned_context(db, owner_id, kind, context_id, *, editable=False):
    try:
        context_id = UUID(str(context_id))
    except ValueError:
        raise HTTPException(422, "关联对象 ID 无效")
    model = Album if kind == "album" else Memory
    row = db.query(model).filter(model.id == context_id, model.owner_id == owner_id).first()
    if row is None or (kind == "memory" and row.status != MemoryStatus.CONFIRMED):
        raise HTTPException(404, "关联对象不存在或不可用")
    if editable and kind == "album" and row.type not in {"user", "custom"}:
        raise HTTPException(403, "只能关联普通相册")
    return row


def summary(row, kind):
    train = kind == "train"
    return {
        "id": str(row.id), "type": kind, "key": f"{kind}:{row.id}",
        "title": f"{row.departure_station if train else row.departure_city} → {row.arrival_station if train else row.arrival_city}",
        "code": row.train_code if train else row.flight_code,
        "from": row.departure_station if train else row.departure_city,
        "to": row.arrival_station if train else row.arrival_city,
        "date_time": row.date_time.isoformat() if row.date_time else None,
        "price": float(row.price) if row.price is not None else None,
        "name": row.name, "photo_id": str(row.photo_id) if row.photo_id else None,
        "distance": float(row.total_mileage or 0), "duration": row.total_running_time or 0,
        "comments": row.comments or "", "seat_type": getattr(row, "seat_type", None),
        "carriage": getattr(row, "carriage", None), "seat_num": getattr(row, "seat_num", None),
        "berth_type": getattr(row, "berth_type", None), "discount_type": getattr(row, "discount_type", None),
        "stop_stations": getattr(row, "stop_stations", None),
        "albums": [], "memories": [], "candidates": [],
    }


def list_tickets(db: Session, owner_id, *, album_id=None, memory_id=None, start=None, end=None):
    """All owned summaries, with relationships fetched in batches, never per ticket."""
    context_refs = None
    if album_id:
        album = owned_context(db, owner_id, "album", album_id)
        context_refs = {(link.ticket_type, link.ticket_id) for link in db.query(AlbumTicket).filter(AlbumTicket.album_id == album.id)}
    if memory_id:
        memory = owned_context(db, owner_id, "memory", memory_id)
        refs = {(link.ticket_type, link.ticket_id) for link in db.query(MemoryTicket).filter(MemoryTicket.memory_id == memory.id)}
        context_refs = refs if context_refs is None else context_refs & refs
    items = {}
    for kind, model in MODELS.items():
        query = db.query(model).filter(model.owner_id == owner_id)
        if start:
            query = query.filter(model.date_time >= start)
        if end:
            query = query.filter(model.date_time < end)
        if context_refs is not None:
            ids = [ticket_id for ticket_kind, ticket_id in context_refs if ticket_kind == kind]
            query = query.filter(model.id.in_(ids))
        for row in query:
            items[(kind, row.id)] = summary(row, kind)
    album_links = db.query(AlbumTicket, Album).join(Album, Album.id == AlbumTicket.album_id).filter(Album.owner_id == owner_id).all()
    for link, album in album_links:
        item = items.get((link.ticket_type, link.ticket_id))
        if item:
            item["albums"].append({"id": str(album.id), "title": album.name, "kind": "album"})
    memory_links = db.query(MemoryTicket, Memory).join(Memory, Memory.id == MemoryTicket.memory_id).filter(
        Memory.owner_id == owner_id, Memory.status == MemoryStatus.CONFIRMED,
    ).all()
    for link, memory in memory_links:
        item = items.get((link.ticket_type, link.ticket_id))
        if item:
            target = "memories" if link.is_confirmed else "candidates"
            item[target].append({"id": str(memory.id), "title": memory.title, "kind": "memory", "reason": "时间相近" if not link.is_confirmed else None})
    return sorted(items.values(), key=lambda item: (item["date_time"] or "", item["key"]), reverse=True)


def set_link(db, owner_id, kind, ticket_id, context_kind, context_id, linked):
    owned_ticket(db, owner_id, kind, ticket_id)
    context = owned_context(db, owner_id, context_kind, context_id, editable=True)
    model = AlbumTicket if context_kind == "album" else MemoryTicket
    field = model.album_id if context_kind == "album" else model.memory_id
    existing = db.query(model).filter(field == context.id, model.ticket_type == kind, model.ticket_id == ticket_id).first()
    if linked:
        if existing is None:
            existing = model(ticket_type=kind, ticket_id=ticket_id, **{f"{context_kind}_id": context.id})
            db.add(existing)
        if context_kind == "memory":
            existing.is_confirmed = True
            existing.source = "user"
            db.query(TicketDismissal).filter(TicketDismissal.memory_id == context.id, TicketDismissal.ticket_type == kind, TicketDismissal.ticket_id == ticket_id).delete()
    else:
        if existing:
            db.delete(existing)
        if context_kind == "memory" and not db.query(TicketDismissal).filter(TicketDismissal.memory_id == context.id, TicketDismissal.ticket_type == kind, TicketDismissal.ticket_id == ticket_id).first():
            db.add(TicketDismissal(memory_id=context.id, ticket_type=kind, ticket_id=ticket_id))
    if context_kind == "memory":
        context.version += 1
        context.updated_at = datetime.now()
    db.flush()


def delete_ticket(db, owner_id, kind, ticket_id):
    row = owned_ticket(db, owner_id, kind, ticket_id)
    for model in (AlbumTicket, MemoryTicket, TicketDismissal):
        db.query(model).filter(model.ticket_type == kind, model.ticket_id == ticket_id).delete(synchronize_session=False)
    db.delete(row)
    db.flush()


def related_photos(db, owner_id, kind, ticket_id):
    owned_ticket(db, owner_id, kind, ticket_id)
    albums = db.query(AlbumTicket.album_id).join(Album, Album.id == AlbumTicket.album_id).filter(
        Album.owner_id == owner_id, AlbumTicket.ticket_type == kind, AlbumTicket.ticket_id == ticket_id,
    )
    memories = db.query(MemoryTicket.memory_id).join(Memory, Memory.id == MemoryTicket.memory_id).filter(
        Memory.owner_id == owner_id, Memory.status == MemoryStatus.CONFIRMED,
        MemoryTicket.is_confirmed.is_(True), MemoryTicket.ticket_type == kind, MemoryTicket.ticket_id == ticket_id,
    )
    album_photos = db.query(AlbumPhoto.photo_id).filter(AlbumPhoto.album_id.in_(albums))
    memory_photos = db.query(MemoryPhoto.photo_id).filter(MemoryPhoto.memory_id.in_(memories))
    photos = db.query(Photo).filter(Photo.owner_id == owner_id, Photo.is_deleted.is_(False), or_(Photo.id.in_(album_photos), Photo.id.in_(memory_photos))).order_by(Photo.photo_time.desc(), Photo.id).limit(12).all()
    return [{"id": str(photo.id), "filename": photo.filename} for photo in photos]
