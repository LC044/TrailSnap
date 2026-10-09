#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
@Time        : 2025/11/20 20:05
@Author      : SiYuan
@Email       : sixyuan044@gmail.com
@File        : server-build_database.py
@Description : 
"""
import sys
from typing import Dict, Type, List, Optional
import csv
import os
from datetime import datetime, date, time

from sqlalchemy import text, make_url, create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from railway.db.models.models import (
    Base, Station, Train, TrainOperationPlan, TrainSchedule
)
from railway.db.dependencies import init_db
from railway.db.session import SessionLocal, engine

# 配置：表名到模型类的映射（关键映射，确保字段匹配）
TABLE_MODEL_MAPPING: Dict[str, Type[Base]] = {
    'station': Station,
    'train': Train,
    'train_operation_plan': TrainOperationPlan,
    'train_schedule': TrainSchedule
}

# CSV文件路径配置
tables = ['station', 'train_operation_plan', 'train', 'train_schedule']
source_dir = os.path.join(os.path.dirname(__file__), 'source')

def convert_value(value: str, field_type: Optional[type] = None) -> Optional[any]:
    """
    转换CSV字符串值为对应的数据类型
    Args:
        value: CSV中的原始字符串值
        field_type: 模型字段的目标类型（可选）
    Returns:
        转换后的值（None表示空值）
    """
    # 处理空值
    if value.strip() == '' or value.lower() in ['null', 'none']:
        return None
    # 根据目标类型转换（如果指定）
    if field_type:
        try:
            if field_type == int:
                return int(value)
            elif field_type == float:
                return float(value)
            elif field_type == bool:
                return value.lower() in ['true', '1', 'yes']
            elif field_type == time:
                try:
                    # 支持 "HH:MM" 或 "HH:MM:SS" 格式的字符串
                    if len(value.strip()) == 5:  # 如 "08:30"
                        return datetime.strptime(value.strip(), "%H:%M").time()
                    else:  # 如 "08:30:00"
                        return datetime.strptime(value.strip(), "%H:%M:%S").time()
                except ValueError:
                    raise ValueError(f"无法将 '{value}' 转换为时间格式（支持 HH:MM 或 HH:MM:SS）")
            elif field_type == date:
                # 支持常见的日期时间格式
                for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%H:%M:%S']:
                    try:
                        return datetime.strptime(value, fmt)
                    except ValueError:
                        continue
                raise ValueError(f"无法解析日期时间格式: {value}")
        except (ValueError, TypeError):
            # 转换失败时返回原始字符串（由SQLAlchemy自动尝试转换）
            return value

    # 自动推断简单类型
    try:
        return int(value)
    except ValueError:
        try:
            return float(value)
        except ValueError:
            # 字符串类型直接返回
            return value

def sync_sequence(db: Session, table_name: str, pk_column: str):
    """同步自增序列到表中最大主键值"""
    try:
        # 序列名默认是：表名_主键列名_seq
        sequence_name = f"{table_name}_{pk_column}_seq"
        sql = f"""
            SELECT setval(
                '{sequence_name}',
                (SELECT COALESCE(MAX({pk_column}), 0) FROM {table_name})
            );
        """
        db.execute(text(sql))
        db.commit()
        print(f"✅ 同步序列 {sequence_name} 成功")
    except Exception as e:
        print(f"❌ 同步序列 {sequence_name} 失败：{str(e)}")
        db.rollback()

def read_csv_to_db(db: Session, table_name: str, model_class: Type[Base]):
    """
    读取CSV文件并批量插入到对应的数据库表中（使用原生csv模块）

    Args:
        db: 数据库会话
        table_name: 表名（对应CSV文件名）
        model_class: 对应的SQLAlchemy模型类
    """
    csv_file = f'{source_dir}/{table_name}.csv'
    print(f"开始处理文件: {csv_file}")

    # 检查文件是否存在
    if not os.path.exists(csv_file):
        raise FileNotFoundError(csv_file)

    try:
        # 读取CSV文件（使用DictReader按列名读取）
        with open(csv_file, 'r', encoding='utf-8-sig', newline='') as f:
            # 获取CSV列名（第一行）
            reader = csv.DictReader(f)
            csv_columns = reader.fieldnames or []

            # 获取模型字段名（排除SQLAlchemy内置字段）
            model_fields = [col for col in model_class.__dict__
                            if not col.startswith('_') and
                            not callable(getattr(model_class, col))]

            # 筛选出CSV和模型共有的字段
            common_fields = [col for col in csv_columns if col in model_fields]

            if not common_fields:
                raise ValueError(f"CSV has no matching fields: {csv_file}")

            # 读取并转换数据
            model_instances: List[Base] = []
            row_count = 0

            for row in reader:
                row_count += 1
                model_data = {}

                for field in common_fields:
                    # 获取CSV原始值
                    raw_value = row.get(field, '').strip()

                    # 获取模型字段的类型（如果有）
                    field_attr = getattr(model_class, field, None)
                    field_type = None
                    if field_attr and hasattr(field_attr, 'type'):
                        field_type = field_attr.type.python_type

                    # 转换值
                    model_data[field] = convert_value(raw_value, field_type)

                # 创建模型实例
                instance = model_class(**model_data)
                model_instances.append(instance)

            print(f"成功读取CSV，共 {row_count} 条数据，有效字段 {common_fields}")

            if not model_instances:
                print(f"警告：{csv_file} 中没有有效数据，跳过插入")
                return

            # 批量插入数据库（提高效率）
            batch_size = 1000  # 每批插入1000条数据
            total = len(model_instances)
            inserted = 0

            for i in range(0, total, batch_size):
                batch = model_instances[i:i + batch_size]
                primary_key = list(model_class.__table__.primary_key.columns)[0]
                existing = {row[0] for row in db.query(primary_key).filter(
                    primary_key.in_([getattr(item, primary_key.key) for item in batch])
                ).all()}
                batch = [item for item in batch if getattr(item, primary_key.key) not in existing]
                db.add_all(batch)
                db.flush()  # 刷新到数据库，但不提交事务
                inserted += len(batch)
                print(f"已插入 {inserted}/{total} 条数据")

            # 提交事务
            db.commit()
            print(f"✅ 成功插入 {total} 条数据到表 {table_name}")

    except UnicodeDecodeError:
        print(f"错误：文件 {csv_file} 编码错误，请检查编码格式（当前使用utf-8-sig）")
        db.rollback()
        raise
    except SQLAlchemyError as e:
        print(f"❌ 数据库错误：插入表 {table_name} 失败 - {str(e)}")
        db.rollback()
        raise
    except Exception as e:
        print(f"❌ 未知错误：处理表 {table_name} 失败 - {str(e)}")
        db.rollback()
        raise
# ------------------------------ 核心：按表名同步序列（失败跳过） ------------------------------
def sync_table_sequence(db: Session, table_name: str) -> None:
    """
    按单个表名同步序列（PostgreSQL默认规则）
    逻辑：表名 → 找模型主键列 → 生成序列名（表名_主键列名_seq）→ 同步序列 → 失败跳过
    """
    if db.get_bind().dialect.name != 'postgresql':
        return
    print(f"\n📌 开始同步表 [{table_name}] 的序列...")

    try:
        # 1. 验证表是否有对应模型
        if table_name not in TABLE_MODEL_MAPPING:
            print(f"⚠️  表 {table_name} 无对应模型 → 跳过")
            return

        model_class = TABLE_MODEL_MAPPING[table_name]

        # 2. 提取模型的主键列（默认单个主键）
        primary_keys = list(model_class.__table__.primary_key.columns.keys())
        if not primary_keys:
            print(f"⚠️  表 {table_name} 无主键列 → 跳过")
            return
        pk_column = primary_keys[0]  # 取第一个主键列（绝大多数场景适用）

        # 3. 生成PostgreSQL默认序列名（表名_主键列名_seq）
        sequence_name = f"{table_name}_{pk_column}_seq"

        # 4. 执行同步：查询主键最大值 → 设置序列
        try:
            # 查主键列最大值（无数据则设为0，避免序列从1开始冲突）
            get_max_sql = text(f"SELECT COALESCE(MAX({pk_column}), 0) AS max_id FROM {table_name};")
            max_id = db.execute(get_max_sql).scalar()

            # 同步序列（setval：将序列当前值设为max_id，后续插入从max_id+1开始）
            sync_sql = text(f"SELECT setval(:seq_name, :max_id);")
            db.execute(sync_sql, {"seq_name": sequence_name, "max_id": max_id})
            db.commit()

            print(f"✅ 表 [{table_name}] 同步成功：序列 [{sequence_name}] → 最大值 [{max_id}]")

        except SQLAlchemyError as e:
            db.rollback()
            print(f"❌ 表 [{table_name}] 同步失败（数据库错误）：{str(e)} → 跳过")
            raise
        except Exception as e:
            db.rollback()
            print(f"❌ 表 [{table_name}] 同步失败（未知错误）：{str(e)} → 跳过")
            raise

    except Exception as e:
        print(f"❌ 表 [{table_name}] 处理异常：{str(e)} → 跳过")
        raise
def build_database(db:Session):
    """主函数：批量处理所有CSV文件"""
    try:
        # 按顺序处理表（注意依赖关系：先插入基础表，再插入关联表）
        # 推荐顺序：station -> train -> train_operation_plan -> train_schedule
        processing_order = ['station', 'train_operation_plan','train' , 'train_schedule']

        for table_name in processing_order:
            if table_name not in TABLE_MODEL_MAPPING:
                print(f"⚠️  警告：表 {table_name} 没有对应的模型类，跳过")
                continue

            model_class = TABLE_MODEL_MAPPING[table_name]
            read_csv_to_db(db, table_name, model_class)
            sync_table_sequence(db, table_name)
        # sync_sequence(db, "train_schedule", "schedule_id")
        print("\n🎉 所有CSV文件处理完成！")

    finally:
        # 关闭数据库连接
        db.close()
        print("数据库连接已关闭")

def drop_tables_by_order():
    # 按反向依赖顺序（先删关联表，再删基础表）
    drop_order = [
        'train_schedule',  # 依赖 train 和 station
        'train',  #
        'train_operation_plan',  # 基础表
        'station'  # 基础表
        # 可根据你的实际模型添加其他表名
    ]

    try:
        with SessionLocal() as db:
            connection = db.connection()
            db_type = connection.dialect.name

            # 禁用外键
            if db_type == 'mysql':
                connection.execute(text("SET FOREIGN_KEY_CHECKS = 0;"))

            # 按顺序删除
            for table_name in drop_order:
                if table_name in Base.metadata.tables:
                    table = Base.metadata.tables[table_name]
                    table.drop(bind=engine, checkfirst=True)
                    print(f"✅ 已删除表：{table_name}")
            # 恢复外键
            if db_type == 'mysql':
                connection.execute(text("SET FOREIGN_KEY_CHECKS = 1;"))
        print("🎉 所有表按顺序删除完成！")
    except Exception as e:
        print(f"❌ 删除失败：{str(e)}")

def rebuild_database():
    db = SessionLocal()
    drop_tables_by_order()
    init_db()
    build_database(db)

if __name__ == '__main__':
    rebuild_database()
