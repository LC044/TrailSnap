"""add photo_colors table for emotion calendar

Revision ID: c7e91f3a2b04
Revises: b21a07c0b227
Create Date: 2026-06-23 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7e91f3a2b04'
down_revision: Union[str, None] = 'b21a07c0b227'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create photo_colors table for emotion color data."""
    op.create_table(
        'photo_colors',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('photo_id', sa.UUID(), nullable=False),
        sa.Column('dominant_colors', sa.JSON(), nullable=True),
        sa.Column('brightness', sa.Float(), nullable=True),
        sa.Column('saturation', sa.Float(), nullable=True),
        sa.Column('emotion_hint', sa.String(20), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['photo_id'], ['photos.id'], ondelete='CASCADE'),
    )
    op.create_index(op.f('ix_photo_colors_photo_id'), 'photo_colors', ['photo_id'], unique=True)


def downgrade() -> None:
    """Drop photo_colors table."""
    op.drop_index(op.f('ix_photo_colors_photo_id'), table_name='photo_colors')
    op.drop_table('photo_colors')
