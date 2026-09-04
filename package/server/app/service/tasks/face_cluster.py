"""Standalone face-clustering task.

Clustering used to run inline at the end of every ``RECOGNIZE_FACE`` batch.
That was wrong for three independent reasons, all of which showed up together
on a NAS deployment as "recognition is slow, the AI container is idle, and the
server container burns 90%+ CPU":

1. ``resource_key == 'face'`` is limited to 1 concurrent slot (2 on
   medium/high). The slot is held for the whole of ``process_batch``, so a
   multi-minute clustering pass inside it stopped every further recognition
   batch from being dispatched at all.
2. ``process_unassigned_faces`` is synchronous CPU work. Called from a
   coroutine it blocks the worker's event loop, freezing the producer loop,
   the other two consumers and SSE progress. ``asyncio.wait_for`` cannot
   interrupt it either, so the batch timeout was ineffective.
3. It ran once per batch (previously once per photo), repeating the same
   whole-library O(n^2) DBSCAN pass over and over during a large import.

Splitting it out fixes all three: clustering now runs on the CPU queue under
its own resource key, off the event loop, and at most once per import round.
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models.task import Task, TaskStatus, TaskType
from app.service.task_strategy import BaseTaskStrategy, TaskStrategyFactory

logger = logging.getLogger(__name__)

# How long to wait before re-checking whether recognition has finished.
DEFER_SECONDS = 60


def enqueue_cluster_faces(db: Session, owner_id) -> Optional[Task]:
    """Register at most one outstanding clustering task per owner.

    Called from ``RecognizeFaceStrategy.handle_completion``. Reusing an
    existing PENDING/PROCESSING row is what collapses a whole import round
    into a single clustering pass.
    """
    if owner_id is None:
        return None

    from app.crud import task as crud_task

    existing = crud_task.get_latest_task_by_type_and_owner(
        db,
        TaskType.CLUSTER_FACES,
        owner_id,
        [TaskStatus.PENDING, TaskStatus.PROCESSING],
    )
    if existing:
        return existing

    return crud_task.add_task(
        db,
        TaskType.CLUSTER_FACES,
        {'owner_id': str(owner_id)},
        owner_id=owner_id,
    )


def _cluster_in_thread(owner_id: UUID) -> None:
    """Run the clustering pass with its own Session.

    A ``Session`` is not thread-safe, so the caller's session must not be
    reused here. This function is the executor payload; keep it free of any
    ORM object that came from another thread.
    """
    from app.db.session import SessionLocal
    from app.service.face_cluster import FaceClusterService

    db = SessionLocal()
    try:
        FaceClusterService(db, owner_id).process_unassigned_faces(owner_id)
    finally:
        db.close()


@TaskStrategyFactory.register(TaskType.CLUSTER_FACES)
class ClusterFacesStrategy(BaseTaskStrategy):
    @property
    def task_category(self) -> str:
        return 'CPU'

    @property
    def resource_key(self) -> str:
        # Deliberately not 'face': sharing the recognition key would recreate
        # the stall this task type exists to remove.
        return 'face_cluster'

    @property
    def timeout(self) -> int:
        # A whole-library DBSCAN pass on a six-figure library takes far longer
        # than the 5 minute default. Timing out here would also be counted as
        # a transient failure and retried, burning the same CPU three times.
        return 60 * 60

    async def process(self, worker, task: Task, db: Session) -> Optional[Dict[str, Any]]:
        owner_id = task.owner_id
        if owner_id is None:
            return {'status': 'skipped', 'reason': 'missing owner_id'}

        if self._recognition_in_flight(db, owner_id):
            self._defer(db, task)
            logger.info(
                "Deferring face clustering for owner %s: recognition still running",
                owner_id,
            )
            return None

        loop = asyncio.get_running_loop()
        # ``None`` uses the loop's default executor on purpose.
        # ``worker.thread_pool`` is torn down by ``_manage_pool_lifecycle``
        # whenever no IO task is active, which could kill a running pass.
        await loop.run_in_executor(None, _cluster_in_thread, owner_id)
        return {'status': 'success'}

    async def process_batch(self, worker, tasks: List[Task], db: Session) -> List[Dict]:
        results = []
        for task in tasks:
            try:
                res = await self.process(worker, task, db)
            except Exception as exc:
                logger.error("Face clustering task %s failed: %s", task.id, exc, exc_info=True)
                results.append({
                    'task_id': task.id,
                    'task_type': task.type,
                    'status': 'failed',
                    'error': str(exc),
                })
                continue

            if res is None:
                # Deferred. The row is back to PENDING with next_retry_at set;
                # omitting it from ``results`` is what keeps _flush_results
                # from treating it as completed and deleting it. Returning
                # something like {'status': 'deferred'} would silently drop
                # the task and clustering would never happen.
                continue

            results.append({
                'task_id': task.id,
                'task_type': task.type,
                'status': 'completed',
                'result': res,
            })
        return results

    @staticmethod
    def _recognition_in_flight(db: Session, owner_id) -> bool:
        return db.query(Task.id).filter(
            Task.type == TaskType.RECOGNIZE_FACE,
            Task.owner_id == owner_id,
            Task.status.in_([TaskStatus.PENDING, TaskStatus.PROCESSING]),
        ).first() is not None

    @staticmethod
    def _defer(db: Session, task: Task) -> None:
        task.status = TaskStatus.PENDING
        task.next_retry_at = datetime.now() + timedelta(seconds=DEFER_SECONDS)
        task.error = None
        # attempt_count is intentionally left alone: waiting for recognition is
        # not a failed attempt, and a long import would otherwise exhaust
        # max_attempts and mark clustering FAILED.
        db.commit()

    def release_resources(self) -> None:
        pass
