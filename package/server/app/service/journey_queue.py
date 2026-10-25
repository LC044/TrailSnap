"""Persist coalesced journey work in the source transaction, without railway I/O."""
from sqlalchemy.orm import Session

from app.db.models.task import Task, TaskStatus, TaskType, DEFAULT_PRIORITIES
from app.db.models.user import User


def enqueue(db: Session, owner_id):
    if owner_id is None:
        return None
    # The same owner lock is used by the matcher. Do not reuse a processing
    # task: a source commit after its snapshot must leave another pending pass.
    db.query(User).filter(User.id == owner_id).with_for_update().first()
    for row in db.new:
        if isinstance(row, Task) and row.type == TaskType.ASSOCIATE_JOURNEYS and row.owner_id == owner_id:
            return row
    row = db.query(Task).filter(
        Task.type == TaskType.ASSOCIATE_JOURNEYS, Task.owner_id == owner_id,
        Task.status == TaskStatus.PENDING,
    ).first()
    if row is None:
        row = Task(type=TaskType.ASSOCIATE_JOURNEYS, owner_id=owner_id,
                   status=TaskStatus.PENDING,
                   priority=DEFAULT_PRIORITIES[TaskType.ASSOCIATE_JOURNEYS],
                   payload={"auto": True})
        db.add(row)
    return row
