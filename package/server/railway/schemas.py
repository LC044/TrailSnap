#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
@Time        : 2025/11/18 20:50
@Author      : SiYuan
@Email       : sixyuan044@gmail.com
@File        : server-schemas.py
@Description : 铁路时刻表系统 Pydantic Schema（适配版本化运行计划）
"""

from datetime import date, time, datetime
from typing import List, Optional, Generic, TypeVar
from pydantic import BaseModel, Field, validator, field_validator

# 定义泛型类型（支持不同业务数据类型）
T = TypeVar("T")

# ------------------------------ 通用响应模型（统一错误码载体）------------------------------
class BaseResponse(BaseModel, Generic[T]):
    """所有接口的统一响应模型：包含错误码、提示信息、业务数据"""
    code: int = Field(default=200, description="错误码：200=成功，4xx=客户端错误，5xx=服务端错误")
    msg: str = Field(default="操作成功", description="提示信息")
    data: Optional[T] = Field(default=None, description="业务数据（成功时返回，失败时为None）")

    class Config:
        from_attributes = True  # 支持从 ORM 模型直接转换

# ------------------------------ 基础模型 ------------------------------
class BaseSchema(BaseModel):
    """基础 Schema，包含公共字段"""

    class Config:
        from_attributes = True  # 支持从 ORM 模型直接转换

# ------------------------------ 车站相关 ------------------------------
class StationCreate(BaseModel):
    telecode: Optional[str] = Field(max_length=3, description="电报码")
    station_name: str = Field(description="车站名称")
    station_pinyin: str = Field(description="拼音（全拼，如beijingxi）")
    station_py: str = Field(description="拼音（首字母，如bjx）")
    province: str = Field(description="所属省份")
    city: str = Field(description="所属城市")
    district: Optional[str] = Field(None, description="所属区县")
    is_high_speed: int = Field(ge=0, le=1, default=0, description="是否高铁站（0=普速，1=高铁）")
    status: int = Field(ge=0, le=1, default=1, description="状态（1=运营，0=暂停）")

class StationRead(BaseSchema):
    latitude: Optional[float] = Field(None, ge=-90, le=90, allow_inf_nan=False)
    longitude: Optional[float] = Field(None, ge=-180, le=180, allow_inf_nan=False)
    coordinate_source: Optional[str] = None
    coordinate_system: Optional[str] = None
    coordinates_updated_at: Optional[datetime] = None
    coordinate_status: Optional[str] = None
    station_name: str
    station_pinyin: str
    province: Optional[str]
    city: str
    district: Optional[str]
    telecode: Optional[str]
    is_high_speed: int
    status: int

# ------------------------------ 查询入参Schema（新增）------------------------------
class StationSingleQuery(BaseModel):
    """单条车站查询参数（支持ID/电报码/名称，三选一）"""
    station_id: Optional[int] = Field(None, description="车站ID（与telecode/name三选一）")
    telecode: Optional[str] = Field(None, max_length=3, description="车站电报码（唯一，三选一）")
    station_name: Optional[str] = Field(None, description="车站名称（精确匹配，三选一）")

class StationListQuery(BaseModel):
    """车站列表查询参数（支持筛选、模糊搜索、分页）"""
    # 筛选条件
    province: Optional[str] = Field(None, description="所属省份（精确匹配，如：北京市）")
    city: Optional[str] = Field(None, description="所属城市（精确匹配，如：北京市）")
    district: Optional[str] = Field(None, description="所属区县（精确匹配，如：丰台区）")
    is_high_speed: Optional[int] = Field(None, ge=0, le=1, description="是否高铁站（0=普速，1=高铁）")
    status: Optional[int] = Field(1, ge=0, le=1, description="状态（1=运营，0=暂停，默认查运营）")
    # 模糊搜索（名称/全拼/简拼）
    keyword: Optional[str] = Field(None, description="搜索关键词（匹配名称/全拼/简拼，如：bjx/北京西/beijingxi）")
    # 分页参数
    page: int = Field(1, ge=1, description="页码（默认第1页）")
    page_size: int = Field(20, ge=1, le=10000, description="每页条数（1-10000，默认20）")

# 定义列表查询的响应数据结构（明确 list 是 StationRead 列表）
class StationListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    total_page: int
    list: List[StationRead]  # 明确是 StationRead 列表


# ------------------------------ 运行计划相关 ------------------------------
class TrainOperationPlanCreate(BaseModel):
    train_no: str = Field(max_length=20, description="关联车次唯一编号（如0G12300）")
    start_date: date = Field(description="计划生效开始日期（YYYY-MM-DD）")
    end_date: Optional[date] = Field(None, description="计划生效结束日期（YYYY-MM-DD），NULL表示永久有效")
    run_rule: int = Field(ge=0, le=5, default=0, description="开行规律：0=每日，1=工作日，2=周末，3=单日，4=双日，5=自定义")
    custom_run_days: Optional[List[str]] = Field(None,
                                                 description="自定义开行日期（run_rule=5时必填，格式[\"2025-11-20\"]）")
    station_num: int = Field(ge=2, default=2, description="途经车站数（含起止站，至少2个）")
    total_mileage: float = Field(ge=0, default=0, description="全程里程（公里）")
    total_running_time: int = Field(ge=0, default=0, description="累计运行时间（分钟）")
    status: int = Field(ge=0, le=1, default=1, description="状态：1=正常，0=停运")

    @field_validator("custom_run_days")
    def check_custom_run_days(cls, v, info):
        """验证自定义开行日期：run_rule=5时必填，格式正确"""
        if info.data.get("run_rule") == 5 and not v:
            raise ValueError("run_rule=5时，custom_run_days不能为空")
        if v:
            for day in v:
                try:
                    datetime.strptime(day, "%Y-%m-%d")
                except ValueError:
                    raise ValueError(f"自定义日期格式错误：{day}（需为YYYY-MM-DD）")
        return v

    @field_validator("end_date")
    def check_date_order(cls, v, info):
        """验证开始日期<=结束日期"""
        if v:
            start_date = info.data.get("start_date")
            if start_date and start_date > v:
                raise ValueError("开始日期不能晚于结束日期")
        return v


class TrainOperationPlanRead(BaseSchema):
    operation_id: int
    train_no: str
    start_date: date
    end_date: Optional[date]
    run_rule: int
    custom_run_days: Optional[List[str]]
    station_num: int
    total_mileage: float
    total_running_time: int
    status: int


class TrainOperationPlanSingleQuery(BaseModel):
    """单条运行计划查询（主键/车次二选一）"""
    operation_id: Optional[int] = Field(None, description="运行计划ID（与train_no二选一）")
    train_no: Optional[str] = Field(None, max_length=20, description="车次编号（与operation_id二选一）")


class TrainOperationPlanListQuery(BaseModel):
    """运行计划列表查询（筛选+分页）"""
    train_no: Optional[str] = Field(None, description="车次编号（模糊匹配）")
    start_date: Optional[date] = Field(None, description="生效开始日期（>=该日期）")
    end_date: Optional[date] = Field(None, description="生效结束日期（<=该日期）")
    run_rule: Optional[int] = Field(None, ge=0, le=5, description="开行规律")
    status: Optional[int] = Field(1, ge=0, le=1, description="状态（默认查正常）")
    page: int = Field(1, ge=1, description="页码")
    page_size: int = Field(20, ge=1, le=100, description="每页条数")


# ------------------------------ 车次相关 ------------------------------
class TrainCreate(BaseModel):
    train_no: str = Field(max_length=20, description="铁路内部唯一编号（关联运行计划）")
    train_code: str = Field(max_length=20, description="对外公布车次（如G123/D456）")
    train_type: str = Field(max_length=2, description="列车类型（G/D/Z/T/K等）")
    from_station: str = Field(max_length=3, description="出发站电报码")
    to_station: str = Field(max_length=3, description="到达站电报码")


class TrainRead(BaseSchema):
    train_id: int
    train_no: str
    train_code: str
    train_type: str
    from_station: str
    to_station: str
    # 关联字段（可选，用于返回关联信息）
    departure_station_name: Optional[str] = Field(None, description="出发站名称")
    arrival_station_name: Optional[str] = Field(None, description="到达站名称")


class TrainSingleQuery(BaseModel):
    """单条车次查询（支持多字段）"""
    train_id: Optional[int] = Field(None, description="车次ID")
    train_no: Optional[str] = Field(None, description="内部编号")
    train_code: Optional[str] = Field(None, description="对外车次（如G123）")
    from_station: Optional[str] = Field(None, description="出发站电报码")
    to_station: Optional[str] = Field(None, description="到达站电报码")


class TrainListQuery(BaseModel):
    """车次列表查询（筛选+分页）"""
    train_code: Optional[str] = Field(None, description="对外车次（模糊匹配）")
    train_type: Optional[str] = Field(None, description="列车类型（G/D/Z等）")
    from_station: Optional[str] = Field(None, description="出发站电报码/名称（模糊）")
    to_station: Optional[str] = Field(None, description="到达站电报码/名称（模糊）")
    page: int = Field(1, ge=1, description="页码")
    page_size: int = Field(20, ge=1, le=100, description="每页条数")

# 定义列表查询的响应数据结构（明确 list 是 StationRead 列表）
class TrainListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    total_page: int
    list: List[TrainRead]  # 明确是 StationRead 列表

# ------------------------------ 时刻表相关 ------------------------------
class TrainScheduleCreate(BaseModel):
    """单条时刻表创建模型"""
    train_no: str = Field(max_length=20, description="关联运行计划的车次编号")
    train_code: str = Field(max_length=20, description="对外公布车次")
    station_telecode: str = Field(max_length=3, description="途经站电报码")
    station_name: str = Field(description="途经站名称")
    sequence: int = Field(ge=1, description="途经顺序（1=出发站，递增）")
    arrive_day_diff: int = Field(ge=0, default=0, description="到达天数差（跨天为1）")
    arrival_time: Optional[time] = Field(None, description="到站时间（出发站为NULL）")
    departure_time: Optional[time] = Field(None, description="发车时间（到达站为NULL）")
    stop_duration: int = Field(ge=0, default=0, description="停留时长（分钟）")
    accumulated_mileage: float = Field(ge=0, description="累计里程（公里）")
    running_time: int = Field(ge=0, description="累计运行时间（分钟）")
    is_departure: int = Field(ge=0, le=1, default=0, description="是否出发站：1=是")
    is_arrival: int = Field(ge=0, le=1, default=0, description="是否到达站：1=是")

    @field_validator("arrival_time", "departure_time")  # 1. 改为 field_validator
    def check_time_logic(cls, v, info):  # 2. 参数改为 (v, info)
        """验证时间逻辑：出发站无到站时间，到达站无发车时间"""
        # 3. 通过 info 获取当前字段名和其他字段值
        current_field = info.field_name  # 对应原来的 field.name
        data = info.data  # 对应原来的 values（其他已验证的字段）

        is_departure = data.get("is_departure", 0)
        is_arrival = data.get("is_arrival", 0)

        if is_departure == 1:
            if current_field == "arrival_time" and v is not None:
                raise ValueError("出发站不能设置到站时间")
            if current_field == "departure_time" and v is None:
                raise ValueError("出发站必须设置发车时间")
        if is_arrival == 1:
            if current_field == "departure_time" and v is not None:
                raise ValueError("到达站不能设置发车时间")
            if current_field == "arrival_time" and v is None:
                raise ValueError("到达站必须设置到站时间")
        return v

    @field_validator("is_departure", "is_arrival")  # 1. 改为 field_validator
    def check_departure_arrival(cls, v, info):  # 2. 参数改为 (v, info)
        """验证出发站/到达站逻辑：只能有一个出发站和一个到达站"""
        current_field = info.field_name  # 对应原来的 field.name
        data = info.data  # 对应原来的 values（其他已验证的字段）

        other_field = "is_arrival" if current_field == "is_departure" else "is_departure"
        if v == 1 and data.get(other_field, 0) == 1:
            raise ValueError("一个站点不能同时是出发站和到达站")
        return v


# 批量创建时刻表
class TrainScheduleBatchCreate(BaseModel):
    schedules: List[TrainScheduleCreate] = Field(description="时刻表列表（至少2条：出发站+到达站）")

    @field_validator("schedules")
    def check_schedules_logic(cls, v):
        """验证时刻表列表逻辑：至少2条，顺序连续，出发站/到达站各一个"""
        if len(v) < 2:
            raise ValueError("时刻表至少包含出发站和到达站（2条记录）")

        # 验证顺序连续（1,2,3...）
        sequences = [item.sequence for item in v]
        if sorted(sequences) != list(range(1, len(v) + 1)):
            raise ValueError("途经顺序必须连续递增（1,2,3...）")

        # 验证出发站和到达站各一个
        departure_count = sum(1 for item in v if item.is_departure == 1)
        arrival_count = sum(1 for item in v if item.is_arrival == 1)
        if departure_count != 1:
            raise ValueError("时刻表必须包含且仅包含一个出发站")
        if arrival_count != 1:
            raise ValueError("时刻表必须包含且仅包含一个到达站")

        # 验证出发站顺序为1，到达站顺序为最后
        departure_seq = next(item.sequence for item in v if item.is_departure == 1)
        arrival_seq = next(item.sequence for item in v if item.is_arrival == 1)
        if departure_seq != 1:
            raise ValueError("出发站的途经顺序必须为1")
        if arrival_seq != len(v):
            raise ValueError("到达站的途经顺序必须为最后一位")

        return v


class TrainScheduleRead(BaseSchema):
    schedule_id: int
    train_no: str
    train_code: str
    station_telecode: str
    station_name: str
    sequence: int
    arrive_day_diff: int
    arrival_time: Optional[time]
    departure_time: Optional[time]
    stop_duration: int
    accumulated_mileage: float
    running_time: int
    is_departure: int
    is_arrival: int


class TrainScheduleSingleQuery(BaseModel):
    """单条时刻表查询"""
    schedule_id: Optional[int] = Field(None, description="时刻表ID")
    train_no: Optional[str] = Field(None, description="车次编号")
    station_telecode: Optional[str] = Field(None, description="车站电报码")
    sequence: Optional[int] = Field(None, description="途经顺序")


class TrainScheduleListQuery(BaseModel):
    """时刻表列表查询（筛选+分页）"""
    train_no: Optional[str] = Field(None, description="车次编号（模糊匹配）")
    train_code: Optional[str] = Field(None, description="对外车次（模糊匹配）")
    station_telecode: Optional[str] = Field(None, description="车站电报码")
    station_name: Optional[str] = Field(None, description="车站名称（模糊匹配）")
    is_departure: Optional[int] = Field(None, ge=0, le=1, description="是否出发站")
    is_arrival: Optional[int] = Field(None, ge=0, le=1, description="是否到达站")
    page: int = Field(1, ge=1, description="页码")
    page_size: int = Field(20, ge=1, le=100, description="每页条数")

class TrainScheduleResponse(BaseModel):
    total: int
    page: int
    page_size: int
    total_page: int
    list: List[TrainScheduleRead]  # 明确是 StationRead 列表

# ------------------------------ 关联查询响应模型（可选，用于返回关联信息）------------------------------
class TrainWithOperationPlanRead(TrainRead):
    """包含运行计划信息的车次响应"""
    operation_plan: Optional[TrainOperationPlanRead] = Field(None, description="关联运行计划")


class TrainScheduleWithStationRead(TrainScheduleRead):
    """包含车站信息的时刻表响应"""
    station: Optional[StationRead] = Field(None, description="关联车站信息")

# ------------------------------ 统计查询相关（新增）------------------------------
class TicketItem(BaseModel):
    id: Optional[str] = Field(None, description="车票唯一标识（可选，用于回传）")
    train_code: str = Field(..., description="车次号（如G123）")
    departure_station: str = Field(..., description="出发站名称")
    arrival_station: str = Field(..., description="到达站名称")
    date_time: Optional[str] = Field(None, description="乘车日期（YYYY-MM-DD或YYYY-MM-DD HH:MM:SS，可选）")

class TicketBatchRequest(BaseModel):
    items: List[TicketItem] = Field(..., description="车票列表")

class TicketStats(BaseModel):
    id: Optional[str] = Field(None, description="车票唯一标识")
    distance_km: Optional[float] = Field(0, description="旅程距离（公里），未知时为空")
    duration_minutes: Optional[int] = Field(0, description="旅程时长（分钟），未知时为空")
    train_no: Optional[str] = Field(None, description="匹配到的内部车次号")

class TicketBatchResponse(BaseResponse[List[TicketStats]]):
    pass
