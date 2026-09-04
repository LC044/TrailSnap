"""Add personalized HTML to AI artifacts (SQLite).

Revision ID: sqlite_0009
Revises: sqlite_0008
"""

import sqlalchemy as sa
from alembic import op

revision = "sqlite_0009"
down_revision = "sqlite_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ai_artifacts", sa.Column("html_content", sa.Text(), nullable=True))
    op.add_column("ai_artifacts", sa.Column("html_config", sa.JSON(), nullable=False, server_default="{}"))


def downgrade() -> None:
    op.drop_column("ai_artifacts", "html_config")
    op.drop_column("ai_artifacts", "html_content")
