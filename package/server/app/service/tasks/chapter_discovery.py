"""Persisted, owner-scoped discovery of life chapter suggestions."""

import asyncio
import time
from uuid import UUID

from app.db.models.task import Task, TaskType
from app.db.session import SessionLocal
from app.service import chapter
from app.service.task_strategy import BaseTaskStrategy, TaskStrategyFactory


def discover_in_session(owner_id: UUID) -> dict:
    started = time.perf_counter()
    db = SessionLocal()
    try:
        rows = chapter.discover(db, owner_id)
        return {"created": len(rows), "chapter_ids": [str(row.id) for row in rows],
                "duration_ms": round((time.perf_counter() - started) * 1000)}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@TaskStrategyFactory.register(TaskType.DISCOVER_CHAPTERS)
class ChapterDiscoveryStrategy(BaseTaskStrategy):
    @property
    def task_category(self) -> str:
        return "CPU"

    @property
    def resource_key(self) -> str:
        return "chapter_discovery"

    @property
    def timeout(self) -> int:
        return 60 * 30

    async def process(self, worker, task: Task, db) -> dict:
        if task.owner_id is None:
            raise ValueError("章节发现任务缺少所有者")
        # The scan is synchronous SQL work. Give it its own session in the
        # executor so large libraries do not block the worker event loop.
        return await asyncio.get_running_loop().run_in_executor(
            None, discover_in_session, task.owner_id)
