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
    annual_report, auth, deps, agent, agent_token, toolbox, metadata, nav
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

    # Start Worker Process if there are pending tasks
    # We can just check if we need to start it, or simply start it once and it will exit if idle
    # TaskManager.get_instance().start_worker_if_needed()
    # Wait, when the app starts, we might have unfinished tasks. Let's start the worker just in case.
    mgr = TaskManager.get_instance()
    # Attach the running loop so cross-thread SSE publishes can be scheduled
    # onto the loop thread via call_soon_threadsafe (asyncio.Queue is not
    # thread-safe).
    mgr.attach_loop(asyncio.get_running_loop())
    mgr.start_worker_if_needed()
    mgr.start_scheduler()
    # Watchdog restarts the worker if it dies with unfinished work left.
    mgr.start_watchdog()

    yield

    # Stop Worker Process
    mgr.stop_watchdog()
    mgr.stop_scheduler()
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

# 添加 GZip 中间件
exclude_paths = ['/ai_communication/AiCommunicationThemesRecord/chat']
app.add_middleware(
    CustomGZipMiddleware,
    minimum_size=1000,
    compresslevel=9,
    exclude_paths=exclude_paths,
    exclude_exact={'/tasks/events'},
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
