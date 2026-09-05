"""Add user-owned AI artifact drafts (SQLite).

Revision ID: sqlite_0008
Revises: sqlite_0007
"""

import sqlalchemy as sa
from alembic import op

revision = "sqlite_0008"
down_revision = "sqlite_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_artifacts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("artifact_type", sa.String(50), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("content_json", sa.JSON(), nullable=False),
        sa.Column("source_photo_ids", sa.JSON(), nullable=False),
        sa.Column("source_ticket_ids", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="draft"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by_session_id", sa.String(36), sa.ForeignKey("agent_sessions.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_ai_artifacts_user_id", "ai_artifacts", ["user_id"])
    op.create_index("ix_ai_artifacts_artifact_type", "ai_artifacts", ["artifact_type"])
    op.create_index("ix_ai_artifacts_status", "ai_artifacts", ["status"])
    op.create_index("ix_ai_artifacts_created_by_session_id", "ai_artifacts", ["created_by_session_id"])


def downgrade() -> None:
    op.drop_table("ai_artifacts")
