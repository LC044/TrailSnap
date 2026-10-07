#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
@Time        : 2025/11/23 23:13
@Author      : SiYuan
@Email       : sixyuan044@gmail.com
@File        : server-train_ticket.py
@Description : 
"""
from uuid import UUID

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List
from decimal import Decimal

class TrainTicketBase(BaseModel):
    """火车票基础模型（用于请求和响应）"""
    train_code: str = Field(..., description="车次号（如G1920）")
    departure_station: str = Field(..., description="出发站")
    arrival_station: str = Field(..., description="到达站")
    date_time: datetime = Field(..., description="发车时间（格式：YYYY-MM-DD HH:MM:SS）")
    carriage: str = Field(..., description="车厢号（如8A、12）")
    seat_num: str = Field(..., description="座位号（如12F、05下）")
    berth_type: Optional[str] = Field("无", description="铺位类型（上/中/下/无）")
    price: Decimal = Field(..., ge=0, description="票价（大于等于0）")
    seat_type: str = Field(..., description="座位类型（一等座/二等座/商务座等）")
    name: str = Field(..., description="乘车人姓名")
    discount_type: Optional[str] = Field("全价票", description="优惠类型（学生票/儿童票/优惠票/全价票等）")
    total_running_time: Optional[int] = Field(default=0, ge=0, description="总运行时间（分钟）")
    total_mileage: Optional[Decimal] = Field(default=0, ge=0, description="总里程（公里）")
    stop_stations: Optional[str] = Field(None, description="途经站点列表")
    comments: Optional[str] = Field(None, description="备注信息")
    photo_id: Optional[UUID] = Field(None, description="关联照片ID")

class TrainTicketCreate(TrainTicketBase):
    """创建火车票请求模型（继承基础模型，无额外字段）"""
    pass

class TrainTicketUpdate(BaseModel):
    """更新火车票请求模型（所有字段可选）"""
    train_code: Optional[str] = Field(None, description="车次号（如G1920）")
    departure_station: Optional[str] = Field(None, description="出发站")
    arrival_station: Optional[str] = Field(None, description="到达站")
    date_time: Optional[datetime] = Field(None, description="发车时间（格式：YYYY-MM-DD HH:MM:SS）")
    carriage: Optional[str] = Field(None, description="车厢号（如8A、12）")
    seat_num: Optional[str] = Field(None, description="座位号（如12F、05下）")
    berth_type: Optional[str] = Field(None, description="铺位类型（上/中/下/无）")
    price: Optional[Decimal] = Field(None, ge=0, description="票价（大于等于0）")
    seat_type: Optional[str] = Field(None, description="座位类型（一等座/二等座/商务座等）")
    name: Optional[str] = Field(None, description="乘车人姓名")
    discount_type: Optional[str] = Field(None, description="优惠类型（学生票/儿童票/优惠票/全价票等）")
    total_running_time: Optional[int] = Field(None, description="总运行时间（分钟）")
    total_mileage: Optional[Decimal] = Field(None, ge=0, description="总里程（公里）")
    stop_stations: Optional[str] = Field(None, description="途经站点列表")
    comments: Optional[str] = Field(None, description="备注信息")
    photo_id: Optional[UUID] = Field(None, description="关联照片ID")

class TrainTicketResponse(TrainTicketBase):
    """火车票响应模型（包含数据库额外字段）"""
    id: str
    created_at: datetime

    # 配置ORM模式（允许直接从SQLAlchemy模型转换）
    class Config:
        from_attributes = True

class TrainTicketListResponse(BaseModel):
    """火车票列表响应模型"""
    total: int = Field(..., description="总记录数")
    items: List[TrainTicketResponse] = Field(..., description="火车票列表")
