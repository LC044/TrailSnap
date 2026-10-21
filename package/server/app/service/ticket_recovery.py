"""Explicit recovery of legacy ticket jobs incorrectly recorded as complete."""
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models.photo import Photo, FileType
from app.db.models.task import Task, TaskType, TaskStatus, DEFAULT_PRIORITIES
from app.db.models.trip import TrainTicket, FlightTicket


def recover_ticket_recognition(db: Session, manager: Any, owner_id: UUID) -> int:
    """Only enqueue legacy, owned, live photos with no saved ticket or retryable job.

    Version 2 empty recognition results are intentional and must not be recovered.
    Existing failed jobs remain available through the normal retry action.
    """
    count = 0
    last_id = None
    while True:
        from app.service.tasks.ai_runtime import AIBatchSession
        if isinstance(db, AIBatchSession):
            db.begin_write()
        if db.get_bind().dialect.name == 'postgresql':
            from app.db.models import User
            db.query(User.id).filter(User.id == owner_id).with_for_update().one()
        query = db.query(Photo).filter(
            Photo.owner_id == owner_id,
            Photo.is_deleted.is_(False), Photo.file_type != FileType.video,
            Photo.processed_tasks['tickets'].as_boolean().is_(True),
            Photo.processed_tasks['tickets_version'].as_integer().is_(None),
            ~db.query(TrainTicket.id).filter(TrainTicket.photo_id == Photo.id).exists(),
            ~db.query(FlightTicket.id).filter(FlightTicket.photo_id == Photo.id).exists(),
            ~db.query(Task.id).filter(
                Task.owner_id == owner_id, Task.type == TaskType.RECOGNIZE_TICKET,
                Task.photo_id == Photo.id,
                Task.status.in_([TaskStatus.PENDING, TaskStatus.PROCESSING, TaskStatus.FAILED]),
            ).exists(),
        )
        if last_id is not None:
            query = query.filter(Photo.id > last_id)
        photos = query.order_by(Photo.id).limit(500).all()
        if not photos:
            db.commit()
            break
        last_id = photos[-1].id
        entries = [dict(type=TaskType.RECOGNIZE_TICKET, owner_id=owner_id,
                        priority=DEFAULT_PRIORITIES[TaskType.RECOGNIZE_TICKET],
                        payload={'photo_id': str(photo.id), 'force': True,
                                 'filename': photo.filename, 'source': 'ticket_recovery'})
                   for photo in photos]
        manager.add_tasks(db, entries)
        count += len(entries)
    return count
