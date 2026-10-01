"""Shared photo-to-task expansion for AI strategies."""

from typing import Callable

from sqlalchemy.orm import Session

from app.db.models.photo import FileType, Photo
from app.db.models.task import Task, TaskType


def generate_photo_tasks(
    db: Session,
    worker,
    task: Task,
    *,
    task_type: TaskType,
    status_key: str,
    priority: int,
    budget: int | None = None,
    eligible: Callable[[Photo], bool] | None = None,
    batch_size: int = 1000,
) -> int:
    """Expand a generator task without loading the whole library at once."""
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    if budget is not None and budget <= 0:
        return 0
    force = (task.payload or {}).get("force", False)
    generated = 0
    last_id = None
    while True:
        query = db.query(Photo).filter(Photo.is_deleted.is_(False))
        if task.owner_id:
            query = query.filter(Photo.owner_id == task.owner_id)
        if last_id is not None:
            query = query.filter(Photo.id > last_id)
        batch = query.order_by(Photo.id).limit(batch_size).all()
        if not batch:
            break
        # Capture the cursor before add_tasks commits and expires ORM objects.
        last_id = batch[-1].id

        entries = []
        for photo in batch:
            if photo.file_type == FileType.video or (eligible and not eligible(photo)):
                continue
            if not force and (photo.processed_tasks or {}).get(status_key):
                continue
            if budget is not None and generated + len(entries) >= budget:
                break
            entries.append({
                "type": task_type,
                "payload": {
                    "photo_id": str(photo.id), "force": force, "file_path": photo.file_path,
                },
                "priority": priority,
                "owner_id": photo.owner_id,
            })
        if entries:
            worker.add_tasks(db, entries)
            generated += len(entries)
        if budget is not None and generated >= budget:
            break
    return generated
