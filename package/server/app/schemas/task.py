from typing import Optional, Any, Dict
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel
from app.db.models.task import TaskStatus, TaskType

class TaskBase(BaseModel):
    type: str
    payload: Optional[Dict[str, Any]] = None

class TaskCreate(TaskBase):
    pass

class TaskResponse(TaskBase):
    id: UUID
    status: str
    result: Optional[Any] = None
    error: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    total_items: Optional[int] = 0
    processed_items: Optional[int] = 0
    attempt_count: int = 0
    next_retry_at: Optional[datetime] = None

    class Config:
        from_attributes = True
