"""add AI model reasoning capabilities and route effort

Revision ID: 1f6c9a2d4e70
Revises: f4a9c2e7d1b6
Create Date: 2026-09-13
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "1f6c9a2d4e70"
down_revision: Union[str, None] = "f4a9c2e7d1b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("ai_models", sa.Column("reasoning_levels", sa.JSON(), nullable=False,
                                         server_default='["none", "low", "medium", "high"]'))
    op.add_column("ai_task_routes", sa.Column("reasoning_effort", sa.String(16), nullable=False,
                                               server_default="none"))


def downgrade() -> None:
    op.drop_column("ai_task_routes", "reasoning_effort")
    op.drop_column("ai_models", "reasoning_levels")
