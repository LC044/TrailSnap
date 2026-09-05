"""Add Agent action lifecycle and audit fields.

Revision ID: f32ad910c441
Revises: e2b71a9c4d06
"""

import sqlalchemy as sa
from alembic import op


revision = "f32ad910c441"
down_revision = "e2b71a9c4d06"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agent_action_plans", sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False))
    op.add_column("agent_action_plans", sa.Column("error_message", sa.Text(), nullable=True))
    op.add_column("agent_action_plans", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("agent_action_plans", sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("agent_action_plans", "failed_at")
    op.drop_column("agent_action_plans", "expires_at")
    op.drop_column("agent_action_plans", "error_message")
    op.drop_column("agent_action_plans", "attempt_count")
