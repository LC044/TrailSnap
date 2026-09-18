"""Add smart album overview query indexes.

Revision ID: b72c4d9e5a10
Revises: a91f2d6c4e38
"""

import sqlalchemy as sa
from alembic import op


revision = "b72c4d9e5a10"
down_revision = "a91f2d6c4e38"
branch_labels = None
depends_on = None


INDEXES = [
    (
        "ix_photos_owner_alive",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_photos_owner_alive "
        "ON photos (owner_id, id) WHERE is_deleted = false",
    ),
    (
        "ix_faces_identity_alive",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_faces_identity_alive "
        "ON faces (face_identity_id, photo_id) WHERE is_deleted = false",
    ),
    (
        "ix_photo_tag_relations_tag_alive",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_photo_tag_relations_tag_alive "
        "ON photo_tag_relations (tag_id, photo_id) WHERE is_deleted = false",
    ),
    (
        "ix_photo_metadata_city_photo",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_photo_metadata_city_photo "
        "ON photo_metadata (city, photo_id) WHERE city IS NOT NULL AND city <> ''",
    ),
]


def upgrade() -> None:
    # CONCURRENTLY cannot run inside Alembic's transaction.
    with op.get_context().autocommit_block():
        conn = op.get_bind()
        for _, statement in INDEXES:
            conn.execute(sa.text(statement))


def downgrade() -> None:
    with op.get_context().autocommit_block():
        conn = op.get_bind()
        for name, _ in reversed(INDEXES):
            conn.execute(sa.text(f"DROP INDEX CONCURRENTLY IF EXISTS {name}"))
