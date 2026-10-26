#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
@Time        : 2025/11/18 20:50
@Author      : SiYuan
@Email       : sixyuan044@gmail.com
@File        : server-crud.py
@Description : 
"""

from typing import List, Optional, Dict, Any, Tuple
from datetime import date, time, datetime
from sqlalchemy import create_engine, or_
from sqlalchemy.orm import Session, sessionmaker, joinedload
from sqlalchemy.exc import IntegrityError, SQLAlchemyError, NoResultFound

# 导入数据库模型和Pydantic Schema
from railway.db.models.models import (
    Base, Station, Train, TrainOperationPlan, TrainSchedule
)

from railway.schemas import (
    StationCreate, StationRead, StationListQuery, StationSingleQuery, TrainScheduleListQuery, TrainScheduleSingleQuery,
    TrainScheduleBatchCreate, TrainListQuery, TrainSingleQuery, TrainCreate, TrainOperationPlanListQuery,
    TrainOperationPlanSingleQuery, TrainOperationPlanCreate
)
from railway.util.city import standardize_city_name, PROVINCE_MAPPING

def format_station_name(name:str):
    return name.strip().replace(' ','')

# ------------------------------ 车站 CRUD ------------------------------
def create_station(db: Session, station: StationCreate) -> Tuple[int, str, Optional[Station]]:
    """
    创建车站
    :param db: 数据库会话
    :param station: 车站创建模型
    :return: (创建成功的车站对象, 状态信息)
    """
    """
    创建/更新车站（存在则检查更新）
    返回格式：(code, msg, data)
    """
    try:
        # 1. 验证必填字段（telecode 可选，但 station_name 等必填）
        required_fields = ["station_name", "station_pinyin", "station_py", "province", "city"]
        for field in required_fields:
            if not getattr(station, field):
                return 400, f"缺少必填字段：{field}", None

        # 2. 检查是否已存在（按 telecode 或 station_name 匹配）
        query = db.query(Station)
        if station.telecode:
            existing = query.filter(Station.telecode == station.telecode).first()
        else:
            # 无电报码时，按名称+城市唯一匹配（避免重复创建）
            existing = query.filter(
                Station.station_name == station.station_name,
                Station.city == station.city
            ).first()

        if existing:
            # 3. 已存在：更新字段（不覆盖 telecode，除非显式传入）
            for key, value in station.dict(exclude_unset=True).items():
                if key != "telecode":  # 电报码不允许更新（唯一标识）
                    setattr(existing, key, value)
            db.commit()
            db.refresh(existing)
            return 200, "车站已存在，已更新信息", existing
        else:
            # 4. 不存在：新增车站
            new_station = Station(**station.dict())
            db.add(new_station)
            db.commit()
            db.refresh(new_station)
            return 200, "车站创建成功", new_station

    except IntegrityError:
        db.rollback()
        return 409, f"电报码{station.telecode}已存在（唯一约束冲突）", None
    except Exception as e:
        db.rollback()
        return 500, f"服务端错误：{str(e)}", None

def get_station_single(db: Session, query: StationSingleQuery) -> Tuple[int, str, Optional[Station]]:
    """
    单条车站查询（支持ID/电报码/名称三选一）
    返回：(code, msg, station对象)
    """
    try:
        # 校验查询条件（三选一）
        query_count = sum([1 for x in [query.station_id, query.telecode, query.station_name] if x is not None])
        if query_count == 0:
            return 400, "必须指定查询条件（station_id/telecode/station_name三选一）", None
        if query_count > 1:
            return 400, "查询条件冲突（station_id/telecode/station_name只能选一个）", None

        # 构建查询
        db_query = db.query(Station)
        if query.station_id:
            station = db_query.filter(Station.station_id == query.station_id).first()
        elif query.telecode:
            station = db_query.filter(Station.telecode == query.telecode).first()
        else:  # station_name（精确匹配）
            station_name = format_station_name(query.station_name)
            station = db_query.filter(Station.station_name == station_name).first()
            if station is None:
                from railway.history_cache import HistoryCache
                candidates = HistoryCache().stations(station_name)
                if len(candidates) == 1:
                    station = db_query.filter(Station.telecode == candidates[0]['telecode']).first()

        if not station:
            return 404, f"未找到符合条件的车站", None
        return 200, "查询成功", station
    except Exception as e:
        return 500, f"查询失败：{str(e)}", None

def get_station_list(db: Session, query: StationListQuery) -> Tuple[int, str, Dict[str, Any]]:
    try:
        db_query = db.query(Station)

        # 🌟 关键修改：标准化用户输入的省份和城市
        standard_province = standardize_city_name(query.province)
        standard_city = standardize_city_name(query.city)
        print(standard_city,standard_province)
        # 1. 省份筛选（前缀模糊匹配，兼容数据库存储的全称）
        if standard_province:
            # 两种情况：1. 标准化后是规范值（如“河南省”）→ 精确匹配；2. 是关键词（如“henan”）→ 模糊匹配
            if standard_province in PROVINCE_MAPPING.keys():
                # 规范值直接精确匹配（高效）
                db_query = db_query.filter(Station.province == standard_province)
            else:
                # 关键词前缀模糊匹配（避免过度模糊）
                db_query = db_query.filter(Station.province.ilike(f"{standard_province}%"))

        # 2. 城市筛选（同理，前缀模糊匹配）
        if standard_city:
            db_query = db_query.filter(Station.city.ilike(f"{standard_city}%"))

        # 3. 其他筛选条件（不变）
        if query.district:
            db_query = db_query.filter(Station.district.ilike(f"{query.district}%"))  # 区县也支持模糊
        if query.is_high_speed is not None:
            db_query = db_query.filter(Station.is_high_speed == query.is_high_speed)
        if query.status is not None:
            db_query = db_query.filter(Station.status == query.status)

        # 4. 模糊搜索（名称/全拼/简拼，不变）
        if query.keyword:
            keyword = f"%{query.keyword}%"
            from railway.history_cache import HistoryCache
            with HistoryCache().connect() as history:
                alias_codes = [row[0] for row in history.execute(
                    'SELECT DISTINCT code FROM station_name WHERE name LIKE ?', (keyword,))]
            db_query = db_query.filter(
                or_(
                    Station.telecode.in_(alias_codes),
                    Station.station_name.ilike(keyword),
                    Station.station_pinyin.ilike(keyword),
                    Station.station_py.ilike(keyword)
                )
            )

        # 5. 分页查询
        total = db_query.count()
        offset = (query.page - 1) * query.page_size
        stations_orm = db_query.order_by(Station.station_name.asc()).offset(offset).limit(query.page_size).all()


        # 7. 构造返回数据
        data = {
            "total": total,
            "page": query.page,
            "page_size": query.page_size,
            "total_page": (total + query.page_size - 1) // query.page_size,
            "list": stations_orm
        }
        return 200, "列表查询成功", data
    except Exception as e:
        return 500, f"列表查询失败：{str(e)}", {
            "total": 0,
            "page": query.page,
            "page_size": query.page_size,
            "total_page": 0,
            "list": []
        }


# ------------------------------ 运行计划 CRUD ------------------------------
def create_train_operation_plan(db: Session, plan: TrainOperationPlanCreate) -> Tuple[
    int, str, Optional[TrainOperationPlan]]:
    """创建运行计划（已存在则更新）"""
    try:
        # 检查是否已存在（按train_no唯一约束）
        existing = db.query(TrainOperationPlan).filter(TrainOperationPlan.train_no == plan.train_no).first()

        if existing:
            # 已存在：更新字段（不允许修改train_no）
            update_data = plan.dict(exclude_unset=True, exclude={"train_no"})
            for key, value in update_data.items():
                setattr(existing, key, value)
            db.commit()
            db.refresh(existing)
            return 200, "运行计划已存在，已更新信息", existing
        else:
            # 不存在：新增
            new_plan = TrainOperationPlan(**plan.dict())
            db.add(new_plan)
            db.commit()
            db.refresh(new_plan)
            return 201, "运行计划创建成功", new_plan
    except IntegrityError:
        db.rollback()
        return 409, f"车次编号{plan.train_no}已存在（唯一约束冲突）", None
    except Exception as e:
        db.rollback()
        return 500, f"创建运行计划失败：{str(e)}", None


def get_train_operation_plan_single(db: Session, query: TrainOperationPlanSingleQuery) -> Tuple[
    int, str, Optional[TrainOperationPlan]]:
    """单条运行计划查询（ID/车次二选一）"""
    try:
        # 校验查询条件
        query_count = sum([1 for x in [query.operation_id, query.train_no] if x is not None])
        if query_count == 0:
            return 400, "必须指定查询条件（operation_id/train_no二选一）", None
        if query_count > 1:
            return 400, "查询条件冲突（operation_id/train_no只能选一个）", None

        # 构建查询
        db_query = db.query(TrainOperationPlan)
        if query.operation_id:
            plan = db_query.filter(TrainOperationPlan.operation_id == query.operation_id).first()
        else:
            plan = db_query.filter(TrainOperationPlan.train_no == query.train_no).first()

        if not plan:
            return 404, "未找到符合条件的运行计划", None
        return 200, "查询成功", plan
    except Exception as e:
        return 500, f"查询运行计划失败：{str(e)}", None


def get_train_operation_plan_list(db: Session, query: TrainOperationPlanListQuery) -> Tuple[int, str, Dict[str, Any]]:
    """运行计划列表查询（筛选+分页）"""
    try:
        db_query = db.query(TrainOperationPlan)

        # 筛选条件
        if query.train_no:
            db_query = db_query.filter(TrainOperationPlan.train_no.ilike(f"%{query.train_no}%"))
        if query.start_date:
            db_query = db_query.filter(TrainOperationPlan.start_date >= query.start_date)
        if query.end_date:
            db_query = db_query.filter(
                or_(
                    TrainOperationPlan.end_date.is_(None),
                    TrainOperationPlan.end_date <= query.end_date
                )
            )
        if query.run_rule is not None:
            db_query = db_query.filter(TrainOperationPlan.run_rule == query.run_rule)
        if query.status is not None:
            db_query = db_query.filter(TrainOperationPlan.status == query.status)

        # 分页
        total = db_query.count()
        offset = (query.page - 1) * query.page_size
        plans = db_query.order_by(TrainOperationPlan.train_no.asc(), TrainOperationPlan.start_date.asc()).offset(
            offset).limit(query.page_size).all()

        # 构造返回数据
        data = {
            "total": total,
            "page": query.page,
            "page_size": query.page_size,
            "total_page": (total + query.page_size - 1) // query.page_size,
            "list": plans
        }
        return 200, "运行计划列表查询成功", data
    except Exception as e:
        return 500, f"查询运行计划列表失败：{str(e)}", {
            "total": 0,
            "page": query.page,
            "page_size": query.page_size,
            "total_page": 0,
            "list": []
        }


def update_train_operation_plan_status(db: Session, operation_id: int, status: int) -> Tuple[
    int, str, Optional[TrainOperationPlan]]:
    """更新运行计划状态（单独抽离，常用操作）"""
    try:
        plan = db.query(TrainOperationPlan).filter(TrainOperationPlan.operation_id == operation_id).first()
        if not plan:
            return 404, "未找到运行计划", None

        plan.status = status
        db.commit()
        db.refresh(plan)
        return 200, f"运行计划状态已更新为{'正常' if status == 1 else '停运'}", plan
    except Exception as e:
        db.rollback()
        return 500, f"更新运行计划状态失败：{str(e)}", None


def delete_train_operation_plan(db: Session, operation_id: int) -> Tuple[int, str]:
    """删除运行计划（级联删除关联的车次和时刻表）"""
    try:
        plan = db.query(TrainOperationPlan).filter(TrainOperationPlan.operation_id == operation_id).first()
        if not plan:
            return 404, "未找到运行计划"

        db.delete(plan)
        db.commit()
        return 200, "运行计划已删除（关联车次和时刻表已级联删除）"
    except Exception as e:
        db.rollback()
        return 500, f"删除运行计划失败：{str(e)}"


# ------------------------------ 车次 CRUD ------------------------------
def create_train(db: Session, train: TrainCreate) -> Tuple[int, str, Optional[Train]]:
    """创建车次（需确保关联的运行计划和车站存在）"""
    try:
        # 校验关联的运行计划是否存在
        operation_plan = db.query(TrainOperationPlan).filter(TrainOperationPlan.train_no == train.train_no).first()
        if not operation_plan:
            return 404, f"关联的运行计划（train_no={train.train_no}）不存在", None

        # 校验出发站和到达站是否存在
        from_station = db.query(Station).filter(Station.telecode == train.from_station).first()
        to_station = db.query(Station).filter(Station.telecode == train.to_station).first()
        if not from_station:
            return 404, f"出发站（电报码={train.from_station}）不存在", None
        if not to_station:
            return 404, f"到达站（电报码={train.to_station}）不存在", None

        # 检查车次是否已存在（按train_no唯一）
        existing = db.query(Train).filter(Train.train_no == train.train_no).first()
        if existing:
            # 已存在：更新字段
            update_data = train.dict(exclude_unset=True, exclude={"train_no"})
            for key, value in update_data.items():
                setattr(existing, key, value)
            db.commit()
            db.refresh(existing)
            return 200, "车次已存在，已更新信息", existing
        else:
            # 不存在：新增
            new_train = Train(**train.dict())
            db.add(new_train)
            db.commit()
            db.refresh(new_train)
            return 201, "车次创建成功", new_train
    except IntegrityError:
        db.rollback()
        return 409, f"车次编号{train.train_no}已存在（唯一约束冲突）", None
    except Exception as e:
        db.rollback()
        return 500, f"创建车次失败：{str(e)}", None


def get_train_single(db: Session, query: TrainSingleQuery) -> Tuple[int, str, Optional[Train]]:
    """单条车次查询（支持多字段筛选）"""
    try:
        # 校验至少一个查询条件
        query_fields = [query.train_id, query.train_no, query.train_code, query.from_station, query.to_station]
        if not any(query_fields):
            return 400, "必须指定至少一个查询条件", None

        # 构建查询
        db_query = db.query(Train)
        if query.train_id:
            db_query = db_query.filter(Train.train_id == query.train_id)
        if query.train_no:
            db_query = db_query.filter(Train.train_no == query.train_no)
        if query.train_code:
            db_query = db_query.filter(Train.train_code == query.train_code)
        if query.from_station:
            db_query = db_query.filter(Train.from_station == query.from_station)
        if query.to_station:
            db_query = db_query.filter(Train.to_station == query.to_station)

        train = db_query.first()
        if not train:
            return 404, "未找到符合条件的车次", None
        return 200, "查询成功", train
    except Exception as e:
        return 500, f"查询车次失败：{str(e)}", None


def get_train_list(db: Session, query: TrainListQuery) -> Tuple[int, str, Dict[str, Any]]:
    """车次列表查询（筛选+分页，支持车站名称模糊匹配）"""
    try:
        db_query = db.query(Train)

        # 筛选条件
        if query.train_code:
            db_query = db_query.filter(Train.train_code.ilike(f"%{query.train_code}%"))
        if query.train_type:
            db_query = db_query.filter(Train.train_type == query.train_type)

        # 出发站筛选（支持电报码或名称模糊匹配）
        if query.from_station:
            # 关联车站表，支持名称模糊匹配
            db_query = db_query.join(
                Station, Train.from_station == Station.telecode
            ).filter(
                or_(
                    Train.from_station == query.from_station,
                    Station.station_name.ilike(f"%{query.from_station}%")
                )
            ).distinct()  # 去重

        # 到达站筛选（同理）
        if query.to_station:
            db_query = db_query.join(
                Station, Train.to_station == Station.telecode
            ).filter(
                or_(
                    Train.to_station == query.to_station,
                    Station.station_name.ilike(f"%{query.to_station}%")
                )
            ).distinct()

        # 分页
        total = db_query.count()
        offset = (query.page - 1) * query.page_size
        trains = db_query.order_by(Train.train_code.asc()).offset(offset).limit(query.page_size).all()

        # 构造返回数据（可选：补充车站名称）
        train_list = []
        for train in trains:
            # 转换为字典，添加车站名称
            train_dict = train.__dict__.copy()
            from_station = db.query(Station).filter(Station.telecode == train.from_station).first()
            to_station = db.query(Station).filter(Station.telecode == train.to_station).first()
            train_dict["departure_station_name"] = from_station.station_name if from_station else None
            train_dict["arrival_station_name"] = to_station.station_name if to_station else None
            train_list.append(train_dict)

        data = {
            "total": total,
            "page": query.page,
            "page_size": query.page_size,
            "total_page": (total + query.page_size - 1) // query.page_size,
            "list": train_list
        }
        return 200, "车次列表查询成功", data
    except Exception as e:
        return 500, f"查询车次列表失败：{str(e)}", {
            "total": 0,
            "page": query.page,
            "page_size": query.page_size,
            "total_page": 0,
            "list": []
        }


def delete_train(db: Session, train_no: str) -> Tuple[int, str]:
    """删除车次（受运行计划外键约束，需先删除运行计划或解除关联）"""
    try:
        train = db.query(Train).filter(Train.train_no == train_no).first()
        if not train:
            return 404, "未找到车次"

        db.delete(train)
        db.commit()
        return 200, "车次已删除"
    except IntegrityError:
        db.rollback()
        return 400, "该车次关联运行计划，无法直接删除（请先删除运行计划）"
    except Exception as e:
        db.rollback()
        return 500, f"删除车次失败：{str(e)}"


# ------------------------------ 时刻表 CRUD ------------------------------
def create_train_schedule_batch(db: Session, batch_create: TrainScheduleBatchCreate) -> Tuple[
    int, str, Optional[List[TrainSchedule]]]:
    """批量创建时刻表（一个运行计划对应多个站点）"""
    try:
        train_no = batch_create.schedules[0].train_no
        # 校验关联的运行计划是否存在
        operation_plan = db.query(TrainOperationPlan).filter(TrainOperationPlan.train_no == train_no).first()
        if not operation_plan:
            return 404, f"关联的运行计划（train_no={train_no}）不存在", None

        # 校验所有车站是否存在
        station_telecodes = [item.station_telecode for item in batch_create.schedules]
        stations = db.query(Station).filter(Station.telecode.in_(station_telecodes)).all()
        existing_telecodes = {station.telecode for station in stations}
        missing_telecodes = set(station_telecodes) - existing_telecodes
        if missing_telecodes:
            return 404, f"以下车站不存在：{','.join(missing_telecodes)}", None

        # 先删除该运行计划已有的时刻表（避免重复）
        db.query(TrainSchedule).filter(TrainSchedule.train_no == train_no).delete()

        # 批量创建
        schedules = [TrainSchedule(**item.dict()) for item in batch_create.schedules]
        db.add_all(schedules)
        db.commit()

        # 刷新运行计划的车站数（同步更新）
        operation_plan.station_num = len(schedules)
        # 同步全程里程和总运行时间（取自到达站的累计值）
        arrival_schedule = next(item for item in schedules if item.is_arrival == 1)
        operation_plan.total_mileage = arrival_schedule.accumulated_mileage
        operation_plan.total_running_time = arrival_schedule.running_time
        db.commit()

        return 201, f"批量创建{len(schedules)}条时刻表成功", schedules
    except IntegrityError:
        db.rollback()
        return 409, "时刻表唯一约束冲突（同一运行计划下车站或顺序重复）", None
    except Exception as e:
        db.rollback()
        return 500, f"批量创建时刻表失败：{str(e)}", None


def get_train_schedule_single(db: Session, query: TrainScheduleSingleQuery) -> Tuple[int, str, Optional[TrainSchedule]]:
    """单条时刻表查询"""
    try:
        query_fields = [query.schedule_id, query.train_no, query.station_telecode, query.sequence]
        if not any(query_fields):
            return 400, "必须指定至少一个查询条件", None

        db_query = db.query(TrainSchedule)
        if query.schedule_id:
            db_query = db_query.filter(TrainSchedule.schedule_id == query.schedule_id)
        if query.train_no:
            db_query = db_query.filter(TrainSchedule.train_no == query.train_no)
        if query.station_telecode:
            db_query = db_query.filter(TrainSchedule.station_telecode == query.station_telecode)
        if query.sequence:
            db_query = db_query.filter(TrainSchedule.sequence == query.sequence)

        schedule = db_query.first()
        if not schedule:
            return 404, "未找到符合条件的时刻表", None
        return 200, "查询成功", schedule
    except Exception as e:
        return 500, f"查询时刻表失败：{str(e)}", None


def get_train_schedule_list(db: Session, query: TrainScheduleListQuery) -> Tuple[int, str, Dict[str, Any]]:
    """时刻表列表查询（筛选+分页）"""
    try:
        db_query = db.query(TrainSchedule)

        # 筛选条件
        if query.train_no:
            db_query = db_query.filter(TrainSchedule.train_no==query.train_no)
        if query.train_code:
            train_no = db.query(Train.train_no).filter(Train.train_code==query.train_code).first()
            if not train_no:
                return 404, f"关联的运行计划（train_code={query.train_code}）不存在", None
            db_query = db_query.filter(TrainSchedule.train_no==train_no[0])
        if query.station_telecode:
            db_query = db_query.filter(TrainSchedule.station_telecode == query.station_telecode)
        if query.station_name:
            db_query = db_query.filter(TrainSchedule.station_name.ilike(f"%{query.station_name}%"))
        if query.is_departure is not None:
            db_query = db_query.filter(TrainSchedule.is_departure == query.is_departure)
        if query.is_arrival is not None:
            db_query = db_query.filter(TrainSchedule.is_arrival == query.is_arrival)

        # 分页
        total = db_query.count()
        offset = (query.page - 1) * query.page_size
        schedules = db_query.order_by(TrainSchedule.train_no.asc(), TrainSchedule.sequence.asc()).offset(offset).limit(
            query.page_size).all()

        # 构造返回数据（可选：补充车站详情）
        schedule_list = []
        for schedule in schedules:
            schedule_dict = schedule.__dict__.copy()
            station = db.query(Station).filter(Station.telecode == schedule.station_telecode).first()
            if station:
                schedule_dict["station_detail"] = {
                    "province": station.province,
                    "city": station.city,
                    "is_high_speed": station.is_high_speed
                }
            schedule_list.append(schedule_dict)

        data = {
            "total": total,
            "page": query.page,
            "page_size": query.page_size,
            "total_page": (total + query.page_size - 1) // query.page_size,
            "list": schedule_list
        }
        return 200, "时刻表列表查询成功", data
    except Exception as e:
        return 500, f"查询时刻表列表失败：{str(e)}", {
            "total": 0,
            "page": query.page,
            "page_size": query.page_size,
            "total_page": 0,
            "list": []
        }


def get_train_full_schedule(db: Session, train_no: str) -> Tuple[int, str, Optional[List[TrainSchedule]]]:
    """获取某车次的完整时刻表（按顺序排序）"""
    try:
        # 先校验运行计划是否存在
        operation_plan = db.query(TrainOperationPlan).filter(TrainOperationPlan.train_no == train_no).first()
        if not operation_plan:
            return 404, f"车次{train_no}的运行计划不存在", None

        # 查询该车次的所有时刻表并按顺序排序
        schedules = db.query(TrainSchedule).filter(TrainSchedule.train_no == train_no).order_by(
            TrainSchedule.sequence.asc()).all()
        if not schedules:
            return 404, f"车次{train_no}未配置时刻表", None

        return 200, f"获取车次{train_no}完整时刻表成功（共{len(schedules)}站）", schedules
    except Exception as e:
        return 500, f"获取完整时刻表失败：{str(e)}", None


def delete_train_schedule(db: Session, train_no: str, station_telecode: Optional[str] = None) -> Tuple[int, str]:
    """删除时刻表（支持删除某车次的全部或单个站点）"""
    try:
        db_query = db.query(TrainSchedule).filter(TrainSchedule.train_no == train_no)
        if station_telecode:
            db_query = db_query.filter(TrainSchedule.station_telecode == station_telecode)

        count = db_query.count()
        if count == 0:
            return 404, "未找到符合条件的时刻表"

        db_query.delete()
        db.commit()

        # 同步更新运行计划的车站数
        remaining_schedules = db.query(TrainSchedule).filter(TrainSchedule.train_no == train_no).count()
        operation_plan = db.query(TrainOperationPlan).filter(TrainOperationPlan.train_no == train_no).first()
        if operation_plan:
            operation_plan.station_num = remaining_schedules
            # 若还有剩余站点，更新全程里程和总运行时间
            if remaining_schedules >= 2:
                arrival_schedule = db.query(TrainSchedule).filter(
                    TrainSchedule.train_no == train_no,
                    TrainSchedule.is_arrival == 1
                ).first()
                if arrival_schedule:
                    operation_plan.total_mileage = arrival_schedule.accumulated_mileage
                    operation_plan.total_running_time = arrival_schedule.running_time
            db.commit()

        return 200, f"成功删除{count}条时刻表"
    except Exception as e:
        db.rollback()
        return 500, f"删除时刻表失败：{str(e)}"

def get_train_no_by_train_code(db: Session, train_code: str) -> Optional[Train]:
    """根据 train_code 查询对应的 train_no"""
    trains = db.query(Train).filter(Train.train_code == train_code).all()
    return trains

def check_operation_plan_valid(
    db: Session, train_code:str, train_no: str, query_date: date
) -> Tuple[int, str, Optional[TrainOperationPlan]]:
    """校验运行计划在查询日期是否有效"""
    try:
        # 1. 查询该 train_no 的有效运行计划（状态正常）
        plan = db.query(TrainOperationPlan).filter(
            TrainOperationPlan.train_no == train_no,
            TrainOperationPlan.status == 1,
            TrainOperationPlan.start_date <= query_date,
            or_(
                TrainOperationPlan.end_date.is_(None),
                TrainOperationPlan.end_date >= query_date
            )
        ).first()

        if not plan:
            return 404, f"车次{train_no}在{query_date}无有效运行计划", None

        # 2. 校验开行规律
        query_date_weekday = query_date.weekday()  # 0=周一，6=周日
        run_rule = plan.run_rule
        custom_run_days = plan.custom_run_days or []

        # 转换 query_date 为字符串格式（匹配 custom_run_days）
        query_date_str = query_date.strftime("%Y-%m-%d")

        # 校验逻辑
        if run_rule == 0:  # 每日开行
            pass  # 直接通过
        elif run_rule == 1:  # 工作日（周一到周五）
            if query_date_weekday >= 5:
                return 400, f"车次{train_code}仅工作日开行，{query_date}为周末", None
        elif run_rule == 2:  # 周末（周六、周日）
            if query_date_weekday < 5:
                return 400, f"车次{train_code}仅周末开行，{query_date}为工作日", None
        elif run_rule == 3:  # 单日开行（暂按自定义逻辑，实际需根据业务调整）
            if query_date_str not in custom_run_days:
                return 400, f"车次{train_code}仅指定日期开行，{query_date}不在开行范围内", None
        elif run_rule == 4:  # 双日开行（暂按自定义逻辑）
            if query_date_str not in custom_run_days:
                return 400, f"车次{train_code}仅双日开行，{query_date}不在开行范围内", None
        elif run_rule == 5:  # 自定义开行
            if query_date_str not in custom_run_days:
                return 400, f"车次{train_code}自定义开行日期为{custom_run_days}，{query_date}不在范围内", None
        return 200, "运行计划有效", plan
    except Exception as e:
        return 500, f"校验运行计划失败：{str(e)}", None

def get_schedule_by_train_code_and_date(
    db: Session, train_code: str, query_date: date
) -> Tuple[int, str, Optional[List[TrainSchedule]]]:
    """根据 train_code 和日期查询时刻表"""
    try:
        # 1. 根据 train_code 找 train_no
        trains = get_train_no_by_train_code(db, train_code)
        if not trains:
            return 404, f"未找到车次{train_code}", None
        for train in trains:
            train_no = train.train_no
            # 2. 校验运行计划是否有效
            code, msg, plan = check_operation_plan_valid(db, train_code, train_no, query_date)
            if code != 200:
                continue
                # return code, msg, None
            # 3. 查询完整时刻表（按顺序排序）
            schedules = db.query(TrainSchedule).filter(
                TrainSchedule.train_no == train_no
            ).order_by(TrainSchedule.sequence.asc()).all()

            if not schedules:
                return 404, f"车次{train_code}在{query_date}无配置时刻表", None

            return 200, f"成功获取车次{train_code}（{query_date}）的时刻表（共{len(schedules)}站）", schedules
        return 404, f"车次{train_code}在{query_date}无有效运行计划", None
    except SQLAlchemyError as e:
        return 500, f"数据库查询失败：{str(e)}", None
    except Exception as e:
        return 500, f"查询时刻表失败：{str(e)}", None
