#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
@Time        : 2025/11/18 21:02
@Author      : SiYuan
@Email       : sixyuan044@gmail.com
@File        : server-init_db.py
@Description : 
"""

from railway.db.session import engine
from railway.db.base import Base


def init_models():
    Base.metadata.create_all(bind=engine)
    from railway.db.migrations import upgrade_railway_schema
    upgrade_railway_schema(engine)
    print("✅ 数据库初始化完成")

if __name__ == "__main__":
    init_models()


