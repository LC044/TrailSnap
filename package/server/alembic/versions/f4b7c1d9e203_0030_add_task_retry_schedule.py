"""Add durable retry scheduling fields to tasks.

Revision ID: f4b7c1d9e203
Revises: a8d2c4e6f901
Create Date: 2026-08-28 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "f4b7c1d9e203"
down_revision: Union[str, None] = "a8d2c4e6f901"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


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
