"""Add durable task retry scheduling fields to SQLite.

Revision ID: sqlite_0004
Revises: sqlite_0003
Create Date: 2026-08-28
"""

import sqlalchemy as sa
from alembic import op


revision = "sqlite_0004"
down_revision = "sqlite_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tasks",
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("tasks", sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_tasks_next_retry_at", "tasks", ["next_retry_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_tasks_next_retry_at", table_name="tasks")
    op.drop_column("tasks", "next_retry_at")
    op.drop_column("tasks", "attempt_count")
