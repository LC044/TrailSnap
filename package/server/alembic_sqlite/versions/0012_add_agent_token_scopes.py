"""Add least-privilege scopes to Agent Tokens (SQLite).

Revision ID: sqlite_0012
Revises: sqlite_0011
"""

import json

import sqlalchemy as sa
from alembic import op


revision = "sqlite_0012"
down_revision = "sqlite_0011"
branch_labels = None
depends_on = None

DEFAULT_READ_SCOPES = ["photos:read", "albums:read", "people:read"]


def upgrade() -> None:
    with op.batch_alter_table("agent_tokens") as batch_op:
        batch_op.add_column(
            sa.Column(
                "scopes",
                sa.JSON(),
                server_default=json.dumps(DEFAULT_READ_SCOPES),
                nullable=False,
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("agent_tokens") as batch_op:
        batch_op.drop_column("scopes")
