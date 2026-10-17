"""add portable storage references

Revision ID: portable_sqlite_0020
Revises: b0b9b9a3a2c0
Create Date: 2026-10-13 12:32:21.611091
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'portable_sqlite_0020'
down_revision: Union[str, Sequence[str], None] = 'b0b9b9a3a2c0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('storage_roots',
        sa.Column('id', sa.CHAR(36), primary_key=True),
        sa.Column('owner_id', sa.CHAR(36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('kind', sa.String(32), nullable=False),
        sa.Column('location', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("kind IN ('managed', 'instance-relative', 'external')", name='ck_storage_root_kind'))
    op.create_index('ix_storage_roots_owner', 'storage_roots', ['owner_id'])
    # SQLite supports a nullable REFERENCES column in ALTER TABLE ADD COLUMN.
    # Do not rebuild the entire photos table or touch existing file paths.
    op.execute('ALTER TABLE photos ADD COLUMN storage_root_id CHAR(36) REFERENCES storage_roots(id)')
    op.add_column('photos', sa.Column('storage_relative_path', sa.Text(), nullable=True))
    op.create_index('ix_photos_storage_reference', 'photos', ['owner_id', 'storage_root_id'])


def downgrade() -> None:
    op.drop_index('ix_photos_storage_reference', table_name='photos')
    with op.batch_alter_table('photos') as batch:
        batch.drop_column('storage_relative_path')
        batch.drop_column('storage_root_id')
    op.drop_table('storage_roots')
