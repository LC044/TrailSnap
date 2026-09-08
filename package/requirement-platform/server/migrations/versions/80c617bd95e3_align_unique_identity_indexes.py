"""align unique identity indexes

Revision ID: 80c617bd95e3
Revises: 7b4d1f6a20c1
Create Date: 2026-09-09
"""
from typing import Sequence, Union

from alembic import op


revision: str = "80c617bd95e3"
down_revision: Union[str, None] = "7b4d1f6a20c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


INDEXES = (
    ("agent_tokens", "ix_agent_tokens_token_hash", ["token_hash"]),
    ("github_identities", "ix_github_identities_github_user_id", ["github_user_id"]),
    ("github_identities", "ix_github_identities_user_id", ["user_id"]),
    ("oauth_login_grants", "ix_oauth_login_grants_code_hash", ["code_hash"]),
)


def upgrade() -> None:
    for table, name, columns in INDEXES:
        op.drop_index(name, table_name=table)
        op.create_index(name, table, columns, unique=True)


def downgrade() -> None:
    for table, name, columns in reversed(INDEXES):
        op.drop_index(name, table_name=table)
        op.create_index(name, table, columns, unique=False)
