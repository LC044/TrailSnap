#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
@Time        : 2025/11/23 23:14
@Author      : SiYuan
@Email       : sixyuan044@gmail.com
@File        : server-train_ticket.py
@Description : 
"""
import logging

from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from decimal import Decimal
from datetime import datetime
import uuid

from app.db.models.trip import TrainTicket
from app.schemas.train_ticket import TrainTicketCreate, TrainTicketUpdate


def get_train_ticket(db: Session, ticket_id: str) -> Optional[TrainTicket]:
    """根据ID获取单张火车票"""
    return db.query(TrainTicket).filter(TrainTicket.id == ticket_id).first()


def get_train_tickets(
        db: Session,
        skip: int = 0,
        limit: int = 100,
        filters: Optional[Dict[str, Any]] = None
) -> (int, List[TrainTicket]):
    """获取火车票列表（支持过滤、分页）"""
    query = db.query(TrainTicket)

    # 应用过滤条件（如按车次、乘车人、出发站等）
    if filters:
        for key, value in filters.items():
            if hasattr(TrainTicket, key) and value is not None:
                if isinstance(value, str):
                    # 字符串字段支持模糊查询
                    query = query.filter(getattr(TrainTicket, key).ilike(f"%{value}%"))
                elif isinstance(value, (int, Decimal, datetime, uuid.UUID)):
                    # 精确匹配
                    query = query.filter(getattr(TrainTicket, key) == value)

    # 计算总记录数
    total = query.count()

    # 分页查询
    items = query.offset(skip).limit(limit).order_by(TrainTicket.date_time.desc()).all()

    return total, items


def get_all_train_tickets(db: Session, owner_id: uuid.UUID = None) -> List[TrainTicket]:
    """获取所有火车票（用于导出）"""
    query = db.query(TrainTicket).order_by(TrainTicket.date_time.desc())
    if owner_id:
        query = query.filter(TrainTicket.owner_id == owner_id)
    return query.all()



def create_train_ticket(db: Session, ticket: TrainTicketCreate, owner_id: uuid.UUID = None) -> TrainTicket:
    """创建新的火车票"""
    # Check duplicate
    existing = db.query(TrainTicket).filter(
        TrainTicket.train_code == ticket.train_code,
        TrainTicket.date_time == ticket.date_time,
        TrainTicket.seat_num == (ticket.seat_num or '无座')
    ).first()
    if existing:
        logging.info(f"Duplicate train ticket found: {ticket.train_code} {ticket.date_time}")
        return None
    db_ticket = TrainTicket(
        train_code=ticket.train_code,
        departure_station=ticket.departure_station,
        arrival_station=ticket.arrival_station,
        date_time=ticket.date_time,
        carriage=ticket.carriage,
        seat_num=ticket.seat_num,
        berth_type=ticket.berth_type,
        price=ticket.price,
        seat_type=ticket.seat_type,
        name=ticket.name,
        discount_type=ticket.discount_type,
        total_running_time=ticket.total_running_time or 0,
        total_mileage=ticket.total_mileage or Decimal('0.0'),
        stop_stations=ticket.stop_stations or '[]',  # 默认空列表，后续可更新
        comments=ticket.comments,
        photo_id=ticket.photo_id,
        owner_id=owner_id
    )
    db.add(db_ticket)
    db.commit()
    db.refresh(db_ticket)  # 刷新获取数据库生成的字段（如id、created_at）
    return db_ticket


def update_train_ticket(
        db: Session,
        ticket_id: str,
        ticket_update: TrainTicketUpdate
) -> Optional[TrainTicket]:
    """更新火车票信息"""
    db_ticket = get_train_ticket(db, ticket_id)
    if not db_ticket:
        return None

    # 只更新提供的字段
    update_data = ticket_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_ticket, key, value)

    db.commit()
    db.refresh(db_ticket)
    return db_ticket


def delete_train_ticket(db: Session, ticket_id: str) -> bool:
    """删除火车票"""
    db_ticket = get_train_ticket(db, ticket_id)
    if not db_ticket:
        return False

    from app.db.models.ticket_wallet import AlbumTicket, TicketDismissal
    from app.db.models.memory import MemoryTicket
    for link_model in (AlbumTicket, MemoryTicket, TicketDismissal):
        db.query(link_model).filter(link_model.ticket_type == "train", link_model.ticket_id == ticket_id).delete(synchronize_session=False)
    db.delete(db_ticket)
    db.commit()
    return True

def delete_train_ticket_by_photo_id(db: Session, ticket_id: str) -> bool:
    """删除火车票"""
    # 删除photo对应的火车票
    db.query(TrainTicket).filter(TrainTicket.photo_id == str(ticket_id)).delete()
    db.commit()
    return True