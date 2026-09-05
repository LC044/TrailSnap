"""Add Agent action lifecycle and audit fields (SQLite).

Revision ID: sqlite_0011
Revises: sqlite_0010
"""

import sqlalchemy as sa
from alembic import op


revision = "sqlite_0011"
down_revision = "sqlite_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("agent_action_plans") as batch_op:
        batch_op.add_column(sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False))
        batch_op.add_column(sa.Column("error_message", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("agent_action_plans") as batch_op:
        batch_op.drop_column("failed_at")
        batch_op.drop_column("expires_at")
        batch_op.drop_column("error_message")
        batch_op.drop_column("attempt_count")
