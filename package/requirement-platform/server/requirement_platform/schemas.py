from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RegisterInput(BaseModel):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_.-]+$")
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginInput(BaseModel):
    identifier: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=128)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    username: str
    email: str
    role: str
    is_active: bool
    created_at: datetime


class GitHubIdentityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    github_user_id: int
    login: str
    avatar_url: str | None
    profile_url: str | None
    email: str | None
    linked_at: datetime
    last_login_at: datetime | None


class RoleUpdate(BaseModel):
    role: Literal["viewer", "admin"]


class GitHubIssueLinkInput(BaseModel):
    issue_number: int = Field(ge=1)


class ReasonInput(BaseModel):
    reason: str = Field(min_length=2, max_length=1000)


class AgentTokenCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    scopes: list[Literal[
        "requirements:read", "requirements:write", "requirements:review",
        "versions:read", "versions:write", "github:write"
    ]] = Field(min_length=1)
    expires_in_days: int | None = Field(default=90, ge=1, le=365)


class RequirementCreate(BaseModel):
    type: Literal["bug", "improvement", "feature"]
    title: str = Field(min_length=4, max_length=160)
    description: str = Field(min_length=10, max_length=8000)
    current_behavior: str | None = Field(default=None, max_length=3000)
    expected_behavior: str | None = Field(default=None, max_length=3000)
    steps_to_reproduce: str | None = Field(default=None, max_length=4000)
    severity: Literal["low", "medium", "high", "critical"] = "medium"
    product_version: str | None = Field(default=None, max_length=50)
    environment: dict[str, Any] = Field(default_factory=dict)
    visibility: Literal["public", "private"] = "public"


class RequirementUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=4, max_length=160)
    description: str | None = Field(default=None, min_length=10, max_length=8000)
    current_behavior: str | None = Field(default=None, max_length=3000)
    expected_behavior: str | None = Field(default=None, max_length=3000)
    steps_to_reproduce: str | None = Field(default=None, max_length=4000)
    environment: dict[str, Any] | None = None


class ReviewInput(BaseModel):
    action: Literal["candidate", "needs_information", "rejected", "deferred", "duplicate", "close"]
    reason: str = Field(min_length=2, max_length=2000)
    priority: Literal["low", "normal", "high", "urgent"] = "normal"
    risk_level: Literal["low", "medium", "high", "critical"] = "medium"
    duplicate_of_id: str | None = None


class DeliveryStatusInput(BaseModel):
    status: Literal["not_started", "developing", "pr_open", "testing", "completed", "blocked", "removed"]


class BatchCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    version_name: str = Field(min_length=1, max_length=50, pattern=r"^[A-Za-z0-9._-]+$")
    batch_type: Literal["fix", "feature", "major", "hotfix"] = "feature"
    goal: str = Field(min_length=4, max_length=4000)
    target_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    max_risk_level: Literal["low", "medium", "high", "critical"] = "high"


class BatchItemInput(BaseModel):
    requirement_id: str
    priority_order: int = Field(default=0, ge=0, le=10000)


class BatchStatusInput(BaseModel):
    status: Literal["planning", "candidate_selection", "scope_locked", "developing", "testing", "release_ready", "published", "completed", "blocked", "paused", "cancelled"]
    reason: str = Field(min_length=2, max_length=2000)


class RequirementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    type: str
    title: str
    description: str
    current_behavior: str | None
    expected_behavior: str | None
    steps_to_reproduce: str | None
    severity: str
    product_version: str | None
    environment: dict[str, Any]
    visibility: str
    status: str
    priority: str
    risk_level: str
    review_reason: str | None
    duplicate_of_id: str | None
    github_issue_number: int | None
    github_issue_url: str | None
    github_state: str | None
    created_by: str
    created_at: datetime
    updated_at: datetime
    version: int
    deleted_at: datetime | None
    deleted_by: str | None
    delete_reason: str | None


class BatchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    version_name: str
    batch_type: str
    goal: str
    status: str
    target_date: str | None
    max_risk_level: str
    scope_summary: str | None
    github_milestone_number: int | None
    github_milestone_url: str | None
    created_by: str
    created_at: datetime
    updated_at: datetime
    locked_at: datetime | None
