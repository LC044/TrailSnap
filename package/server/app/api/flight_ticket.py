#!/usr/bin/env python
# -*- coding: utf-8 -*-

from fastapi import APIRouter, Depends, HTTPException, Path, Query, UploadFile, File
from sqlalchemy.orm import Session
from typing import Optional, Dict, Any
from decimal import Decimal
import aiohttp
from aiohttp import FormData
import logging

from app.crud.flight_ticket import (
    create_flight_ticket,
    get_flight_ticket,
    update_flight_ticket,
    delete_flight_ticket,
    get_flight_tickets
)
from app.schemas.flight_ticket import (
    FlightTicketCreate, 
    FlightTicketResponse, 
    FlightTicketListResponse, 
    FlightTicketUpdate
)
from app.dependencies import get_db, BaseResponse
from app.api.deps import get_current_user
from app.db.models import User
from app.core.config_manager import config_manager

from app.service.ticket_wallet import owned_ticket, validate_photo

router = APIRouter()

@router.post("/recognize", summary="识别飞机票图片")
async def recognize_ticket(
    file: UploadFile = File(..., description="飞机票图片"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    上传飞机票图片并调用AI服务进行识别
    返回识别到的结构化数据
    """
    logging.info(f"Starting flight ticket recognition for file: {file.filename}")
    try:
        # 1. 读取文件内容
        file_content = await file.read()
        
        # 2. 构造请求发送给AI服务
        import base64
        b64_data = base64.b64encode(file_content).decode('utf-8')
        json_data = {"images": [b64_data]}
        
        async with aiohttp.ClientSession() as session:
            api_url = f"{config_manager.get_user_config(user.id, db).ai.ai_api_url}/tickets/predict"
            
            async with session.post(api_url, json=json_data) as response:
                if response.status != 200:
                    raise HTTPException(status_code=500, detail=f"AI服务请求失败: {response.status}")
                
                result_data = await response.json()
                
                ai_results = result_data.get('results', [])
                if not ai_results:
                    raise HTTPException(status_code=400, detail="未能识别出票据信息")
                    
                tickets = ai_results[0].get('tickets', [])
                if not tickets:
                    raise HTTPException(status_code=400, detail="未能识别出票据信息")
                
                # 过滤出飞机票
                flight_tickets = [t for t in tickets if t.get('type') == 'flight']
                
                if not flight_tickets:
                    # 如果没有识别出飞机票，尝试返回任意票据但提示可能类型不符，或者直接报错
                    # 这里为了用户体验，如果识别到了但类型不对，也可以返回，但前端需要处理
                    # 暂时严格过滤
                    if tickets:
                         # 如果识别到了火车票，可能用户传错了，或者模型误判
                         logging.warning("Recognized tickets but none marked as flight.")
                         # 尝试取第一个，前端可能需要兼容
                         ticket_info = tickets[0]
                    else:
                         raise HTTPException(status_code=400, detail="未能识别出飞机票信息")
                else:
                    # 在多检测结果中选择“最完整/最可信”的一张
                    def score(info: Dict[str, Any]) -> int:
                        s = 0
                        if info.get('flight_code'): s += 4
                        if info.get('departure_city'): s += 3
                        if info.get('arrival_city'): s += 3
                        if info.get('datetime'): s += 2
                        if info.get('price'): s += 1
                        return s
                    
                    ticket_info = max(flight_tickets, key=score)

                return BaseResponse(code=200, msg="识别成功", data=ticket_info)

    except Exception as e:
        logging.error(f"Flight ticket recognition failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("", response_model=BaseResponse[FlightTicketResponse], summary="创建飞机票")
async def create_ticket(
    ticket: FlightTicketCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """手动创建一张新的飞机票"""
    validate_photo(db, current_user.id, getattr(ticket, "photo_id", None))
    data = create_flight_ticket(db, ticket, owner_id=current_user.id)
    return BaseResponse(code=200, msg="创建成功", data=data)

@router.get("", response_model=BaseResponse[FlightTicketListResponse], summary="获取飞机票列表")
async def get_tickets(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    flight_code: Optional[str] = Query(None, description="按航班号筛选"),
    name: Optional[str] = Query(None, description="按乘车人筛选"),
    start_date: Optional[str] = Query(None, description="发车时间起始（格式：YYYY-MM-DD）"),
    end_date: Optional[str] = Query(None, description="发车时间结束（格式：YYYY-MM-DD）"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """分页获取飞机票列表"""
    filters = {
        "owner_id": current_user.id
    }
    if flight_code: filters['flight_code'] = flight_code
    if name: filters['name'] = name
    if start_date: filters['start_date'] = start_date
    if end_date: filters['end_date'] = end_date
    
    total, items = get_flight_tickets(db, skip, limit, filters)
    return BaseResponse(code=200, msg="获取成功", data={"total": total, "items": items})

@router.get("/{ticket_id}", response_model=BaseResponse[FlightTicketResponse], summary="获取飞机票详情")
async def get_ticket(
    ticket_id: str = Path(..., description="飞机票ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    owned_ticket(db, current_user.id, "flight", ticket_id)
    """根据ID获取飞机票详情"""
    ticket = get_flight_ticket(db, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="飞机票不存在")
    return BaseResponse(code=200, msg="获取成功", data=ticket)

@router.put("/{ticket_id}", response_model=BaseResponse[FlightTicketResponse], summary="更新飞机票")
async def update_ticket(
    ticket_update: FlightTicketUpdate,
    ticket_id: str = Path(..., description="飞机票ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    validate_photo(db, current_user.id, ticket_update.photo_id)
    owned_ticket(db, current_user.id, "flight", ticket_id)
    """更新飞机票信息"""
    ticket = update_flight_ticket(db, ticket_id, ticket_update)
    if not ticket:
        raise HTTPException(status_code=404, detail="飞机票不存在")
    return BaseResponse(code=200, msg="更新成功", data=ticket)

@router.delete("/{ticket_id}", summary="删除飞机票")
async def delete_ticket(
    ticket_id: str = Path(..., description="飞机票ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    owned_ticket(db, current_user.id, "flight", ticket_id)
    """删除飞机票"""
    success = delete_flight_ticket(db, ticket_id)
    if not success:
        raise HTTPException(status_code=404, detail="飞机票不存在")
    return BaseResponse(code=200, msg="删除成功", data={"msg": "删除成功"})
