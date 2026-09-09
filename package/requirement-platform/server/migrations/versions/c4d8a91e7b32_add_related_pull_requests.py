"""add related pull requests

Revision ID: c4d8a91e7b32
Revises: 9c73e1ab420d
Create Date: 2026-09-10
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "c4d8a91e7b32"
down_revision: Union[str, None] = "9c73e1ab420d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("requirements") as batch_op:
        batch_op.add_column(sa.Column("github_pull_requests", sa.JSON(), nullable=False, server_default="[]"))


def downgrade() -> None:
    with op.batch_alter_table("requirements") as batch_op:
        batch_op.drop_column("github_pull_requests")
