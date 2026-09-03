from typing import List, Dict, Optional, Any
from uuid import UUID
from datetime import datetime
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db.models.task import Task, TaskStatus, TaskType, DEFAULT_PRIORITIES, CATEGORY_DESCRIPTION_MAP, \
    CATEGORY_NAME_MAP, INTERACTIVE_TASK_PRIORITY

DEFAULT_SCAN_STATUS = {
    'running': False,
    'progress': 0.0,
    'added': 0,
    'deleted': 0,
    'errors': 0,
    'current_task': None,
    'message': 'Idle',
    'total_files': 0,
    'processed_files': 0,
    'classified': 0
}


def list_tasks(db: Session, status: Optional[str] = None, type: Optional[str] = None, limit: int = 50, updated_since: Optional[str] = None) -> List[Task]:
    """List tasks, optionally filtered by status / type / updated_since.

    ``updated_since`` is an ISO 8601 string; rows whose ``updated_at`` is
    strictly later than that timestamp are returned. This powers the SSE
    catch-up flow on the frontend.
    """
    query = db.query(Task).order_by(Task.created_at.desc())
    if status:
        query = query.filter(Task.status == status)
    if type:
        query = query.filter(Task.type == type)
    if updated_since:
        try:
            ts = datetime.fromisoformat(updated_since.replace("Z", "+00:00"))
            query = query.filter(Task.updated_at > ts)
        except Exception:
            # Silently ignore unparseable timestamps so the endpoint still
            # works for clients that have a bad clock.
            pass
    return query.limit(limit).all()

def get_task(db: Session, task_id: UUID) -> Optional[Task]:
    return db.query(Task).filter(Task.id == task_id).first()

def get_tasks_by_ids(db: Session, task_ids: List[UUID]) -> List[Task]:
    return db.query(Task).filter(Task.id.in_(task_ids)).all()

def count_tasks_by_status(db: Session, status: str) -> int:
    return db.query(Task).filter(Task.status == status).count()

def count_dispatchable_tasks(db: Session, paused_types: set = None) -> int:
    """Count unfinished tasks that the worker is allowed to dispatch.

    Used by the worker watchdog to decide whether to restart a dead worker:
    if the only unfinished work belongs to paused categories, the worker's
    idle-exit was intentional and should not be overridden. Interactive tasks
    are still dispatchable because category pause only controls the automatic
    processing pipeline.
    """
    q = db.query(Task).filter(Task.status.in_([TaskStatus.PENDING, TaskStatus.PROCESSING]))
    if paused_types:
        q = q.filter(or_(
            Task.type.notin_(list(paused_types)),
            Task.priority >= INTERACTIVE_TASK_PRIORITY,
        ))
    return q.count()

def get_tasks_by_status(db: Session, status: str) -> List[Task]:
    return db.query(Task).filter(Task.status == status).all()

def delete_tasks_by_ids(db: Session, task_ids: List[UUID]) -> int:
    return db.query(Task).filter(Task.id.in_(task_ids)).delete(synchronize_session=False)

def get_task_by_id_and_owner(db: Session, task_id: UUID, owner_id: UUID) -> Optional[Task]:
    return db.query(Task).filter(Task.id == task_id, Task.owner_id == owner_id).first()

def get_latest_task_by_type_and_owner(db: Session, task_type: str, owner_id: UUID, statuses: List[str]) -> Optional[Task]:
    return db.query(Task).filter(
        Task.type == task_type,
        Task.owner_id == owner_id,
        Task.status.in_(statuses)
    ).order_by(Task.created_at.desc()).first()

def delete_task(db: Session, task: Task) -> None:
    db.delete(task)
    db.commit()

def get_grouped_status(db: Session, paused_categories: set) -> List[Dict[str, Any]]:
    from sqlalchemy import func
    stats = []
    categories = [
        TaskType.PROCESS_BASIC, TaskType.EXTRACT_METADATA,
        TaskType.RECOGNIZE_FACE, TaskType.CLUSTER_FACES, TaskType.RECOGNIZE_TICKET,
        TaskType.CLASSIFY_IMAGE, TaskType.VISUAL_DESCRIPTION,
        TaskType.OCR, TaskType.IMAGE_EMBEDDING, TaskType.GENERATE_THUMBNAIL
    ]

    try:
        # Optimize: query all pending/processing counts in one go
        pending_counts = db.query(
            Task.type, func.count(Task.id)
        ).filter(
            Task.status.in_([TaskStatus.PENDING, TaskStatus.PROCESSING]),
            Task.type.in_(categories)
        ).group_by(Task.type).all()
        pending_map = {row[0]: row[1] for row in pending_counts}

        # Optimize: query all failed counts in one go
        failed_counts = db.query(
            Task.type, func.count(Task.id)
        ).filter(
            Task.status == TaskStatus.FAILED,
            Task.type.in_(categories)
        ).group_by(Task.type).all()
        failed_map = {row[0]: row[1] for row in failed_counts}
    except Exception as e:
        # If session was closed (e.g. by cancelled request), return empty to avoid ResourceClosedError crash
        return []

    for cat in categories:
        pending = pending_map.get(cat, 0)
        completed = 0
        failed = failed_map.get(cat, 0)

        stats.append({
            'task_name': CATEGORY_NAME_MAP.get(cat, cat),
            'category': cat,
            'pending': pending,
            'completed': completed,
            'failed': failed,
            'status': 'paused' if cat in paused_categories else 'active',
            'priority': DEFAULT_PRIORITIES.get(cat, 0),
            'description': CATEGORY_DESCRIPTION_MAP.get(cat, '')
        })

    stats.sort(key=lambda x: x['priority'], reverse=True)
    return stats

def add_task(db: Session, type: str, payload: dict, priority: Optional[int] = None, owner_id: Optional[UUID] = None) -> Task:
    # Callers may override the type's default priority for genuinely urgent
    # work (for example an action explicitly started from the photo viewer).
    # ``None`` keeps the historical default-priority behaviour.
    if priority is None:
        priority = DEFAULT_PRIORITIES.get(type, 0)
    task = Task(type=type, payload=payload, priority=priority, status=TaskStatus.PENDING, owner_id=owner_id)
    db.add(task)
    db.commit()
    db.refresh(task)
    return task

def add_tasks(db: Session, tasks_data: List[Dict], owner_id: Optional[UUID] = None) -> None:
    if not tasks_data:
        return

    tasks = []
    for t_data in tasks_data:
        priority = DEFAULT_PRIORITIES.get(t_data['type'], 0)

        task_owner_id = t_data.get('owner_id', owner_id)

        tasks.append(Task(
            type=t_data['type'],
            payload=t_data.get('payload', {}),
            priority=priority,
            status=TaskStatus.PENDING,
            owner_id=task_owner_id
        ))

    db.bulk_save_objects(tasks)
    db.commit()

def cancel_task(db: Session, task: Task) -> Task:
    task.status = TaskStatus.CANCELLED
    db.commit()
    db.refresh(task)
    return task

def retry_task(db: Session, task: Task) -> Task:
    task.status = TaskStatus.PENDING
    task.error = None
    task.attempt_count = 0
    task.next_retry_at = None
    task.updated_at = datetime.now()
    db.commit()
    db.refresh(task)
    return task

def retry_all_failed_tasks(db: Session, types: Optional[List[str]] = None) -> int:
    query = db.query(Task).filter(Task.status == TaskStatus.FAILED)
    if types:
        query = query.filter(Task.type.in_(types))

    result = query.update({
        Task.status: TaskStatus.PENDING,
        Task.error: None,
        Task.attempt_count: 0,
        Task.next_retry_at: None,
        Task.updated_at: datetime.now()
    }, synchronize_session=False)
    
    db.commit()
    return result

def delete_failed_tasks(db: Session, types: Optional[List[str]] = None) -> int:
    query = db.query(Task).filter(Task.status == TaskStatus.FAILED)
    if types:
        query = query.filter(Task.type.in_(types))

    count = query.delete(synchronize_session=False)
    db.commit()
    return count
