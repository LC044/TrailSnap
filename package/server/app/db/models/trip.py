#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
@Time        : 2025/5/9 23:44 
@Author      : SiYuan 
@Email       : sixyuan044@gmail.com 
@File        : TrailSnap-trip.py 
@Description : 
"""

from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Text, Enum, Numeric, DECIMAL
from sqlalchemy.orm import relationship
from app.db.types import UUID
from datetime import datetime
import uuid

from app.db.base import Base

TicketType = Enum('train', 'flight', 'bus', name='ticket_type')  # 票据类型：火车票、飞机票、汽车票

class TrainTicket(Base):
    """火车票模型"""
    __tablename__ = "train_tickets"

    # 修改为UUID类型主键
    id = Column(
        String(36),
        primary_key=True,
        index=True,
        default=lambda: str(uuid.uuid4()),  # 自动生成UUID
        comment="票据ID（UUID）"
    )
    train_code = Column(String(20), index=True, nullable=False, comment="车次号（如G1920）")
    departure_station = Column(String(50), nullable=False, comment="出发站")
    arrival_station = Column(String(50), nullable=False, comment="到达站")
    date_time = Column(DateTime, nullable=False, comment="发车时间")
    carriage = Column(String(10), nullable=False, comment="车厢号（如8A、12）")
    seat_num = Column(String(10), nullable=False, comment="座位号（如12F、05下）")
    berth_type = Column(String(10), default="无", comment="铺位类型（上/中/下/无）")
    price = Column(Numeric(10, 2), nullable=False, comment="票价（保留两位小数）")
    seat_type = Column(String(20), nullable=False, comment="座位类型（一等座/二等座/商务座等）")
    name = Column(String(50), nullable=False, comment="乘车人姓名")
    discount_type = Column(String(20), default="全价票", comment="优惠类型（学生票/儿童票/优惠票/全价票等）")
    total_mileage = Column(DECIMAL(10, 1), nullable=False, default=0, comment="线路里程（公里）")
    total_running_time = Column(Integer, nullable=False, default=0, comment="累计运行时间（分钟）")
    stop_stations = Column(Text, nullable=True, default="[]", comment="经停站列表，JSON格式存储")
    comments = Column(Text, nullable=True, comment="备注信息")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")
    
    # 新增字段：关联照片ID
    # photo_id = Column(String(36), nullable=True, comment="关联照片ID", index=True)
    photo_id = Column(UUID(as_uuid=True), ForeignKey("photos.id", ondelete="SET NULL"), nullable=True, comment="关联照片ID", index=True)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=True)

class FlightTicket(Base):
    """飞机票模型"""
    __tablename__ = "flight_tickets"

    # 修改为UUID类型主键
    id = Column(
        String(36),
        primary_key=True,
        index=True,
        default=lambda: str(uuid.uuid4()),  # 自动生成UUID
        comment="票据ID（UUID）"
    )
    flight_code = Column(String(20), index=True, nullable=False, comment="航班号")
    departure_city = Column(String(50), nullable=False, comment="出发地")
    arrival_city = Column(String(50), nullable=False, comment="目的地")
    date_time = Column(DateTime, nullable=False, comment="出发日期时间")
    price = Column(Numeric(10, 2), nullable=False, comment="票价")
    name = Column(String(50), nullable=False, comment="乘车人姓名")
    
    total_mileage = Column(DECIMAL(10, 1), nullable=False, default=0, comment="里程")
    total_running_time = Column(Integer, nullable=False, default=0, comment="飞行时长（分钟）")
    comments = Column(Text, nullable=True, comment="备注信息")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")
    
    # 新增字段：关联照片ID
    # photo_id = Column(String(36), nullable=True, comment="关联照片ID", index=True)
    photo_id = Column(UUID(as_uuid=True), ForeignKey("photos.id", ondelete="SET NULL"), nullable=True,
                      comment="关联照片ID", index=True)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=True)
