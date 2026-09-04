"""Add user-owned AI artifact drafts.

Revision ID: a7e4c9d2f601
Revises: d4c8b1e07a52
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "a7e4c9d2f601"
down_revision = "d4c8b1e07a52"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_artifacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("artifact_type", sa.String(50), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("content_json", sa.JSON(), nullable=False),
        sa.Column("source_photo_ids", sa.JSON(), nullable=False),
        sa.Column("source_ticket_ids", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="draft"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by_session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agent_sessions.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    for name, columns in (
        ("ix_ai_artifacts_user_id", ["user_id"]),
        ("ix_ai_artifacts_artifact_type", ["artifact_type"]),
        ("ix_ai_artifacts_status", ["status"]),
        ("ix_ai_artifacts_created_by_session_id", ["created_by_session_id"]),
    ):
        op.create_index(name, "ai_artifacts", columns)


def downgrade() -> None:
    op.drop_table("ai_artifacts")
