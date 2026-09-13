"""add cc-switch input token semantics

Revision ID: b6e21c4f8a90
Revises: a3f7e9c1b5d2
Create Date: 2026-09-13
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "b6e21c4f8a90"
down_revision: Union[str, None] = "a3f7e9c1b5d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "usage_request_logs",
        sa.Column("input_token_semantics", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "usage_daily_rollups",
        sa.Column("input_token_semantics", sa.Integer(), nullable=False, server_default="0"),
    )

    # cc-switch 的 rollup 保存的是已归一化的新增输入；非缓存内含型应用也是 fresh。
    op.execute("UPDATE usage_daily_rollups SET input_token_semantics = 2")
    op.execute(
        "UPDATE usage_request_logs SET input_token_semantics = 2 "
        "WHERE app_type NOT IN ('codex', 'gemini', 'grokbuild')"
    )


def downgrade() -> None:
    op.drop_column("usage_daily_rollups", "input_token_semantics")
    op.drop_column("usage_request_logs", "input_token_semantics")
