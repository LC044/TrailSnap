#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
@Time        : 2025/11/18 20:56
@Author      : SiYuan
@Email       : sixyuan044@gmail.com
@File        : server-api.py
@Description : 
"""
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, Depends, HTTPException, Path, Body, Query, APIRouter
from sqlalchemy.orm import Session
from datetime import date


from railway.schemas import (
    StationRead, StationCreate, BaseResponse, StationSingleQuery, StationListQuery, StationListResponse,
    TrainScheduleRead, TrainScheduleListQuery, TrainScheduleSingleQuery, TrainScheduleBatchCreate, TrainListQuery,
    TrainSingleQuery, TrainRead, TrainCreate, TrainOperationPlanRead, TrainOperationPlanListQuery,
    TrainOperationPlanSingleQuery, TrainOperationPlanCreate, TrainListResponse, TrainScheduleResponse,
    TicketBatchRequest, TicketStats, TicketBatchResponse
)
from railway.crud import (
    create_station, get_station_single, get_station_list, get_train_full_schedule, delete_train_schedule,
    get_train_schedule_list, get_train_schedule_single, create_train_schedule_batch, delete_train, get_train_list,
    get_train_single, create_train, delete_train_operation_plan, update_train_operation_plan_status,
    get_train_operation_plan_list, get_train_operation_plan_single, create_train_operation_plan,
    get_schedule_by_train_code_and_date,
)
from railway.db.models.models import Train, TrainSchedule, TrainOperationPlan
from railway.db.dependencies import get_ready_db as get_db
from app.dependencies import BaseResponse as ApiResponse

router = APIRouter()


@router.get("/status", response_model=ApiResponse[Dict[str, str]])
def railway_initialization_status() -> ApiResponse[Dict[str, str]]:
    from railway.initialization import get_initialization_state
    return ApiResponse.success(data={"state": get_initialization_state()})

# ------------------------------ 车站接口 ------------------------------
@router.post(
    "/stations",
    response_model=BaseResponse[StationRead],  # 统一响应模型+业务数据结构
    summary="创建/更新车站（存在则检查更新）"
)
def create_or_update_station_api(
        station: StationCreate = Body(..., description="车站信息"),
        db: Session = Depends(get_db)
):
    # 调用 CRUD 函数，获取 code、msg、data
    code, msg, data = create_station(db, station)

    # 返回统一响应格式
    return BaseResponse(
        code=code,
        msg=msg,
        data=data  # data 为 ORM 模型，BaseResponse 会通过 from_attributes 自动转换为 StationRead
    )

# ------------------------------ 单条车站查询接口 ------------------------------
@router.get(
    "/stations/single",
    response_model=BaseResponse[StationRead],
    summary="单条车站查询（ID/电报码/名称三选一）"
)
def query_station_single(
    # 查询参数（与StationSingleQuery对应，使用Query绑定）
    station_id: Optional[int] = Query(None, description="车站ID（与telecode/name三选一）"),
    telecode: Optional[str] = Query(None, max_length=3, description="车站电报码（唯一，三选一）"),
    station_name: Optional[str] = Query(None, description="车站名称（精确匹配，三选一）"),
    db: Session = Depends(get_db)
):
    # 构造查询参数对象
    query = StationSingleQuery(
        station_id=station_id,
        telecode=telecode,
        station_name=station_name
    )
    # 调用CRUD函数
    code, msg, data = get_station_single(db, query)
    # 返回统一响应
    return BaseResponse(code=code, msg=msg, data=data)

# ------------------------------ 车站列表查询接口 ------------------------------
@router.get(
    "/stations",
    response_model=BaseResponse[StationListResponse],  # data为分页字典
    summary="车站列表查询（支持筛选、模糊搜索、分页）"
)
def query_station_list(
    # 筛选参数
    province: Optional[str] = Query(None, description="所属省份（可选）"),
    city: Optional[str] = Query(None, description="所属城市（可选）"),
    district: Optional[str] = Query(None, description="所属区县（可选）"),
    is_high_speed: Optional[int] = Query(None, ge=0, le=1, description="是否高铁站（0=普速，1=高铁）"),
    status: Optional[int] = Query(1, ge=0, le=1, description="状态（1=运营，0=暂停）"),
    # 搜索参数
    keyword: Optional[str] = Query(None, description="搜索关键词（匹配名称/全拼/简拼）"),
    # 分页参数
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=5000, description="每页条数（1-5000）"),
    db: Session = Depends(get_db)
):
    # 构造查询参数对象
    query = StationListQuery(
        province=province,
        city=city,
        district=district,
        is_high_speed=is_high_speed,
        status=status,
        keyword=keyword,
        page=page,
        page_size=page_size
    )
    # 调用CRUD函数
    code, msg, data = get_station_list(db, query)
    # 返回统一响应
    return BaseResponse(code=code, msg=msg, data=data)

# ------------------------------ 运行计划接口 ------------------------------
@router.post(
    "/train-operation-plans",
    response_model=BaseResponse[TrainOperationPlanRead],
    summary="创建/更新运行计划（存在则更新）"
)
def create_or_update_operation_plan(
    plan: TrainOperationPlanCreate = Body(..., description="运行计划信息"),
    db: Session = Depends(get_db)
):
    code, msg, data = create_train_operation_plan(db, plan)
    return BaseResponse(code=code, msg=msg, data=data)

@router.get(
    "/train-operation-plans/single",
    response_model=BaseResponse[TrainOperationPlanRead],
    summary="单条运行计划查询（ID/车次编号二选一）"
)
def query_operation_plan_single(
    operation_id: Optional[int] = Query(None, description="运行计划ID（与train_no二选一）"),
    train_no: Optional[str] = Query(None, max_length=20, description="车次编号（与operation_id二选一）"),
    db: Session = Depends(get_db)
):
    query = TrainOperationPlanSingleQuery(operation_id=operation_id, train_no=train_no)
    code, msg, data = get_train_operation_plan_single(db, query)
    return BaseResponse(code=code, msg=msg, data=data)

@router.get(
    "/train-operation-plans",
    response_model=BaseResponse[Dict[str, Any]],
    summary="运行计划列表查询（筛选+分页）"
)
def query_operation_plan_list(
    train_no: Optional[str] = Query(None, description="车次编号（模糊匹配）"),
    start_date: Optional[date] = Query(None, description="生效开始日期（>=该日期）"),
    end_date: Optional[date] = Query(None, description="生效结束日期（<=该日期）"),
    run_rule: Optional[int] = Query(None, ge=0, le=5, description="开行规律：0=每日，1=工作日...5=自定义"),
    status: Optional[int] = Query(1, ge=0, le=1, description="状态（1=正常，0=停运）"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数（1-100）"),
    db: Session = Depends(get_db)
):
    query = TrainOperationPlanListQuery(
        train_no=train_no, start_date=start_date, end_date=end_date,
        run_rule=run_rule, status=status, page=page, page_size=page_size
    )
    code, msg, data = get_train_operation_plan_list(db, query)
    return BaseResponse(code=code, msg=msg, data=data)

@router.patch(
    "/train-operation-plans/{operation_id}/status",
    response_model=BaseResponse[TrainOperationPlanRead],
    summary="更新运行计划状态（正常/停运）"
)
def update_operation_plan_status(
    operation_id: int = Path(..., ge=1, description="运行计划ID"),
    status: int = Body(..., ge=0, le=1, description="目标状态：1=正常，0=停运"),
    db: Session = Depends(get_db)
):
    code, msg, data = update_train_operation_plan_status(db, operation_id, status)
    return BaseResponse(code=code, msg=msg, data=data)

@router.delete(
    "/train-operation-plans/{operation_id}",
    response_model=BaseResponse[None],
    summary="删除运行计划（级联删除关联车次和时刻表）"
)
def delete_operation_plan(
    operation_id: int = Path(..., ge=1, description="运行计划ID"),
    db: Session = Depends(get_db)
):
    code, msg = delete_train_operation_plan(db, operation_id)
    return BaseResponse(code=code, msg=msg, data=None)

# ------------------------------ 车次接口 ------------------------------
@router.post(
    "/trains",
    response_model=BaseResponse[TrainRead],
    summary="创建/更新车次（需关联已存在的运行计划和车站）"
)
def create_or_update_train(
    train: TrainCreate = Body(..., description="车次信息"),
    db: Session = Depends(get_db)
):
    code, msg, data = create_train(db, train)
    return BaseResponse(code=code, msg=msg, data=data)

@router.get(
    "/trains/single",
    response_model=BaseResponse[TrainRead],
    summary="单条车次查询（支持ID/内部编号/对外车次等多字段）"
)
def query_train_single(
    train_id: Optional[int] = Query(None, description="车次ID"),
    train_no: Optional[str] = Query(None, description="铁路内部编号（如0G12300）"),
    train_code: Optional[str] = Query(None, description="对外公布车次（如G123）"),
    from_station: Optional[str] = Query(None, description="出发站电报码"),
    to_station: Optional[str] = Query(None, description="到达站电报码"),
    db: Session = Depends(get_db)
):
    query = TrainSingleQuery(
        train_id=train_id, train_no=train_no, train_code=train_code,
        from_station=from_station, to_station=to_station
    )
    code, msg, data = get_train_single(db, query)
    return BaseResponse(code=code, msg=msg, data=data)

@router.get(
    "/trains",
    response_model=BaseResponse[TrainListResponse],
    summary="车次列表查询（筛选+模糊搜索+分页）"
)
def query_train_list(
    train_code: Optional[str] = Query(None, description="对外车次（模糊匹配）"),
    train_type: Optional[str] = Query(None, description="列车类型（G/D/Z/T/K等）"),
    from_station: Optional[str] = Query(None, description="出发站（电报码或名称模糊匹配）"),
    to_station: Optional[str] = Query(None, description="到达站（电报码或名称模糊匹配）"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数（1-100）"),
    db: Session = Depends(get_db)
):
    query = TrainListQuery(
        train_code=train_code, train_type=train_type,
        from_station=from_station, to_station=to_station,
        page=page, page_size=page_size
    )
    code, msg, data = get_train_list(db, query)
    return BaseResponse(code=code, msg=msg, data=data)

@router.delete(
    "/trains/{train_no}",
    response_model=BaseResponse[None],
    summary="删除车次（需先解除运行计划关联或删除运行计划）"
)
def delete_train_api(
    train_no: str = Path(..., max_length=20, description="铁路内部编号（如0G12300）"),
    db: Session = Depends(get_db)
):
    code, msg = delete_train(db, train_no)
    return BaseResponse(code=code, msg=msg, data=None)

# ------------------------------ 时刻表接口 ------------------------------
@router.post(
    "/train-schedules/batch",
    response_model=BaseResponse[List[TrainScheduleRead]],
    summary="批量创建/更新时刻表（一个运行计划对应多个站点）"
)
def batch_create_or_update_schedule(
    batch_data: TrainScheduleBatchCreate = Body(..., description="批量时刻表数据（至少2条：出发站+到达站）"),
    db: Session = Depends(get_db)
):
    code, msg, data = create_train_schedule_batch(db, batch_data)
    return BaseResponse(code=code, msg=msg, data=data)

@router.get(
    "/train-schedules/single",
    response_model=BaseResponse[TrainScheduleRead],
    summary="单条时刻表查询（支持ID/车次/车站/顺序）"
)
def query_schedule_single(
    schedule_id: Optional[int] = Query(None, description="时刻表ID"),
    train_no: Optional[str] = Query(None, description="车次编号"),
    station_telecode: Optional[str] = Query(None, max_length=3, description="车站电报码"),
    sequence: Optional[int] = Query(None, ge=1, description="途经顺序"),
    db: Session = Depends(get_db)
):
    query = TrainScheduleSingleQuery(
        schedule_id=schedule_id, train_no=train_no,
        station_telecode=station_telecode, sequence=sequence
    )
    code, msg, data = get_train_schedule_single(db, query)
    return BaseResponse(code=code, msg=msg, data=data)

@router.get(
    "/train-schedules",
    response_model=BaseResponse[TrainScheduleResponse],
    summary="时刻表列表查询（筛选+模糊搜索+分页）"
)
def query_schedule_list(
    train_no: Optional[str] = Query(None, description="车次编号（模糊匹配）"),
    train_code: Optional[str] = Query(None, description="对外车次（精准匹配）"),
    station_telecode: Optional[str] = Query(None, description="车站电报码"),
    station_name: Optional[str] = Query(None, description="车站名称（模糊匹配）"),
    is_departure: Optional[int] = Query(None, ge=0, le=1, description="是否出发站（1=是）"),
    is_arrival: Optional[int] = Query(None, ge=0, le=1, description="是否到达站（1=是）"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数（1-100）"),
    db: Session = Depends(get_db)
):
    query = TrainScheduleListQuery(
        train_no=train_no, train_code=train_code, station_telecode=station_telecode,
        station_name=station_name, is_departure=is_departure, is_arrival=is_arrival,
        page=page, page_size=page_size
    )
    code, msg, data = get_train_schedule_list(db, query)
    return BaseResponse(code=code, msg=msg, data=data)

@router.get(
    "/train-schedules/full/{train_no}",
    response_model=BaseResponse[List[TrainScheduleRead]],
    summary="获取某车次完整时刻表（按途经顺序排序）"
)
def query_full_schedule(
    train_no: str = Path(..., max_length=20, description="车次编号（如0G12300）"),
    db: Session = Depends(get_db)
):
    code, msg, data = get_train_full_schedule(db, train_no)
    return BaseResponse(code=code, msg=msg, data=data)

@router.delete(
    "/train-schedules/{train_no}",
    response_model=BaseResponse[None],
    summary="删除时刻表（支持删除全车次或单个站点）"
)
def delete_schedule(
    train_no: str = Path(..., max_length=20, description="车次编号"),
    station_telecode: Optional[str] = Query(None, max_length=3, description="车站电报码（留空则删除全车次时刻表）"),
    db: Session = Depends(get_db)
):
    code, msg = delete_train_schedule(db, train_no, station_telecode)
    return BaseResponse(code=code, msg=msg, data=None)

@router.get(
    "/trains/{train_code}/schedules",
    response_model=BaseResponse[List[TrainScheduleRead]],
    summary="根据对外车次（train_code）和日期查询时刻表"
)
def query_schedule_by_train_code_and_date(
    train_code: str = Path(..., max_length=20, description="对外公布车次（如G123/D456）"),
    query_date: date = Query(..., description="查询日期（YYYY-MM-DD，如2025-11-20）"),
    db: Session = Depends(get_db)
):
    """
    按对外车次和日期查询完整时刻表：
    1. 自动匹配对应的内部编号（train_no）
    2. 校验该日期的运行计划是否有效（生效时间+开行规律）
    3. 返回按途经顺序排序的完整时刻表
    """
    code, msg, data = get_schedule_by_train_code_and_date(db, train_code, query_date)
    return BaseResponse(code=code, msg=msg, data=data)

# ------------------------------ 统计查询接口（新增）------------------------------
@router.post("/stats/batch", response_model=TicketBatchResponse, summary="批量计算车票里程和时长")
def batch_calculate_stats(
    request: TicketBatchRequest,
    db: Session = Depends(get_db)
):
    results = []
    # 1. 收集所有车次号
    train_codes = set(item.train_code for item in request.items)
    if not train_codes:
        return BaseResponse(data=[])

    # 2. 批量查询车次对应关系 (Train Code -> Train No)
    trains = db.query(Train).filter(Train.train_code.in_(train_codes)).all()
    
    code_to_train_nos = {}
    for t in trains:
        if t.train_code not in code_to_train_nos:
            code_to_train_nos[t.train_code] = []
        code_to_train_nos[t.train_code].append(t.train_no)

    # 3. 收集相关的 train_no，准备查询时刻表
    all_train_nos = []
    for nos in code_to_train_nos.values():
        all_train_nos.extend(nos)
    
    # 4. 批量查询时刻表
    if all_train_nos:
        schedules = db.query(TrainSchedule).filter(
            TrainSchedule.train_no.in_(all_train_nos)
        ).all()
    else:
        schedules = []

    # 构建内存索引: train_no -> { station_name -> schedule_record }
    schedule_map = {}
    for s in schedules:
        if s.train_no not in schedule_map:
            schedule_map[s.train_no] = {}
        schedule_map[s.train_no][s.station_name] = s

    # 5. 遍历请求项计算结果
    for item in request.items:
        stats = TicketStats(id=item.id, distance_km=0, duration_minutes=0)
        
        candidate_nos = code_to_train_nos.get(item.train_code, [])
        best_no = None
        
        # 寻找包含出发和到达站的 train_no
        for no in candidate_nos:
            s_map = schedule_map.get(no, {})
            if item.departure_station in s_map and item.arrival_station in s_map:
                best_no = no
                break
        
        if best_no:
            s_map = schedule_map[best_no]
            dep = s_map[item.departure_station]
            arr = s_map[item.arrival_station]
            
            # 计算距离
            try:
                dist = float(arr.accumulated_mileage) - float(dep.accumulated_mileage)
                if dist < 0: dist = 0
                stats.distance_km = dist
            except:
                stats.distance_km = 0
            
            # 计算时长
            try:
                dur = arr.running_time - dep.running_time
                if dur < 0: dur = 0
                stats.duration_minutes = dur
            except:
                stats.duration_minutes = 0
                
            stats.train_no = best_no
            
        results.append(stats)

    return BaseResponse(data=results)

if __name__ == "__main__":
    import uvicorn
    # 运行服务：http://127.0.0.1:8005/docs 可访问 Swagger 文档
    uvicorn.run("api:app", host="0.0.0.0", port=8005, reload=True)
