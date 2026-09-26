"""add_photo_color_analysis_version

Revision ID: 5d30ac3c5d2a
Revises: d9a6e1f20b44
Create Date: 2026-09-27 03:02:56.899017

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5d30ac3c5d2a'
down_revision: Union[str, None] = 'd9a6e1f20b44'
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
