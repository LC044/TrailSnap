#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
@Time        : 2025/11/25 19:48
@Author      : SiYuan
@Email       : sixyuan044@gmail.com
@File        : server-main.py
@Description : 
"""
from fastapi import FastAPI
from contextlib import asynccontextmanager

from railway import api

# 初始化 FastAPI 应用
@asynccontextmanager
async def lifespan(app: FastAPI):
    from railway.initialization import start_background_initialization
    start_background_initialization()
    yield


app = FastAPI(title="12306 车次信息 API", description="基于 FastAPI+PostgreSQL+SQLAlchemy 的铁路车次信息管理接口", version="1.0.0", lifespan=lifespan)

# 示例接口
@app.get("/")
def root():
    return {"message": "Image Manager Backend Ready"}


app.include_router(api.router, prefix="/railway", tags=["railway"])

if __name__ == "__main__":
    import uvicorn
    # http://127.0.0.1:8005/docs
    uvicorn.run(app, host="0.0.0.0", port=8005)
