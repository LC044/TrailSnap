#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Asynchronous recycle-bin purge jobs.

Emptying a recycle bin holding thousands of photos is inherently slow: every
photo means index writes across a dozen child tables plus an ``unlink`` on the
original file and up to five thumbnail variants. Even with the bulk-SQL rewrite
in :func:`app.crud.photo.batch_delete_photos_db` this can run for tens of
seconds, which is far longer than a browser (or a reverse proxy) is willing to
keep an HTTP request open.

So the API hands the work to a background thread and returns a ``job_id``
immediately. The client polls for progress and stays responsive the whole time.

Design notes:

* One worker thread per job, capped by ``_MAX_CONCURRENT_JOBS`` so a user cannot
  spawn unbounded threads by spamming the endpoint.
* Each job owns its own ``SessionLocal()``. Sharing the request-scoped session
  would blow up as soon as FastAPI returns and closes it.
* Job state lives in memory. A purge is not a business record worth persisting:
  if the server restarts mid-purge the already-committed chunks are gone for
  good (which is what the user asked for) and the remainder simply stays in the
  bin, where the nightly retention job will pick it up.
* Finished jobs are reaped after ``_JOB_TTL_SECONDS`` so the registry cannot
  grow without bound.
"""

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from uuid import UUID

logger = logging.getLogger("app.service.recycle_bin_purge")

# Beyond this many photos the API prefers an async job over a blocking response.
# 200 photos complete well inside a normal request budget after the bulk rewrite.
ASYNC_PURGE_THRESHOLD = 200

_MAX_CONCURRENT_JOBS = 4
_JOB_TTL_SECONDS = 30 * 60


@dataclass
class PurgeJob:
    """Progress record for a single background purge."""

    id: str
    user_id: str
    total: int
    processed: int = 0
    deleted: int = 0
    status: str = "pending"  # pending | running | completed | failed
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None

    def to_dict(self) -> dict:
        # `progress` is precomputed so every client renders the same number.
        progress = 100 if self.status == "completed" else (
            int(self.processed * 100 / self.total) if self.total else 0
        )
        return {
            "job_id": self.id,
            "status": self.status,
            "total": self.total,
            "processed": self.processed,
            "deleted": self.deleted,
            "progress": progress,
            "error": self.error,
        }


_jobs: Dict[str, PurgeJob] = {}
_lock = threading.Lock()


def _reap_expired_locked() -> None:
    """Drop finished jobs older than the TTL. Caller must hold ``_lock``."""
    cutoff = time.time() - _JOB_TTL_SECONDS
    for job_id in [
        jid
        for jid, job in _jobs.items()
        if job.finished_at is not None and job.finished_at < cutoff
    ]:
        _jobs.pop(job_id, None)


def active_job_for_user(user_id: UUID) -> Optional[PurgeJob]:
    """Return the user's in-flight purge, if any.

    Lets the API reject a second purge instead of racing two workers over the
    same rows (the second would mostly no-op, but it would also double the
    write-lock pressure for no benefit).
    """
    with _lock:
        for job in _jobs.values():
            if job.user_id == str(user_id) and job.status in ("pending", "running"):
                return job
    return None


def get_job(job_id: str, user_id: UUID) -> Optional[PurgeJob]:
    """Look up a job, scoped to its owner so ids are not cross-readable."""
    with _lock:
        job = _jobs.get(job_id)
        if job is None or job.user_id != str(user_id):
            return None
        return job


def _run_job(job_id: str, user_id: UUID, photo_ids: List[UUID]) -> None:
    from app.crud.photo import batch_delete_photos_db
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        with _lock:
            job = _jobs.get(job_id)
            if job:
                job.status = "running"

        def on_progress(processed: int, total: int) -> None:
            with _lock:
                tracked = _jobs.get(job_id)
                if tracked:
                    tracked.processed = processed

        deleted = batch_delete_photos_db(
            db,
            photo_ids,
            is_delete_file=True,
            user_id=user_id,
            progress_cb=on_progress,
        )

        with _lock:
            job = _jobs.get(job_id)
            if job:
                job.deleted = deleted
                job.processed = job.total
                job.status = "completed"
                job.finished_at = time.time()
        logger.info(
            "recycle-bin purge %s finished: %s/%s photos deleted",
            job_id, deleted, len(photo_ids),
        )
    except Exception as exc:  # noqa: BLE001 - background thread must never crash the app
        db.rollback()
        logger.exception("recycle-bin purge %s failed", job_id)
        with _lock:
            job = _jobs.get(job_id)
            if job:
                job.status = "failed"
                job.error = str(exc)
                job.finished_at = time.time()
    finally:
        db.close()


def start_purge_job(user_id: UUID, photo_ids: List[UUID]) -> PurgeJob:
    """Queue a purge of ``photo_ids`` and return its progress record.

    Raises ``RuntimeError`` when the concurrency cap is reached, so the caller
    can translate it into a 429 rather than silently dropping the request.
    """
    job_id = str(uuid.uuid4())
    job = PurgeJob(id=job_id, user_id=str(user_id), total=len(photo_ids))

    with _lock:
        _reap_expired_locked()
        running = sum(1 for j in _jobs.values() if j.status in ("pending", "running"))
        if running >= _MAX_CONCURRENT_JOBS:
            raise RuntimeError("Too many purge jobs are already running")
        _jobs[job_id] = job

    thread = threading.Thread(
        target=_run_job,
        args=(job_id, user_id, photo_ids),
        name=f"recycle-purge-{job_id[:8]}",
        daemon=True,
    )
    thread.start()
    return job
