"""Quiesce the desktop sidecar before an offline directory migration."""
import asyncio

from starlette.responses import JSONResponse


class DesktopMaintenance:
    def __init__(self):
        self.draining = False
        self.active = 0

    async def middleware(self, scope, receive, send, app):
        path = scope.get("path", "").removeprefix("/api")
        if scope["type"] != "http" or path == "/system/desktop/prepare-migration":
            return await app(scope, receive, send)
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
        try:
            await app(scope, receive, send)
        finally:
            if tracked:
                self.active -= 1

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
