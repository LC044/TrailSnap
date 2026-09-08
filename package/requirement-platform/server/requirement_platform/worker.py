import os
import time
from datetime import datetime, timedelta, timezone

from .config import settings
from .db import SessionLocal, init_db
from .models import BackgroundJob
from .services import analyze_requirement, retry_at, sync_batch_milestone, sync_requirement_issue


HANDLERS = {
    "triage": analyze_requirement,
    "github_issue": sync_requirement_issue,
    "github_milestone": sync_batch_milestone,
}


def claim_job(db):
    now = datetime.now(timezone.utc)
    row = db.query(BackgroundJob).filter(
        BackgroundJob.available_at <= now,
        ((BackgroundJob.status == "queued") | ((BackgroundJob.status == "running") & (BackgroundJob.lease_expires_at < now))),
    ).order_by(BackgroundJob.created_at).first()
    if not row:
        return None
    row.status = "running"
    row.attempts += 1
    row.lease_expires_at = now + timedelta(minutes=15)
    db.commit()
    return row.id


def run_job(job_id: str) -> None:
    db = SessionLocal()
    try:
        job = db.query(BackgroundJob).filter(BackgroundJob.id == job_id).first()
        if not job:
            return
        handler = HANDLERS.get(job.job_type)
        if not handler:
            raise RuntimeError(f"Unknown job type: {job.job_type}")
        handler(db, job.object_id)
        job = db.query(BackgroundJob).filter(BackgroundJob.id == job_id).first()
        job.status = "completed"
        job.lease_expires_at = None
        job.last_error = None
        db.commit()
    except Exception as exc:
        db.rollback()
        job = db.query(BackgroundJob).filter(BackgroundJob.id == job_id).first()
        if job:
            job.last_error = str(exc)[:4000]
            job.lease_expires_at = None
            if job.attempts >= settings.max_job_attempts:
                job.status = "failed"
            else:
                job.status = "queued"
                job.available_at = retry_at(job.attempts)
            db.commit()
    finally:
        db.close()


def main() -> None:
    init_db()
    once = os.getenv("RP_WORKER_ONCE", "").lower() in {"1", "true", "yes"}
    while True:
        db = SessionLocal()
        try:
            job_id = claim_job(db)
        finally:
            db.close()
        if job_id:
            run_job(job_id)
        elif once:
            return
        else:
            time.sleep(settings.worker_poll_seconds)


if __name__ == "__main__":
    main()
