"""Index the FK columns that photo deletion cascades through (SQLite).

Revision ID: sqlite_0007
Revises: sqlite_0006
Create Date: 2026-09-03

SQLite mirror of PG revision d4c8b1e07a52. With ``PRAGMA foreign_keys=ON`` (set in
app/db/session.py) SQLite scans each referencing table to enforce ON DELETE
CASCADE, so the same missing indexes made emptying a large recycle bin
super-linear. Verified with EXPLAIN QUERY PLAN: ``photo_clusters`` went from
``SCAN`` to ``SEARCH ... USING INDEX``.

There is no CONCURRENTLY here — SQLite has no such option and the desktop
databases this runs against are small enough that a brief lock is fine.

``photo_tag_relations`` is intentionally skipped: its unique constraint is
``(photo_id, tag_id)`` so the autoindex already covers photo_id as its leading
column (confirmed via EXPLAIN QUERY PLAN).
"""

import sqlalchemy as sa
from alembic import op


revision = "sqlite_0007"
down_revision = "sqlite_0006"
branch_labels = None
depends_on = None


# (index name, table, column)
INDEXES = (
    ("ix_album_photos_photo_id", "album_photos", "photo_id"),
    ("ix_photo_clusters_photo_id", "photo_clusters", "photo_id"),
    ("ix_photo_clusters_cluster_id", "photo_clusters", "cluster_id"),
)


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = set(inspector.get_table_names())

    for name, table, column in INDEXES:
        # Desktop databases have travelled through several schema generations, so
        # tolerate a table or index that is already in the expected shape.
        if table not in tables:
            continue
        if name in {idx["name"] for idx in inspector.get_indexes(table)}:
            continue
        op.create_index(name, table, [column])


def downgrade() -> None:
    conn = op.get_bind()
    tables = set(sa.inspect(conn).get_table_names())
    for name, table, _column in reversed(INDEXES):
        if table in tables:
            op.drop_index(name, table_name=table)
