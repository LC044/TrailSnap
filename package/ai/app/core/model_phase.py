"""Coordinate model residency for a complete inference request, including streams."""
import asyncio
import logging
from contextlib import asynccontextmanager

from app.config import settings


class ModelPhaseCoordinator:
    def __init__(self, prepare):
        self.prepare = prepare
        self.condition = asyncio.Condition()
        self.family = None
        self.active = 0

    @asynccontextmanager
    async def slot(self, family):
        async with self.condition:
            await self.condition.wait_for(lambda: self.active == 0 or self.family == family)
            if self.family != family:
                # A cancellation must not let another family load while release
                # is still executing in the background thread.
                preparation = asyncio.create_task(self.prepare(family))
                try:
                    await asyncio.shield(preparation)
                except asyncio.CancelledError:
                    await preparation
                    raise
                logging.info('AI model phase switched: previous=%s current=%s', self.family, family)
                self.family = family
            self.active += 1
        try:
            yield
        finally:
            async with self.condition:
                self.active -= 1
                self.condition.notify_all()


async def prepare_family(family):
    from app.services.model_manager import model_manager
    from app.services.llm_manager import llm_manager
    if family != 'llm':
        await llm_manager.stop()
    await asyncio.to_thread(model_manager.release_except, family)


class ModelPhaseMiddleware:
    def __init__(self, app):
        self.app = app
        self.coordinator = ModelPhaseCoordinator(prepare_family)

    async def __call__(self, scope, receive, send):
        prefix = scope.get('path', '').strip('/').split('/')[0]
        family = {'classification': 'classification', 'face': 'face',
                  'embedding': 'embedding', 'ocr': 'ocr', 'tickets': 'tickets',
                  'v1': 'llm'}.get(prefix)
        if (scope['type'] != 'http' or scope.get('method') != 'POST'
                or family is None or not settings.AI_SINGLE_MODEL_FAMILY):
            await self.app(scope, receive, send)
            return
        # ASGI lifetime includes the final body chunk. BaseHTTPMiddleware's
        # call_next returns before a streaming LLM response has finished.
        async with self.coordinator.slot(family):
            request = asyncio.create_task(self.app(scope, receive, send))
            try:
                await asyncio.shield(request)
            except asyncio.CancelledError:
                # Cancelling an executor future does not stop native inference.
                # Drain the request before permitting another model to unload it.
                while not request.done():
                    try:
                        await asyncio.shield(request)
                    except asyncio.CancelledError:
                        continue
                    except Exception:
                        break
                if request.done() and not request.cancelled():
                    request.exception()
                raise
