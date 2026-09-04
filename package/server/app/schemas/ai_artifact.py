from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class AIArtifactUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    content_json: dict[str, Any] | None = None
    html_content: str | None = Field(default=None, max_length=500_000)
    html_config: dict[str, Any] | None = None
    status: str | None = Field(default=None, pattern="^(draft|published|archived)$")


class AIArtifactRead(BaseModel):
    id: UUID
    user_id: UUID
    artifact_type: str
    title: str
    content_json: dict[str, Any]
    html_content: str | None
    html_config: dict[str, Any]
    source_photo_ids: list[str]
    source_ticket_ids: list[str]
    status: str
    version: int
    created_by_session_id: UUID | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
