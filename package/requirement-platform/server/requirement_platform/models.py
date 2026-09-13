import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"
    __table_args__ = (Index("uq_users_single_owner", "role", unique=True, sqlite_where=text("role = 'owner'")),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16), default="viewer", index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Requirement(Base):
    __tablename__ = "requirements"
    __table_args__ = (
        Index("ix_requirements_status_created", "status", "created_at"),
        Index("ix_requirements_creator_status", "created_by", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    public_number: Mapped[int | None] = mapped_column(Integer, nullable=True, unique=True, index=True)
    type: Mapped[str] = mapped_column(String(24), index=True)
    title: Mapped[str] = mapped_column(String(160), index=True)
    description: Mapped[str] = mapped_column(Text)
    log_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_behavior: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_behavior: Mapped[str | None] = mapped_column(Text, nullable=True)
    steps_to_reproduce: Mapped[str | None] = mapped_column(Text, nullable=True)
    severity: Mapped[str] = mapped_column(String(16), default="medium")
    product_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    environment: Mapped[dict] = mapped_column(JSON, default=dict)
    visibility: Mapped[str] = mapped_column(String(16), default="public", index=True)
    status: Mapped[str] = mapped_column(String(32), default="submitted", index=True)
    priority: Mapped[str] = mapped_column(String(16), default="normal")
    risk_level: Mapped[str] = mapped_column(String(16), default="medium")
    review_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    duplicate_of_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("requirements.id", ondelete="SET NULL"), nullable=True
    )
    github_issue_number: Mapped[int | None] = mapped_column(Integer, nullable=True, unique=True)
    github_issue_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    github_state: Mapped[str | None] = mapped_column(String(24), nullable=True)
    github_pull_requests: Mapped[list] = mapped_column(JSON, default=list)
    source: Mapped[str] = mapped_column(String(16), default="platform", index=True)
    created_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    submitter_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    submitter_contact: Mapped[str | None] = mapped_column(String(255), nullable=True)
    anonymous_upload_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    version: Mapped[int] = mapped_column(Integer, default=1)
    content_revision: Mapped[int] = mapped_column(Integer, default=1)
    state_version: Mapped[int] = mapped_column(Integer, default=1)
    confirmed_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    deleted_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    delete_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class RequirementAttachment(Base):
    __tablename__ = "requirement_attachments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    requirement_id: Mapped[str] = mapped_column(String(36), ForeignKey("requirements.id", ondelete="CASCADE"), index=True)
    uploaded_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    original_name: Mapped[str] = mapped_column(String(255))
    stored_name: Mapped[str] = mapped_column(String(255), unique=True)
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(16))
    content_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    processing_status: Mapped[str] = mapped_column(String(20), default="stored")
    processing_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class GitHubIdentity(Base):
    __tablename__ = "github_identities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True)
    github_user_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    login: Mapped[str] = mapped_column(String(100), index=True)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    profile_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OAuthLoginGrant(Base):
    __tablename__ = "oauth_login_grants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    code_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AgentToken(Base):
    __tablename__ = "agent_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(100))
    token_prefix: Mapped[str] = mapped_column(String(16), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    scopes: Mapped[list] = mapped_column(JSON, default=list)
    project_key: Mapped[str] = mapped_column(String(80), default="trailsnap")
    agent_role: Mapped[str | None] = mapped_column(String(24), nullable=True)
    task_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RequirementRevision(Base):
    __tablename__ = "requirement_revisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    requirement_id: Mapped[str] = mapped_column(String(36), ForeignKey("requirements.id", ondelete="CASCADE"), index=True)
    editor_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"))
    snapshot: Mapped[dict] = mapped_column(JSON)
    reason: Mapped[str] = mapped_column(String(255), default="updated")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ReviewDecision(Base):
    __tablename__ = "requirement_review_decisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    requirement_id: Mapped[str] = mapped_column(String(36), ForeignKey("requirements.id", ondelete="CASCADE"), index=True)
    reviewer_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"))
    action: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TriageReport(Base):
    __tablename__ = "triage_reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    requirement_id: Mapped[str] = mapped_column(String(36), ForeignKey("requirements.id", ondelete="CASCADE"), index=True)
    requirement_version: Mapped[int] = mapped_column(Integer)
    schema_version: Mapped[int] = mapped_column(Integer, default=2)
    status: Mapped[str] = mapped_column(String(20), default="current", index=True)
    prompt_version: Mapped[str] = mapped_column(String(40), default="triage-v2")
    knowledge_revision: Mapped[str | None] = mapped_column(String(80), nullable=True)
    fallback_reason: Mapped[str | None] = mapped_column(String(120), nullable=True)
    provider: Mapped[str] = mapped_column(String(50))
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    report: Mapped[dict] = mapped_column(JSON)
    confidence: Mapped[float] = mapped_column(default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RequirementFollower(Base):
    __tablename__ = "requirement_followers"
    __table_args__ = (UniqueConstraint("requirement_id", "user_id", name="uq_requirement_follower"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    requirement_id: Mapped[str] = mapped_column(String(36), ForeignKey("requirements.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ReleaseBatch(Base):
    __tablename__ = "release_batches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120))
    version_name: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    batch_type: Mapped[str] = mapped_column(String(24), default="feature")
    goal: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="planning", index=True)
    target_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    max_risk_level: Mapped[str] = mapped_column(String(16), default="high")
    scope_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    github_milestone_number: Mapped[int | None] = mapped_column(Integer, nullable=True, unique=True)
    github_milestone_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ReleaseBatchItem(Base):
    __tablename__ = "release_batch_items"
    __table_args__ = (UniqueConstraint("batch_id", "requirement_id", name="uq_batch_requirement"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    batch_id: Mapped[str] = mapped_column(String(36), ForeignKey("release_batches.id", ondelete="CASCADE"), index=True)
    requirement_id: Mapped[str] = mapped_column(String(36), ForeignKey("requirements.id", ondelete="RESTRICT"), index=True)
    priority_order: Mapped[int] = mapped_column(Integer, default=0)
    delivery_status: Mapped[str] = mapped_column(String(24), default="not_started")
    requirement_snapshot: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BackgroundJob(Base):
    __tablename__ = "background_jobs"
    __table_args__ = (Index("ix_jobs_status_available", "status", "available_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    job_type: Mapped[str] = mapped_column(String(40), index=True)
    object_id: Mapped[str] = mapped_column(String(36), index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_object", "object_type", "object_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    actor_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action: Mapped[str] = mapped_column(String(80))
    object_type: Mapped[str] = mapped_column(String(40))
    object_id: Mapped[str] = mapped_column(String(36))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WebhookEvent(Base):
    __tablename__ = "github_webhook_events"

    delivery_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(50))
    payload: Mapped[dict] = mapped_column(JSON)
    processed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AIConnection(Base):
    __tablename__ = "ai_connections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    provider: Mapped[str] = mapped_column(String(40), default="openai_compatible")
    api_base: Mapped[str] = mapped_column(String(500))
    api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    api_key_hint: Mapped[str | None] = mapped_column(String(16), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=45)
    priority: Mapped[int] = mapped_column(Integer, default=100)
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class AIModel(Base):
    __tablename__ = "ai_models"
    __table_args__ = (UniqueConstraint("connection_id", "model_name", name="uq_ai_connection_model"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    connection_id: Mapped[str] = mapped_column(String(36), ForeignKey("ai_connections.id", ondelete="CASCADE"), index=True)
    model_name: Mapped[str] = mapped_column(String(160))
    display_name: Mapped[str] = mapped_column(String(160), default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    supports_json_mode: Mapped[bool] = mapped_column(Boolean, default=True)
    context_window: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reasoning_levels: Mapped[list] = mapped_column(JSON, default=lambda: ["none", "low", "medium", "high"])
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class AITaskRoute(Base):
    __tablename__ = "ai_task_routes"

    task_type: Mapped[str] = mapped_column(String(80), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    model_ids: Mapped[list] = mapped_column(JSON, default=list)
    reasoning_effort: Mapped[str] = mapped_column(String(16), default="none")
    updated_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="RESTRICT"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ClarificationQuestion(Base):
    __tablename__ = "clarification_questions"
    __table_args__ = (UniqueConstraint("requirement_id", "question_id", name="uq_clarification_question"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    requirement_id: Mapped[str] = mapped_column(String(36), ForeignKey("requirements.id", ondelete="CASCADE"), index=True)
    question_id: Mapped[str] = mapped_column(String(40))
    target_field: Mapped[str | None] = mapped_column(String(80), nullable=True)
    question: Mapped[str] = mapped_column(Text)
    rationale: Mapped[str] = mapped_column(Text)
    blocking: Mapped[bool] = mapped_column(Boolean, default=True)
    suggested_options: Mapped[list] = mapped_column(JSON, default=list)
    source_revision: Mapped[int] = mapped_column(Integer)
    round_number: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    answer_source: Mapped[str | None] = mapped_column(String(24), nullable=True)
    answered_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RequirementSpec(Base):
    __tablename__ = "requirement_specs"
    __table_args__ = (UniqueConstraint("requirement_id", "revision", name="uq_requirement_spec_revision"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    requirement_id: Mapped[str] = mapped_column(String(36), ForeignKey("requirements.id", ondelete="CASCADE"), index=True)
    requirement_revision: Mapped[int] = mapped_column(Integer)
    revision: Mapped[int] = mapped_column(Integer)
    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    content: Mapped[dict] = mapped_column(JSON)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    state_version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="RESTRICT"))
    approved_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class AcceptanceCriterion(Base):
    __tablename__ = "acceptance_criteria"
    __table_args__ = (UniqueConstraint("spec_id", "criterion_id", name="uq_spec_criterion"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    spec_id: Mapped[str] = mapped_column(String(36), ForeignKey("requirement_specs.id", ondelete="CASCADE"), index=True)
    criterion_id: Mapped[str] = mapped_column(String(30))
    given_text: Mapped[str] = mapped_column(Text)
    when_text: Mapped[str] = mapped_column(Text)
    then_text: Mapped[str] = mapped_column(Text)
    required: Mapped[bool] = mapped_column(Boolean, default=True)
    verification: Mapped[str] = mapped_column(String(50))
    dataset: Mapped[str | None] = mapped_column(String(120), nullable=True)


class ContextBundle(Base):
    __tablename__ = "context_bundles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    spec_id: Mapped[str] = mapped_column(String(36), ForeignKey("requirement_specs.id", ondelete="RESTRICT"), index=True)
    role: Mapped[str] = mapped_column(String(24), default="coding")
    repository: Mapped[str] = mapped_column(String(200))
    target_branch: Mapped[str] = mapped_column(String(200))
    base_sha: Mapped[str] = mapped_column(String(40), index=True)
    content: Mapped[dict] = mapped_column(JSON)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DeliveryTask(Base):
    __tablename__ = "delivery_tasks"
    __table_args__ = (UniqueConstraint("spec_id", name="uq_delivery_task_spec"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    requirement_id: Mapped[str] = mapped_column(String(36), ForeignKey("requirements.id", ondelete="RESTRICT"), index=True)
    spec_id: Mapped[str] = mapped_column(String(36), ForeignKey("requirement_specs.id", ondelete="RESTRICT"), index=True)
    context_bundle_id: Mapped[str] = mapped_column(String(36), ForeignKey("context_bundles.id", ondelete="RESTRICT"))
    repository: Mapped[str] = mapped_column(String(200))
    target_branch: Mapped[str] = mapped_column(String(200))
    base_sha: Mapped[str] = mapped_column(String(40))
    state: Mapped[str] = mapped_column(String(24), default="queued", index=True)
    state_version: Mapped[int] = mapped_column(Integer, default=1)
    risk_level: Mapped[str] = mapped_column(String(16), default="medium")
    budget: Mapped[dict] = mapped_column(JSON, default=dict)
    dependency_ids: Mapped[list] = mapped_column(JSON, default=list)
    blocked_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class AgentRun(Base):
    __tablename__ = "agent_runs"
    __table_args__ = (Index("ix_agent_runs_claim", "status", "lease_expires_at", "started_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("delivery_tasks.id", ondelete="CASCADE"), index=True)
    attempt_id: Mapped[str] = mapped_column(String(36), default=new_id, unique=True, index=True)
    execution_epoch: Mapped[int] = mapped_column(Integer, default=1)
    role: Mapped[str] = mapped_column(String(24), default="coding")
    provider: Mapped[str] = mapped_column(String(40))
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="running", index=True)
    runner_name: Mapped[str] = mapped_column(String(120))
    lease_token_hash: Mapped[str] = mapped_column(String(64))
    lease_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    session_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    implementation_plan: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    plan_submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    usage: Mapped[dict] = mapped_column(JSON, default=dict)
    exit_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    state_version: Mapped[int] = mapped_column(Integer, default=1)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AgentRunQuestion(Base):
    __tablename__ = "agent_run_questions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True)
    question: Mapped[str] = mapped_column(Text)
    blocking: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(20), default="open")
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PullRequestLink(Base):
    __tablename__ = "delivery_pull_requests"
    __table_args__ = (UniqueConstraint("repository", "pull_request_number", name="uq_delivery_pr"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("delivery_tasks.id", ondelete="CASCADE"), index=True)
    repository: Mapped[str] = mapped_column(String(200))
    pull_request_number: Mapped[int] = mapped_column(Integer)
    url: Mapped[str] = mapped_column(String(500))
    head_sha: Mapped[str] = mapped_column(String(40))
    base_sha: Mapped[str] = mapped_column(String(40))
    state: Mapped[str] = mapped_column(String(20), default="open")
    covered_acceptance_ids: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Artifact(Base):
    __tablename__ = "delivery_artifacts"
    __table_args__ = (UniqueConstraint("run_id", "sha256", "uri", name="uq_run_artifact"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("delivery_tasks.id", ondelete="CASCADE"), index=True)
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    uri: Mapped[str] = mapped_column(String(1000))
    sha256: Mapped[str] = mapped_column(String(64))
    mime_type: Mapped[str] = mapped_column(String(120))
    size_bytes: Mapped[int] = mapped_column(Integer)
    access_level: Mapped[str] = mapped_column(String(20), default="private")
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    producer_token_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DomainEvent(Base):
    __tablename__ = "domain_events"

    sequence: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id: Mapped[str] = mapped_column(String(36), default=new_id, unique=True, index=True)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    aggregate_type: Mapped[str] = mapped_column(String(40))
    aggregate_id: Mapped[str] = mapped_column(String(36), index=True)
    aggregate_version: Mapped[int] = mapped_column(Integer)
    correlation_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    causation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    source: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (UniqueConstraint("actor_key", "operation", "idempotency_key", name="uq_idempotency_operation"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    actor_key: Mapped[str] = mapped_column(String(120))
    operation: Mapped[str] = mapped_column(String(80))
    idempotency_key: Mapped[str] = mapped_column(String(200))
    request_hash: Mapped[str] = mapped_column(String(64))
    response: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
