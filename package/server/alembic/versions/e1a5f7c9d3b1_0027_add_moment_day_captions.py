"""add moment_day_captions

Revision ID: e1a5f7c9d3b1
Revises: 33e5bc9135d0
Create Date: 2026-07-27 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e1a5f7c9d3b1'
down_revision: Union[str, None] = '33e5bc9135d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'moment_day_captions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('scope_type', sa.String(length=16), nullable=False, server_default='all'),
        sa.Column('scope_id', sa.String(length=64), nullable=True),
        sa.Column('day', sa.Date(), nullable=False),
        sa.Column('caption', sa.Text(), nullable=False),
        sa.Column('source', sa.String(length=16), nullable=False, server_default='ai'),
        sa.Column('model_name', sa.String(length=64), nullable=True),
        sa.Column('photo_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'scope_type', 'scope_id', 'day', name='uq_moment_day_caption_user_scope_day'),
    )
    op.create_index(op.f('ix_moment_day_captions_id'), 'moment_day_captions', ['id'], unique=False)
    op.create_index(op.f('ix_moment_day_captions_user_id'), 'moment_day_captions', ['user_id'], unique=False)
    op.create_index(op.f('ix_moment_day_captions_day'), 'moment_day_captions', ['day'], unique=False)
    op.create_index('ix_moment_day_captions_user_day', 'moment_day_captions', ['user_id', 'day'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_moment_day_captions_user_day', table_name='moment_day_captions')
    op.drop_index(op.f('ix_moment_day_captions_day'), table_name='moment_day_captions')
    op.drop_index(op.f('ix_moment_day_captions_user_id'), table_name='moment_day_captions')
    op.drop_index(op.f('ix_moment_day_captions_id'), table_name='moment_day_captions')
    op.drop_table('moment_day_captions')
