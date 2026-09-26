"""add_photo_color_analysis_version

Revision ID: 53d28e061c8e
Revises: sqlite_0015
Create Date: 2026-09-27 03:02:57.448000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '53d28e061c8e'
down_revision: Union[str, Sequence[str], None] = 'sqlite_0015'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('photo_colors', sa.Column('analysis_version', sa.Integer(), nullable=False, server_default='1'))
    op.add_column('photo_colors', sa.Column('analysis_attempted_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index('ix_photo_colors_analysis_version_attempted', 'photo_colors', ['analysis_version', 'analysis_attempted_at'])


def downgrade() -> None:
    op.drop_index('ix_photo_colors_analysis_version_attempted', table_name='photo_colors')
    op.drop_column('photo_colors', 'analysis_attempted_at')
    op.drop_column('photo_colors', 'analysis_version')
