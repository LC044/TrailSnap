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

Once per import round is still too often for a library that grows a few photos
at a time, so an auto-enqueued pass also has to justify itself: it runs when
the unassigned pool has grown by ``MIN_NEW_UNASSIGNED`` since the last
completed pass, or when that pass is older than ``MAX_SKIP_AGE``. A task
created by hand through ``POST /tasks/`` carries no ``payload['auto']`` and is
never throttled, so an explicit "re-cluster now" always runs.
"""
import asyncio
import json
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.models.face import Face
from app.db.models.photo import Photo
from app.db.models.system import SystemState
from app.db.models.task import Task, TaskStatus, TaskType
from app.service.task_strategy import BaseTaskStrategy, TaskStrategyFactory

logger = logging.getLogger(__name__)

# How long to wait before re-checking whether recognition has finished.
DEFER_SECONDS = 60


def _int_env(name: str, default: int, minimum: int) -> int:
    try:
        return max(minimum, int(os.environ.get(name, default)))
    except (TypeError, ValueError):
        return default


# A pass re-clusters the owner's whole unassigned pool, so importing a handful
# of photos should not trigger one. The throttle compares against the pool the
# last completed pass left behind: those faces were already examined and came
# out as noise, so only the growth since then carries new information.
MIN_NEW_UNASSIGNED = _int_env("TS_FACE_CLUSTER_MIN_NEW_FACES", 10, 1)

# No threshold is lossless -- a single new face can bridge four previously
# isolated ones into a cluster -- so the increment check alone would let a
# library that stops just short of the threshold go unclustered forever. This
# bounds that to one day.
MAX_SKIP_AGE = timedelta(hours=_int_env("TS_FACE_CLUSTER_MAX_SKIP_HOURS", 24, 1))

_BASELINE_KEY_PREFIX = "face_cluster_baseline:"


def _baseline_key(owner_id) -> str:
    return f"{_BASELINE_KEY_PREFIX}{owner_id}"


def count_unassigned_faces(db: Session, owner_id) -> int:
    """Size of the pool a clustering pass would operate on.

    Mirrors the candidate select in ``FaceClusterService._cluster_unassigned_faces``;
    the two must agree or the throttle would be measuring a different set than
    the one that gets clustered.
    """
    query = db.query(func.count(Face.id)).filter(
        Face.face_identity_id.is_(None),
        Face.is_deleted.is_(False),
        Face.face_feature.isnot(None),
    )
    if owner_id:
        query = query.filter(
            Face.photo_id.in_(
                db.query(Photo.id).filter(
                    Photo.owner_id == owner_id,
                    Photo.is_deleted.is_(False),
                )
            )
        )
    return query.scalar() or 0


def _load_baseline(db: Session, owner_id) -> Tuple[Optional[int], Optional[datetime]]:
    row = db.query(SystemState).filter(SystemState.key == _baseline_key(owner_id)).first()
    if not row or not row.value:
        return None, None
    try:
        payload = json.loads(row.value)
        return int(payload["unassigned"]), datetime.fromisoformat(payload["at"])
    except (TypeError, ValueError, KeyError):
        # A hand-edited or older-format row must not wedge clustering; treat it
        # as "never clustered" and let the next pass rewrite it.
        return None, None


def record_baseline(db: Session, owner_id, unassigned: int) -> None:
    """Anchor the throttle to the pool size left behind by a completed pass."""
    key = _baseline_key(owner_id)
    value = json.dumps({"unassigned": int(unassigned), "at": datetime.now().isoformat()})
    row = db.query(SystemState).filter(SystemState.key == key).first()
    if row:
        row.value = value
    else:
        db.add(SystemState(key=key, value=value))
    db.commit()


def should_cluster(db: Session, owner_id) -> Tuple[bool, str]:
    """Whether enough has changed since the last pass to justify another one."""
    baseline, recorded_at = _load_baseline(db, owner_id)
    if baseline is None:
        return True, "no completed pass on record"

    if recorded_at is None or datetime.now() - recorded_at >= MAX_SKIP_AGE:
        return True, f"last pass was at {recorded_at}"

    current = count_unassigned_faces(db, owner_id)
    # Faces deleted or assigned by hand since the last pass can push the pool
    # below the baseline. Clamping keeps the delta meaningful without a write;
    # MAX_SKIP_AGE is what eventually re-anchors it.
    new_faces = max(0, current - baseline)
    if new_faces >= MIN_NEW_UNASSIGNED:
        return True, f"{new_faces} new unassigned faces"
    return False, f"only {new_faces} new unassigned faces since the last pass"


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
        # 'auto' marks this as pipeline-generated, which is what subjects it to
        # the throttle. A row a user creates through POST /tasks/ carries no
        # such flag and always runs.
        {'owner_id': str(owner_id), 'auto': True},
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
        # Anchor the throttle to what this pass leaves behind rather than to
        # what it started with: the leftovers are noise this pass already
        # examined, so they are not new information next time. Written from
        # this session, after the pass, so a failed pass keeps the old
        # baseline and the next round retries.
        record_baseline(db, owner_id, count_unassigned_faces(db, owner_id))
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

        if (task.payload or {}).get('auto'):
            # Only auto-enqueued passes are throttled. ``POST /tasks/`` lets a
            # user create a CLUSTER_FACES row by hand, and an explicitly
            # requested re-cluster must never be silently skipped.
            try:
                proceed, reason = should_cluster(db, owner_id)
            except SQLAlchemyError as exc:
                # The throttle is an optimisation. If its bookkeeping is
                # broken, cluster anyway rather than silently stop producing
                # people.
                db.rollback()
                logger.warning("Face clustering throttle unavailable: %s", exc)
                proceed, reason = True, "throttle unavailable"
            if not proceed:
                logger.info(
                    "Skipping face clustering for owner %s: %s", owner_id, reason
                )
                return {'status': 'skipped', 'reason': reason}

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
