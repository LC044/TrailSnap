#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
@Time        : 2025/10/14 20:38
@Author      : SiYuan
@Email       : sixyuan044@gmail.com
@File        : TrailSnapAPI-main.py
@Description :
"""
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware, GZipResponder
from fastapi import FastAPI, Request
from contextlib import asynccontextmanager
import asyncio
import os
import logging
import time
from dotenv import load_dotenv
from starlette.datastructures import Headers
from starlette.types import Receive, Scope, Send

if not os.path.exists('./data'):
    os.mkdir('./data')
load_dotenv('./data/.env')

from app.api import (
    user, train_ticket, flight_ticket, album, index, settings, face, ocr,
    location, location_stats, search, classification, system, media, stats, photo, tasks,
    annual_report, auth, deps, agent, agent_token, toolbox, metadata, nav, guess_city, storage,
    notification
)
from railway.api import router as railway_router
from app.db.session import engine, SessionLocal
from app.core.logger import setup_logging
from app.core.config_manager import VERSION
from app.service.task_manager import TaskManager

@asynccontextmanager
async def lifespan(app: FastAPI):
    global log_listener
    log_listener = setup_logging('api')

    mgr = TaskManager.get_instance()
    # Attach the running loop so cross-thread SSE publishes can be scheduled
    # onto the loop thread via call_soon_threadsafe (asyncio.Queue is not
    # thread-safe).
    mgr.attach_loop(asyncio.get_running_loop())
    mgr.start_worker_if_needed()
    # Watchdog restarts the worker if it dies with unfinished work left.
    mgr.start_watchdog()

    # 通用通知通道：task.* 事件会桥接到此，前端一条 SSE 收两类事件。
    from app.service.notification_manager import NotificationManager
    NotificationManager.get_instance().attach_loop(asyncio.get_running_loop())

    # 统一后台任务调度：扫描 / 回收站清理 / 版本更新检查
    # 全部交给 APScheduler 单线程按 cron / interval 触发，替代原先
    # TaskManager._scheduler_loop 和 UpdateCheckScheduler 各自的守护线程。
    from app.core.system_config import system_config
    from app.service.scheduler import JobScheduler
    from app.service.jobs.scan_folder import scan_folder_job
    from app.service.jobs.recycle_bin_cleanup import recycle_bin_cleanup_job
    from app.service.jobs.update_check import update_check_job

    job_scheduler = JobScheduler()
    job_scheduler.register_cron_job(
        "scan_folder",
        system_config.config.scan_schedule.to_cron_expression(),
        scan_folder_job,
    )
    # recycle_bin.cleanup_time "HH:MM" -> cron "M H * * *"
    cleanup_cron = None
    try:
        hh, mm = system_config.config.recycle_bin.cleanup_time.split(":")
        cleanup_cron = f"{int(mm)} {int(hh)} * * *"
    except Exception:
        pass
    job_scheduler.register_cron_job("recycle_bin_cleanup", cleanup_cron, recycle_bin_cleanup_job)
    # 服务启动后立即跑一次版本检查（去重键保证同一版本不会重复推送），
    # 之后每 6 小时再触发一次。
    from datetime import datetime
    job_scheduler.register_interval_job("update_check", 6 * 3600, update_check_job, next_run_time=datetime.now())
    job_scheduler.start()

    yield

    job_scheduler.stop()

    # Stop Worker Process
    mgr.stop_watchdog()
    mgr.stop_worker()

    if log_listener:
        log_listener.stop()

app = FastAPI(
    title="TrailSnap - 足迹相册",
    lifespan=lifespan,
    version=VERSION,
    swagger_ui_parameters={"persistAuthorization": True}
)
# Initialize logging listener
log_listener = None

# @app.middleware("http")
async def log_requests(request: Request, call_next):
    # 2. 判断当前请求是否在排除列表中，若是则直接处理请求，不记录日志
    if request.url.path.startswith('/medias'):
        response = await call_next(request)
        return response
    start_time = time.time()
    operation = f"{request.method} {request.url.path}"
    params = dict(request.query_params)
    try:
        response = await call_next(request)
        process_time = (time.time() - start_time) * 1000
        extra = {
            "operation": operation,
            "params": params,
            "result": response.status_code,
            "duration_ms": f"{process_time:.2f}"
        }
        logging.getLogger("app.middleware").info("Request processed", extra=extra)
        return response
    except Exception as e:
        process_time = (time.time() - start_time) * 1000
        extra = {
            "operation": operation,
            "params": params,
            "result": "Error",
            "duration_ms": f"{process_time:.2f}"
        }
        logging.getLogger("app.middleware").error(f"Request failed: {str(e)}", exc_info=e, extra=extra)
        raise e

# 自定义 GZip 中间件
class CustomGZipMiddleware(GZipMiddleware):
    def __init__(
        self, app, minimum_size: int = 500, compresslevel: int = 9,
        exclude_paths=None, exclude_exact=None,
    ) -> None:
        super().__init__(app, minimum_size, compresslevel)
        self.exclude_paths = exclude_paths or []
        self.exclude_exact = set(exclude_exact or [])

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            headers = Headers(scope=scope)
            request = Request(scope, receive)
            path = request.url.path
            if (
                "gzip" in headers.get("Accept-Encoding", "")
                and path not in self.exclude_exact
                and not any(path.endswith(suffix) for suffix in self.exclude_paths)
            ):
                responder = GZipResponder(
                    self.app, self.minimum_size, compresslevel=self.compresslevel
                )
                await responder(scope, receive, send)
                return
        await self.app(scope, receive, send)

import json
from starlette.responses import Response, StreamingResponse

class FieldsFilterMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        fields_query = request.query_params.get("fields")
        
        if not fields_query or request.method != "GET":
            await self.app(scope, receive, send)
            return
            
        fields = set(f.strip() for f in fields_query.split(",") if f.strip())
        if not fields:
            await self.app(scope, receive, send)
            return

        # Intercept send to modify the response body
        async def custom_send(message: dict) -> None:
            if message["type"] == "http.response.start":
                # Remove content-length as we will modify the body
                headers = []
                for name, value in message.get("headers", []):
                    if name.lower() != b"content-length":
                        headers.append((name, value))
                message["headers"] = headers
                await send(message)
            elif message["type"] == "http.response.body":
                body = message.get("body", b"")
                if body:
                    try:
                        data = json.loads(body.decode("utf-8"))
                        if isinstance(data, dict) and "data" in data:
                            target = data["data"]
                            if isinstance(target, list):
                                for item in target:
                                    if isinstance(item, dict):
                                        keys_to_remove = set(item.keys()) - fields
                                        for k in keys_to_remove:
                                            item.pop(k, None)
                            elif isinstance(target, dict):
                                keys_to_remove = set(target.keys()) - fields
                                for k in keys_to_remove:
                                    target.pop(k, None)
                        body = json.dumps(data).encode("utf-8")
                    except Exception:
                        pass
                message["body"] = body
                await send(message)
            else:
                await send(message)

        await self.app(scope, receive, custom_send)

# 演示模式中间件（最内层）：DEMO_MODE=true 时拦截写操作 + 脱敏敏感配置。
# 放在最内层的原因：CORS 在最外层，保证 403 响应也带 CORS 头；
# GZip 在外层，保证脱敏时拿到的是未压缩 JSON。
from app.middleware.demo_mode import DemoModeMiddleware
app.add_middleware(DemoModeMiddleware)

app.add_middleware(FieldsFilterMiddleware)

# 添加 GZip 中间件
exclude_paths = ['/ai_communication/AiCommunicationThemesRecord/chat']
app.add_middleware(
    CustomGZipMiddleware,
    minimum_size=1000,
    compresslevel=9,
    exclude_paths=exclude_paths,
    exclude_exact={'/tasks/events', '/notifications/events'},
)

# 配置允许跨域的源（生产环境建议指定具体域名，不要用 "*"）
origins = [
    "*"
]

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # 允许的源
    allow_credentials=True,  # 允许携带Cookie
    allow_methods=["*"],     # 允许所有HTTP方法
    allow_headers=["*"],     # 允许所有请求头
)

# 示例接口
@app.get("/")
def root():
    return {"message": "Image Manager Backend Ready"}

@app.get("/health-check", tags=["System"])
def health_check():
    """
    健康检测接口
    """
    return {"status": "ok", "message": "Service is running"}

app.include_router(auth.router, prefix="/auth", tags=["Auth"])
app.include_router(agent_token.router, prefix="/tokens", tags=["Tokens"])
app.include_router(user.router, prefix="/users", tags=["Users"])
app.include_router(train_ticket.router, prefix="/train-ticket", tags=["train-ticket"])
app.include_router(flight_ticket.router, prefix="/flight-ticket", tags=["flight-ticket"])
app.include_router(railway_router, prefix="/railway", tags=["railway"])
app.include_router(photo.router, prefix="/photos", tags=["Photos"])
app.include_router(metadata.router, prefix="/metadata", tags=["Metadata"])
app.include_router(album.router,prefix="/albums", tags=["Albums"])
app.include_router(settings.router, prefix="/settings", tags=["Settings"])
app.include_router(index.router, prefix="/index", tags=["Index"])
app.include_router(media.router, prefix="/medias", tags=["Media"])
app.include_router(stats.router, prefix="/stats", tags=["Stats"])
app.include_router(tasks.router, prefix="/tasks", tags=["Tasks"])
app.include_router(notification.router, prefix="/notifications", tags=["Notifications"])
app.include_router(toolbox.router, prefix="/toolbox", tags=["Toolbox"])
app.include_router(face.router, prefix="/faces", tags=["Faces"])
app.include_router(ocr.router, prefix="/ocr", tags=["OCR"])
app.include_router(location.router, prefix="/locations", tags=["Locations"])
app.include_router(location_stats.router, prefix="/location-stats", tags=["LocationStats"])
app.include_router(search.router, prefix="/search", tags=["Search"])
app.include_router(classification.router, prefix="/tags", tags=["Classification"])
app.include_router(annual_report.router, prefix="/annual-report", tags=["AnnualReport"])
app.include_router(system.router, prefix="/system", tags=["System"])
app.include_router(agent.router, prefix="/agent", tags=["Agent"])
app.include_router(nav.router, prefix="/nav", tags=["Nav"])
app.include_router(guess_city.router, prefix="/guess-city", tags=["GuessCity"])
app.include_router(storage.router, prefix="/storage", tags=["Storage"])

from fastapi.openapi.utils import get_openapi

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title="TrailSnap - 足迹相册",
        version=VERSION,
        description="Image Manager Backend API",
        routes=app.routes,
    )
    # Define the security scheme
    openapi_schema["components"]["securitySchemes"] = {
        "OAuth2PasswordBearer": {
            "type": "oauth2",
            "flows": {
                "password": {
                    "scopes": {},
                    "tokenUrl": "/auth/login",
                }
            }
        }
    }
    # Apply it globally
    openapi_schema["security"] = [{"OAuth2PasswordBearer": []}]
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi

if __name__ == "__main__":
    import uvicorn
    # http://127.0.0.1:8000/docs
    uvicorn.run(app, host="0.0.0.0", port=8000, timeout_keep_alive=60)
