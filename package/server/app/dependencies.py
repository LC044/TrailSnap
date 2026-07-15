#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
@Time        : 2025/5/10 22:31 
@Author      : SiYuan 
@Email       : sixyuan044@gmail.com 
@File        : server-dependencies.py 
@Description : 
"""

from typing import List, Optional, Generic, TypeVar
from pydantic import BaseModel, Field

from app.db.session import SessionLocal, engine

# Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# 定义泛型类型（支持不同业务数据类型）
T = TypeVar("T")

# ------------------------------ 通用响应模型（统一错误码载体）------------------------------
class BaseResponse(BaseModel, Generic[T]):
    """所有接口的统一响应模型：包含错误码、提示信息、业务数据"""
    code: int = Field(default=0, description="错误码：0=成功")
    msg: str = Field(default="success", description="提示信息")
    data: Optional[T] = Field(default=None, description="业务数据（成功时返回，失败时为None）")

    class Config:
        from_attributes = True  # 支持从 ORM 模型直接转换

    @classmethod
    def success(cls, data: Optional[T] = None, msg: str = "success") -> "BaseResponse[T]":
        return cls(code=0, msg=msg, data=data)

    @classmethod
    def fail(cls, code: int = 500, msg: str = "error", data: Optional[T] = None) -> "BaseResponse[T]":
        return cls(code=code, msg=msg, data=data)