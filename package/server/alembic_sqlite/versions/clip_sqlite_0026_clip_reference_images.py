"""clip_reference_images

Revision ID: clip_sqlite_0026
Revises: clip_sqlite_0025
Create Date: 2026-11-15 19:00:49.930611
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'clip_sqlite_0026'
down_revision: Union[str, Sequence[str], None] = 'clip_sqlite_0025'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('clip_rule_revisions', sa.Column('reference_images', sa.JSON(),
                  server_default='[]', nullable=False))


def downgrade() -> None:
    with op.batch_alter_table('clip_rule_revisions') as batch:
        batch.drop_column('reference_images')
