"""merge usage and agent-native migration heads

Revision ID: f4a9c2e7d1b6
Revises: b6e21c4f8a90, e7a1b3d5f920
Create Date: 2026-09-13
"""
from typing import Sequence


revision: str = "f4a9c2e7d1b6"
down_revision: tuple[str, str] = ("b6e21c4f8a90", "e7a1b3d5f920")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
