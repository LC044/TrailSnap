"""ticket wallet associations

Revision ID: e15669e7cb95
Revises: d1f139000001
Create Date: 2026-10-06 16:34:58.195016

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e15669e7cb95'
down_revision: Union[str, None] = 'd1f139000001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    uuid_type = sa.CHAR(36) if op.get_bind().dialect.name == "sqlite" else sa.UUID()
    op.create_table("album_tickets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("album_id", uuid_type, sa.ForeignKey("albums.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ticket_type", sa.String(16), nullable=False),
        sa.Column("ticket_id", sa.String(36), nullable=False),
        sa.UniqueConstraint("album_id", "ticket_type", "ticket_id", name="uq_album_ticket"))
    op.create_index("ix_album_tickets_reference", "album_tickets", ["ticket_type", "ticket_id"])
    op.create_table("ticket_dismissals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("memory_id", uuid_type, sa.ForeignKey("memories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ticket_type", sa.String(16), nullable=False),
        sa.Column("ticket_id", sa.String(36), nullable=False),
        sa.UniqueConstraint("memory_id", "ticket_type", "ticket_id", name="uq_ticket_dismissal"))


def downgrade() -> None:
    op.drop_table("ticket_dismissals")
    op.drop_index("ix_album_tickets_reference", table_name="album_tickets")
    op.drop_table("album_tickets")
