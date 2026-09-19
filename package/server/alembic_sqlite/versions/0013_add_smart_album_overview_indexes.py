"""Add smart album overview query indexes (SQLite).

Revision ID: sqlite_0013
Revises: sqlite_0012
"""

import sqlalchemy as sa
from alembic import op


revision = "sqlite_0013"
down_revision = "sqlite_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_photos_owner_alive",
        "photos",
        ["owner_id", "id"],
        sqlite_where=sa.text("is_deleted = false"),
    )
    op.create_index(
        "ix_faces_identity_alive",
        "faces",
        ["face_identity_id", "photo_id"],
        sqlite_where=sa.text("is_deleted = false"),
    )
    op.create_index(
        "ix_photo_tag_relations_tag_alive",
        "photo_tag_relations",
        ["tag_id", "photo_id"],
        sqlite_where=sa.text("is_deleted = false"),
    )
    op.create_index(
        "ix_photo_metadata_city_photo",
        "photo_metadata",
        ["city", "photo_id"],
        sqlite_where=sa.text("city IS NOT NULL AND city <> ''"),
    )


def downgrade() -> None:
    op.drop_index("ix_photo_metadata_city_photo", table_name="photo_metadata")
    op.drop_index("ix_photo_tag_relations_tag_alive", table_name="photo_tag_relations")
    op.drop_index("ix_faces_identity_alive", table_name="faces")
    op.drop_index("ix_photos_owner_alive", table_name="photos")
