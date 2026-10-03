"""Daily-frame video generation in the persistent task worker."""

import asyncio
from uuid import UUID

from app.db.models.task import TaskType
from app.service.daily_frame_render import RenderCancelled, render_work
from app.service.task_strategy import BaseTaskStrategy, TaskStrategyFactory


@TaskStrategyFactory.register(TaskType.RENDER_DAILY_FRAME)
class DailyFrameRenderStrategy(BaseTaskStrategy):
    @property
    def task_category(self) -> str:
        return "CPU"

    @property
    def resource_key(self) -> str:
        return "daily_frame_render"

    @property
    def timeout(self) -> int:
        return 4 * 60 * 60

    @property
    def max_attempts(self) -> int:
        return 1

    async def process(self, worker, task, db):
        return await asyncio.to_thread(render_work, UUID(task.payload["work_id"]), task.payload["generation"], task.id)

    async def process_batch(self, worker, tasks, db):
        results = []
        for task in tasks:
            item = {"task_id": task.id, "task_type": task.type}
            try:
                item.update(status="completed", result=await self.process(worker, task, db))
            except RenderCancelled:
                item.update(status="cancelled", result={})
            except Exception:
                # User-facing date-specific error is persisted on the work.
                item.update(status="failed", error="影片生成失败，请查看作品详情")
            results.append(item)
        return results
