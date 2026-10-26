"""rebuild embeddings for Chinese CLIP

Revision ID: e205c1a0b002
Revises: b54833411649
Create Date: 2026-10-26 23:44:04.971387
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e205c1a0b002'
down_revision: Union[str, Sequence[str], None] = 'b54833411649'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from app.db.embedding_upgrade import queue_chinese_clip_rebuild
    queue_chinese_clip_rebuild(op.get_bind())


def downgrade() -> None:
    from app.db.embedding_upgrade import remove_chinese_clip_rebuild
    remove_chinese_clip_rebuild(op.get_bind())
