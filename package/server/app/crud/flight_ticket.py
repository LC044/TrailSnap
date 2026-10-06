#!/usr/bin/env python
# -*- coding: utf-8 -*-
import logging

from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from decimal import Decimal
from datetime import datetime
import uuid

from app.db.models.trip import FlightTicket
from app.schemas.flight_ticket import FlightTicketCreate, FlightTicketUpdate

def get_flight_ticket(db: Session, ticket_id: str) -> Optional[FlightTicket]:
    """根据ID获取单张飞机票"""
    return db.query(FlightTicket).filter(FlightTicket.id == ticket_id).first()

def get_flight_tickets(
        db: Session,
        skip: int = 0,
        limit: int = 100,
        filters: Optional[Dict[str, Any]] = None
) -> (int, List[FlightTicket]):
    """获取飞机票列表（支持过滤、分页）"""
    query = db.query(FlightTicket)

    if filters:
        for key, value in filters.items():
            if hasattr(FlightTicket, key) and value is not None:
                if isinstance(value, str):
                    query = query.filter(getattr(FlightTicket, key).ilike(f"%{value}%"))
                elif isinstance(value, (int, Decimal, datetime, uuid.UUID)):
                    query = query.filter(getattr(FlightTicket, key) == value)
            elif key == 'start_date' and value:
                query = query.filter(FlightTicket.date_time >= value)
            elif key == 'end_date' and value:
                query = query.filter(FlightTicket.date_time <= f"{value} 23:59:59")

    total = query.count()
    items = query.order_by(FlightTicket.date_time.desc()).offset(skip).limit(limit).all()
    return total, items

def create_flight_ticket(db: Session, ticket: FlightTicketCreate, owner_id: uuid.UUID = None) -> FlightTicket:
    """创建新的飞机票"""
    # Check duplicate
    existing = db.query(FlightTicket).filter(
        FlightTicket.flight_code == ticket.flight_code,
        FlightTicket.date_time == ticket.date_time,
        FlightTicket.name == ticket.name
    ).first()
    if existing:
        logging.info(f"Duplicate flight ticket found: {ticket.flight_code} {ticket.date_time} {ticket.name}")
        return None
    db_ticket = FlightTicket(
        flight_code=ticket.flight_code,
        departure_city=ticket.departure_city,
        arrival_city=ticket.arrival_city,
        date_time=ticket.date_time,
        price=ticket.price,
        name=ticket.name,
        total_mileage=ticket.total_mileage or Decimal('0.0'),
        total_running_time=ticket.total_running_time or 0,
        comments=ticket.comments,
        photo_id=ticket.photo_id,
        owner_id=owner_id
    )
    db.add(db_ticket)
    db.commit()
    db.refresh(db_ticket)
    return db_ticket

def update_flight_ticket(
        db: Session,
        ticket_id: str,
        ticket_update: FlightTicketUpdate
) -> Optional[FlightTicket]:
    """更新飞机票信息"""
    db_ticket = get_flight_ticket(db, ticket_id)
    if not db_ticket:
        return None

    update_data = ticket_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_ticket, key, value)

    db.commit()
    db.refresh(db_ticket)
    return db_ticket

def delete_flight_ticket(db: Session, ticket_id: str) -> bool:
    """删除飞机票"""
    db_ticket = get_flight_ticket(db, ticket_id)
    if not db_ticket:
        return False

    from app.db.models.ticket_wallet import AlbumTicket, TicketDismissal
    from app.db.models.memory import MemoryTicket
    for link_model in (AlbumTicket, MemoryTicket, TicketDismissal):
        db.query(link_model).filter(link_model.ticket_type == "flight", link_model.ticket_id == ticket_id).delete(synchronize_session=False)
    db.delete(db_ticket)
    db.commit()
    return True

def delete_flight_ticket_by_photo_id(db: Session, ticket_id: str) -> bool:
    """删除飞机票"""
    # 删除photo对应的飞机票
    db.query(FlightTicket).filter(FlightTicket.photo_id == str(ticket_id)).delete()
    db.commit()
    return True