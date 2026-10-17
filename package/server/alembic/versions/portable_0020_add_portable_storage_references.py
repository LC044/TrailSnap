"""add portable storage references

Revision ID: portable_0020
Revises: 4c8b8ca1eaac
Create Date: 2026-10-13 12:32:20.660936

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'portable_0020'
down_revision: Union[str, None] = '4c8b8ca1eaac'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('storage_roots',
        sa.Column('id', sa.UUID(), primary_key=True),
        sa.Column('owner_id', sa.UUID(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('kind', sa.String(32), nullable=False),
        sa.Column('location', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("kind IN ('managed', 'instance-relative', 'external')", name='ck_storage_root_kind'))
    op.create_index('ix_storage_roots_owner', 'storage_roots', ['owner_id'])
    op.add_column('photos', sa.Column('storage_root_id', sa.UUID(), nullable=True))
    op.add_column('photos', sa.Column('storage_relative_path', sa.Text(), nullable=True))
    op.create_foreign_key('fk_photos_storage_root', 'photos', 'storage_roots', ['storage_root_id'], ['id'])
    # Keep unbounded TEXT out of a PostgreSQL B-tree; path comparison is a residual.
    op.create_index('ix_photos_storage_reference', 'photos', ['owner_id', 'storage_root_id'])


def downgrade() -> None:
    op.drop_index('ix_photos_storage_reference', table_name='photos')
    op.drop_constraint('fk_photos_storage_root', 'photos', type_='foreignkey')
    op.drop_column('photos', 'storage_relative_path')
    op.drop_column('photos', 'storage_root_id')
    op.drop_table('storage_roots')
