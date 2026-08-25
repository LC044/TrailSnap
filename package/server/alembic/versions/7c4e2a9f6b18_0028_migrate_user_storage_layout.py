"""Migrate the legacy mixed user storage layout.

Revision ID: 7c4e2a9f6b18
Revises: e1a5f7c9d3b1
Create Date: 2026-08-25 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op

from app.service.migrations.user_storage_v1 import run


revision: str = "7c4e2a9f6b18"
down_revision: Union[str, None] = "e1a5f7c9d3b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    run(op.get_bind())


def downgrade() -> None:
    # Moving user files back into a shared directory could overwrite another
    # user's data.  The storage-layout migration is intentionally irreversible.
    pass
