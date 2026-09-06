from typing import List
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field

AGENT_TOKEN_READ_SCOPES = ("photos:read", "albums:read", "people:read")
AGENT_TOKEN_PROPOSAL_SCOPES = ("albums:propose",)
AGENT_TOKEN_SUPPORTED_SCOPES = AGENT_TOKEN_READ_SCOPES + AGENT_TOKEN_PROPOSAL_SCOPES

class AgentTokenBase(BaseModel):
    name: str = Field(..., description="令牌名称")

class AgentTokenCreateAPI(AgentTokenBase):
    expires_at: datetime = Field(..., description="过期时间")
    password: str = Field(..., description="用户密码，用于验证")
    scopes: List[str] = Field(
        default_factory=lambda: list(AGENT_TOKEN_READ_SCOPES),
        description="令牌权限；提案权限只能创建待用户确认的计划，不能直接执行",
    )

class AgentTokenResponse(AgentTokenBase):
    id: UUID
    user_id: UUID
    token: str
    created_at: datetime
    expires_at: datetime
    scopes: List[str]
    is_deleted: bool

    class Config:
        from_attributes = True
