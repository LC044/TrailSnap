"""Add confirmed Agent action plans.

Revision ID: e2b71a9c4d06
Revises: c8f2a1d49073
"""

import sqlalchemy as sa
from alembic import op


revision = "e2b71a9c4d06"
down_revision = "c8f2a1d49073"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_action_plans",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=True),
        sa.Column("plan_type", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("operations", sa.JSON(), nullable=False),
        sa.Column("preview", sa.JSON(), nullable=False),
        sa.Column("undo_data", sa.JSON(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("undone_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["agent_sessions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_action_plans_user_id", "agent_action_plans", ["user_id"])
    op.create_index("ix_agent_action_plans_session_id", "agent_action_plans", ["session_id"])
    op.create_index("ix_agent_action_plans_user_status", "agent_action_plans", ["user_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_agent_action_plans_user_status", table_name="agent_action_plans")
    op.drop_index("ix_agent_action_plans_session_id", table_name="agent_action_plans")
    op.drop_index("ix_agent_action_plans_user_id", table_name="agent_action_plans")
    op.drop_table("agent_action_plans")
