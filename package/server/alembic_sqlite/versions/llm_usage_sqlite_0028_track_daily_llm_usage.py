"""track daily llm usage

Revision ID: llm_usage_sqlite_0028
Revises: cleanup_sqlite_0027
Create Date: 2026-11-19 02:00:55.452906
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from app.db.types import GUID


revision: str = 'llm_usage_sqlite_0028'
down_revision: Union[str, Sequence[str], None] = 'cleanup_sqlite_0027'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "llm_usage_daily",
        sa.Column("owner_id", GUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("day", sa.Date(), primary_key=True),
        sa.Column("source", sa.String(24), primary_key=True),
        sa.Column("connection_id", sa.String(128), primary_key=True),
        sa.Column("model", sa.String(256), primary_key=True),
        sa.Column("requests", sa.BigInteger(), nullable=False),
        sa.Column("reported_requests", sa.BigInteger(), nullable=False),
        sa.Column("cache_reported_requests", sa.BigInteger(), nullable=False),
        sa.Column("input_tokens", sa.BigInteger(), nullable=False),
        sa.Column("output_tokens", sa.BigInteger(), nullable=False),
        sa.Column("cached_input_tokens", sa.BigInteger(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("llm_usage_daily")
