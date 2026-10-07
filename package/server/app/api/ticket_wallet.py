"""Unified ticket wallet endpoints; legacy ticket CRUD remains compatible."""
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query, HTTPException, UploadFile, File
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.dependencies import BaseResponse, get_db
from app.api.deps import get_current_user
from app.db.models import User
from app.db.models.album import Album
from app.db.models.memory import Memory, MemoryStatus
from app.service import ticket_wallet as service

router = APIRouter()


@router.post("/import", response_model=BaseResponse[dict])
async def import_wallet(file: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    import csv
    import io
    import json
    contents = await file.read(10 * 1024 * 1024 + 1)
    if len(contents) > 10 * 1024 * 1024:
        raise HTTPException(413, "文件大小超过 10MB")
    try:
        if (file.filename or "").lower().endswith(".csv"):
            records = list(csv.DictReader(io.StringIO(contents.decode("utf-8-sig"))))
        elif (file.filename or "").lower().endswith(".json"):
            payload = json.loads(contents.decode("utf-8-sig"))
            if isinstance(payload, dict):
                if payload.get("version") != 1:
                    raise ValueError("不支持的文件版本")
                records = payload.get("items")
            else:
                records = payload
        else:
            raise ValueError("仅支持 JSON/CSV")
        if not isinstance(records, list) or len(records) > 10000:
            raise ValueError("文件须包含不超过 10000 张票据")
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(422, "文件格式无效，仅支持旧版票据数组或版本 1 的 JSON/CSV")
    return BaseResponse.success(service.import_records(db, user.id, records))


class TicketRef(BaseModel):
    type: Literal["train", "flight"]
    id: str = Field(min_length=1, max_length=36)


class LinkRequest(BaseModel):
    tickets: list[TicketRef] = Field(min_length=1, max_length=1000)
    context_kind: Literal["album", "memory"]
    context_id: str
    linked: bool = True


@router.get("", response_model=BaseResponse[dict])
def list_wallet(album_id: str | None = None, memory_id: str | None = None,
                start: datetime | None = None, end: datetime | None = None,
                skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=1000),
                db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    # Normalize ISO inputs to the naive UTC convention used by existing tickets.
    from datetime import timezone
    start = start.astimezone(timezone.utc).replace(tzinfo=None) if start and start.tzinfo else start
    end = end.astimezone(timezone.utc).replace(tzinfo=None) if end and end.tzinfo else end
    if start and end and start >= end:
        raise HTTPException(422, "结束时间须晚于开始时间")
    items = service.list_tickets(db, user.id, album_id=album_id, memory_id=memory_id, start=start, end=end)
    return BaseResponse.success({"items": items[skip:skip + limit], "total": len(items)})


@router.get("/contexts", response_model=BaseResponse[dict])
def contexts(kind: Literal["album", "memory"], q: str = Query("", max_length=100),
             skip: int = Query(0, ge=0), limit: int = Query(30, ge=1, le=100),
             db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    model = Album if kind == "album" else Memory
    title = Album.name if kind == "album" else Memory.title
    query = db.query(model).filter(model.owner_id == user.id)
    query = query.filter(Album.type.in_(["user", "custom"])) if kind == "album" else query.filter(Memory.status == MemoryStatus.CONFIRMED)
    if q:
        query = query.filter(title.contains(q, autoescape=True))
    total = query.count()
    rows = query.order_by(title, model.id).offset(skip).limit(limit).all()
    return BaseResponse.success({"items": [{"id": str(row.id), "title": row.name if kind == "album" else row.title, "kind": kind} for row in rows], "total": total})


@router.post("/links", response_model=BaseResponse[dict])
def link_tickets(payload: LinkRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    # Validate before mutating: a mixed request is all-or-nothing.
    service.owned_context(db, user.id, payload.context_kind, payload.context_id, editable=True)
    for ref in payload.tickets:
        service.owned_ticket(db, user.id, ref.type, ref.id)
    try:
        for kind, ticket_id in {(ref.type, ref.id) for ref in payload.tickets}:
            service.set_link(db, user.id, kind, ticket_id, payload.context_kind, payload.context_id, payload.linked)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return BaseResponse.success({"updated": len({(ref.type, ref.id) for ref in payload.tickets})})


@router.get("/{kind}/{ticket_id}", response_model=BaseResponse[dict])
def detail(kind: Literal["train", "flight"], ticket_id: str,
           db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    service.owned_ticket(db, user.id, kind, ticket_id)
    item = next(item for item in service.list_tickets(db, user.id) if item["key"] == f"{kind}:{ticket_id}")
    item["photos"] = service.related_photos(db, user.id, kind, ticket_id)
    return BaseResponse.success(item)


@router.delete("/{kind}/{ticket_id}", response_model=BaseResponse[dict])
def remove(kind: Literal["train", "flight"], ticket_id: str,
           db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    service.delete_ticket(db, user.id, kind, ticket_id)
    db.commit()
    return BaseResponse.success({"deleted": True})
