#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
@Time        : 2025/5/9 23:45 
@Author      : SiYuan 
@Email       : sixyuan044@gmail.com 
@File        : TrailSnap-session.py 
@Description : 
"""
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.environ.get('TS_DB_URL') or os.environ.get('DB_URL')
if not DATABASE_URL:
    raise ValueError("DB_URL or TS_DB_URL environment variable is not set")

engine = create_engine(
    DATABASE_URL,
    pool_size=10,  # 先保留默认，后续再调
    max_overflow=50,
    pool_timeout=30,
    pool_recycle=1800,  # 定期回收空闲连接（避免失效连接）
    pool_pre_ping=True,  # 关键：每次从池子里拿连接前，先执行SELECT 1校验连接有效性
    # ===== psycopg2驱动参数 =====
    connect_args={
        "connect_timeout": 10,  # PG连接超时（秒）
        "keepalives": 1,        # 开启TCP保活
        "keepalives_idle": 60,  # 60秒无数据则发送保活包
        "keepalives_interval": 10,  # 保活包发送间隔
    }
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

