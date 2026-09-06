from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class AlbumActionProposal(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=4000)
    photo_ids: List[UUID] = Field(min_length=1, max_length=500)
    cover_photo_id: Optional[UUID] = None
    tags: List[str] = Field(default_factory=list, max_length=10)
    album_id: Optional[UUID] = None
    artifact_id: Optional[UUID] = None
    summary: Optional[str] = Field(default=None, max_length=2000)


class AgentRepairSelectionUpdate(BaseModel):
    selected_repair_ids: List[str] = Field(min_length=1, max_length=100)


class AgentActionPlanRead(BaseModel):
    id: UUID
    user_id: UUID
    session_id: Optional[UUID]
    plan_type: str
    title: str
    summary: Optional[str]
    status: str
    operations: Dict[str, Any]
    preview: Dict[str, Any]
    result: Optional[Dict[str, Any]]
    attempt_count: int
    error_message: Optional[str]
    created_at: datetime
    updated_at: datetime
    expires_at: Optional[datetime]
    executed_at: Optional[datetime]
    failed_at: Optional[datetime]
    undone_at: Optional[datetime]

    class Config:
        from_attributes = True
