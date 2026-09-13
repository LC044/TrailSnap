"""agent native phase a and b

Revision ID: d6f8a2c4e910
Revises: c4d8a91e7b32
Create Date: 2026-09-12
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "d6f8a2c4e910"
down_revision: Union[str, None] = "c4d8a91e7b32"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
NAMING_CONVENTION = {"fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"}


def upgrade() -> None:
    with op.batch_alter_table("requirements", naming_convention=NAMING_CONVENTION) as batch_op:
        batch_op.add_column(sa.Column("content_revision", sa.Integer(), nullable=False, server_default="1"))
        batch_op.add_column(sa.Column("state_version", sa.Integer(), nullable=False, server_default="1"))
        batch_op.add_column(sa.Column("confirmed_summary", sa.Text(), nullable=True))
        batch_op.drop_constraint("fk_requirements_created_by_users", type_="foreignkey")
        batch_op.create_foreign_key("fk_requirements_created_by_users", "users", ["created_by"], ["id"], ondelete="SET NULL")
    with op.batch_alter_table("agent_tokens") as batch_op:
        batch_op.add_column(sa.Column("project_key", sa.String(80), nullable=False, server_default="trailsnap"))
        batch_op.add_column(sa.Column("agent_role", sa.String(24), nullable=True))
        batch_op.add_column(sa.Column("task_id", sa.String(36), nullable=True))
        batch_op.create_index("ix_agent_tokens_task_id", ["task_id"])
    with op.batch_alter_table("triage_reports") as batch_op:
        batch_op.add_column(sa.Column("schema_version", sa.Integer(), nullable=False, server_default="2"))
        batch_op.add_column(sa.Column("status", sa.String(20), nullable=False, server_default="current"))
        batch_op.add_column(sa.Column("prompt_version", sa.String(40), nullable=False, server_default="triage-v2"))
        batch_op.add_column(sa.Column("knowledge_revision", sa.String(80), nullable=True))
        batch_op.add_column(sa.Column("fallback_reason", sa.String(120), nullable=True))
        batch_op.create_index("ix_triage_reports_status", ["status"])
    with op.batch_alter_table("requirement_attachments", naming_convention=NAMING_CONVENTION) as batch_op:
        batch_op.add_column(sa.Column("content_sha256", sa.String(64), nullable=True))
        batch_op.add_column(sa.Column("processing_status", sa.String(20), nullable=False, server_default="stored"))
        batch_op.add_column(sa.Column("processing_error", sa.Text(), nullable=True))
        batch_op.drop_constraint("fk_requirement_attachments_uploaded_by_users", type_="foreignkey")
        batch_op.create_foreign_key("fk_requirement_attachments_uploaded_by_users", "users", ["uploaded_by"], ["id"], ondelete="SET NULL")

    op.create_table(
        "clarification_questions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("requirement_id", sa.String(36), sa.ForeignKey("requirements.id", ondelete="CASCADE"), nullable=False),
        sa.Column("question_id", sa.String(40), nullable=False), sa.Column("target_field", sa.String(80)),
        sa.Column("question", sa.Text(), nullable=False), sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("blocking", sa.Boolean(), nullable=False), sa.Column("suggested_options", sa.JSON(), nullable=False),
        sa.Column("source_revision", sa.Integer(), nullable=False), sa.Column("round_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False), sa.Column("answer", sa.Text()),
        sa.Column("answer_source", sa.String(24)), sa.Column("answered_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("answered_at", sa.DateTime(timezone=True)), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("requirement_id", "question_id", name="uq_clarification_question"),
    )
    op.create_index("ix_clarification_questions_requirement_id", "clarification_questions", ["requirement_id"])
    op.create_index("ix_clarification_questions_status", "clarification_questions", ["status"])

    op.create_table(
        "requirement_specs", sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("requirement_id", sa.String(36), sa.ForeignKey("requirements.id", ondelete="CASCADE"), nullable=False),
        sa.Column("requirement_revision", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False), sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False), sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False), sa.Column("state_version", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("approved_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("approved_at", sa.DateTime(timezone=True)), sa.Column("superseded_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("requirement_id", "revision", name="uq_requirement_spec_revision"),
    )
    for name, cols in [("ix_requirement_specs_requirement_id", ["requirement_id"]), ("ix_requirement_specs_status", ["status"]), ("ix_requirement_specs_content_hash", ["content_hash"])]:
        op.create_index(name, "requirement_specs", cols)
    op.create_table(
        "acceptance_criteria", sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("spec_id", sa.String(36), sa.ForeignKey("requirement_specs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("criterion_id", sa.String(30), nullable=False), sa.Column("given_text", sa.Text(), nullable=False),
        sa.Column("when_text", sa.Text(), nullable=False), sa.Column("then_text", sa.Text(), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False), sa.Column("verification", sa.String(50), nullable=False),
        sa.Column("dataset", sa.String(120)), sa.UniqueConstraint("spec_id", "criterion_id", name="uq_spec_criterion"),
    )
    op.create_index("ix_acceptance_criteria_spec_id", "acceptance_criteria", ["spec_id"])
    op.create_table(
        "context_bundles", sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("spec_id", sa.String(36), sa.ForeignKey("requirement_specs.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("role", sa.String(24), nullable=False), sa.Column("repository", sa.String(200), nullable=False),
        sa.Column("target_branch", sa.String(200), nullable=False), sa.Column("base_sha", sa.String(40), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False), sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_context_bundles_spec_id", "context_bundles", ["spec_id"])
    op.create_index("ix_context_bundles_base_sha", "context_bundles", ["base_sha"])
    op.create_index("ix_context_bundles_content_hash", "context_bundles", ["content_hash"])
    op.create_table(
        "delivery_tasks", sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("requirement_id", sa.String(36), sa.ForeignKey("requirements.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("spec_id", sa.String(36), sa.ForeignKey("requirement_specs.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("context_bundle_id", sa.String(36), sa.ForeignKey("context_bundles.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("repository", sa.String(200), nullable=False), sa.Column("target_branch", sa.String(200), nullable=False),
        sa.Column("base_sha", sa.String(40), nullable=False), sa.Column("state", sa.String(24), nullable=False),
        sa.Column("state_version", sa.Integer(), nullable=False), sa.Column("risk_level", sa.String(16), nullable=False),
        sa.Column("budget", sa.JSON(), nullable=False), sa.Column("dependency_ids", sa.JSON(), nullable=False),
        sa.Column("blocked_reason", sa.Text()), sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("spec_id", name="uq_delivery_task_spec"),
    )
    for name, cols in [("ix_delivery_tasks_requirement_id", ["requirement_id"]), ("ix_delivery_tasks_spec_id", ["spec_id"]), ("ix_delivery_tasks_state", ["state"])]:
        op.create_index(name, "delivery_tasks", cols)
    op.create_table(
        "agent_runs", sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("task_id", sa.String(36), sa.ForeignKey("delivery_tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("attempt_id", sa.String(36), nullable=False), sa.Column("execution_epoch", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(24), nullable=False), sa.Column("provider", sa.String(40), nullable=False), sa.Column("model", sa.String(100)),
        sa.Column("status", sa.String(24), nullable=False), sa.Column("runner_name", sa.String(120), nullable=False),
        sa.Column("lease_token_hash", sa.String(64), nullable=False), sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=False), sa.Column("session_reference", sa.String(255)),
        sa.Column("implementation_plan", sa.JSON()), sa.Column("plan_submitted_at", sa.DateTime(timezone=True)),
        sa.Column("result", sa.JSON()), sa.Column("usage", sa.JSON(), nullable=False), sa.Column("exit_reason", sa.Text()),
        sa.Column("state_version", sa.Integer(), nullable=False), sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)), sa.UniqueConstraint("attempt_id"),
    )
    op.create_index("ix_agent_runs_task_id", "agent_runs", ["task_id"])
    op.create_index("ix_agent_runs_attempt_id", "agent_runs", ["attempt_id"], unique=True)
    op.create_index("ix_agent_runs_status", "agent_runs", ["status"])
    op.create_index("ix_agent_runs_claim", "agent_runs", ["status", "lease_expires_at", "started_at"])
    op.create_table(
        "agent_run_questions", sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("question", sa.Text(), nullable=False), sa.Column("blocking", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False), sa.Column("answer", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("answered_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_agent_run_questions_run_id", "agent_run_questions", ["run_id"])
    op.create_table(
        "delivery_pull_requests", sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("task_id", sa.String(36), sa.ForeignKey("delivery_tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("repository", sa.String(200), nullable=False), sa.Column("pull_request_number", sa.Integer(), nullable=False),
        sa.Column("url", sa.String(500), nullable=False), sa.Column("head_sha", sa.String(40), nullable=False),
        sa.Column("base_sha", sa.String(40), nullable=False), sa.Column("state", sa.String(20), nullable=False),
        sa.Column("covered_acceptance_ids", sa.JSON(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("repository", "pull_request_number", name="uq_delivery_pr"),
    )
    op.create_index("ix_delivery_pull_requests_task_id", "delivery_pull_requests", ["task_id"])
    op.create_table(
        "delivery_artifacts", sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("task_id", sa.String(36), sa.ForeignKey("delivery_tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False), sa.Column("uri", sa.String(1000), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False), sa.Column("mime_type", sa.String(120), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False), sa.Column("access_level", sa.String(20), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False), sa.Column("producer_token_id", sa.String(36)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "sha256", "uri", name="uq_run_artifact"),
    )
    op.create_index("ix_delivery_artifacts_task_id", "delivery_artifacts", ["task_id"])
    op.create_index("ix_delivery_artifacts_run_id", "delivery_artifacts", ["run_id"])
    op.create_table(
        "domain_events", sa.Column("sequence", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("event_type", sa.String(80), nullable=False), sa.Column("aggregate_type", sa.String(40), nullable=False),
        sa.Column("aggregate_id", sa.String(36), nullable=False), sa.Column("aggregate_version", sa.Integer(), nullable=False),
        sa.Column("correlation_id", sa.String(36)), sa.Column("causation_id", sa.String(36)), sa.Column("source", sa.String(40), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("id"),
    )
    op.create_index("ix_domain_events_id", "domain_events", ["id"], unique=True)
    op.create_index("ix_domain_events_event_type", "domain_events", ["event_type"])
    op.create_index("ix_domain_events_aggregate_id", "domain_events", ["aggregate_id"])
    op.create_index("ix_domain_events_correlation_id", "domain_events", ["correlation_id"])
    op.create_table(
        "idempotency_records", sa.Column("id", sa.String(36), primary_key=True), sa.Column("actor_key", sa.String(120), nullable=False),
        sa.Column("operation", sa.String(80), nullable=False), sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False), sa.Column("response", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("actor_key", "operation", "idempotency_key", name="uq_idempotency_operation"),
    )


def downgrade() -> None:
    for table in ["idempotency_records", "domain_events", "delivery_artifacts", "delivery_pull_requests", "agent_run_questions", "agent_runs", "delivery_tasks", "context_bundles", "acceptance_criteria", "requirement_specs", "clarification_questions"]:
        op.drop_table(table)
    with op.batch_alter_table("triage_reports") as batch_op:
        batch_op.drop_index("ix_triage_reports_status")
        for column in ["fallback_reason", "knowledge_revision", "prompt_version", "status", "schema_version"]:
            batch_op.drop_column(column)
    with op.batch_alter_table("requirement_attachments", naming_convention=NAMING_CONVENTION) as batch_op:
        batch_op.drop_constraint("fk_requirement_attachments_uploaded_by_users", type_="foreignkey")
        batch_op.create_foreign_key("fk_requirement_attachments_uploaded_by_users", "users", ["uploaded_by"], ["id"], ondelete="CASCADE")
        for column in ["processing_error", "processing_status", "content_sha256"]:
            batch_op.drop_column(column)
    with op.batch_alter_table("agent_tokens") as batch_op:
        batch_op.drop_index("ix_agent_tokens_task_id")
        for column in ["task_id", "agent_role", "project_key"]:
            batch_op.drop_column(column)
    with op.batch_alter_table("requirements", naming_convention=NAMING_CONVENTION) as batch_op:
        batch_op.drop_constraint("fk_requirements_created_by_users", type_="foreignkey")
        batch_op.create_foreign_key("fk_requirements_created_by_users", "users", ["created_by"], ["id"], ondelete="CASCADE")
        for column in ["confirmed_summary", "state_version", "content_revision"]:
            batch_op.drop_column(column)
