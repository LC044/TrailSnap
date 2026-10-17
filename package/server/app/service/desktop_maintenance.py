"""Quiesce the desktop sidecar before an offline directory migration."""
import asyncio
import os

from starlette.responses import JSONResponse


class DesktopMaintenance:
    def __init__(self):
        self.draining = False
        self.active = 0
        self.ai_draining = False
        self.ai_active = 0

    async def middleware(self, scope, receive, send, app):
        path = scope.get("path", "").removeprefix("/api")
        if scope["type"] == "http" and os.getenv("TS_DESKTOP_VERIFY") == "1" and path not in {"/health-check", "/system/desktop/runtime"}:
            response = JSONResponse({"code": 503, "msg": "正在验证更新，暂未开放图库", "data": None}, status_code=503)
            return await response(scope, receive, send)
        if scope["type"] != "http" or path in {"/system/desktop/prepare-migration", "/system/desktop/ai-extension"}:
            return await app(scope, receive, send)
        ai_request = path.startswith(("/faces", "/search", "/train-ticket", "/flight-ticket", "/settings/ai-models", "/settings/verify-ai-service"))
        if ai_request and self.ai_draining:
            response = JSONResponse(
                {"code": 503, "msg": "ai_extension_wait=maintenance 等待 AI 扩展更新", "data": None},
                status_code=503,
            )
            return await response(scope, receive, send)
        if self.draining:
            response = JSONResponse(
                {"code": 503, "msg": "数据目录迁移准备中，请在重启完成后重试", "data": None},
                status_code=503, headers={"Retry-After": "30"},
            )
            return await response(scope, receive, send)
        # SSE subscriptions do not write data and otherwise never finish.
        tracked = path not in {"/tasks/events", "/notifications/events"}
        if tracked:
            self.active += 1
        if ai_request:
            self.ai_active += 1
        try:
            await app(scope, receive, send)
        finally:
            if tracked:
                self.active -= 1
            if ai_request:
                self.ai_active -= 1

    async def prepare(self, scheduler, manager):
        # Set this synchronously on the ASGI loop before accepting another request.
        self.draining = True
        await asyncio.to_thread(scheduler.stop, wait=True)
        while self.active:
            await asyncio.sleep(0.1)
        from railway.initialization import wait_for_initialization
        await asyncio.to_thread(wait_for_initialization)
        await asyncio.to_thread(manager.drain_for_migration)


maintenance = DesktopMaintenance()


class DesktopMaintenanceMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        await maintenance.middleware(scope, receive, send, self.app)
