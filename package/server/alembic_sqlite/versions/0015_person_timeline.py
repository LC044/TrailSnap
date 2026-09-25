"""Add person story exclusions (SQLite).

Revision ID: sqlite_0015
Revises: sqlite_0014
"""

import sqlalchemy as sa
from alembic import op

revision = "sqlite_0015"
down_revision = "sqlite_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "person_timeline_hides",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("person_a_id", sa.String(36), sa.ForeignKey("face_identities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("person_b_id", sa.String(36), nullable=False),
        sa.Column("start_at", sa.DateTime(), nullable=False),
        sa.Column("end_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_person_timeline_hides_owner_id", "person_timeline_hides", ["owner_id"])
    op.create_index("ix_person_timeline_hides_scope", "person_timeline_hides", ["owner_id", "person_a_id", "person_b_id", "start_at", "end_at"])


def downgrade() -> None:
    op.drop_table("person_timeline_hides")
