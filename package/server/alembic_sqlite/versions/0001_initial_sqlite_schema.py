"""Create the initial TrailSnap SQLite schema.

This bootstrap revision creates the current metadata. Follow-up revisions must
therefore be defensive on fresh databases; see ``alembic_sqlite/README.md``.
"""

from alembic import op

import app.db.models  # noqa: F401
from app.db.base import Base

revision = "sqlite_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind(), checkfirst=True)
