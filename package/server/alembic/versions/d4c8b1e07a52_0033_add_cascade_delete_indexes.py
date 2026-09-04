"""Index the FK columns that photo deletion cascades through.

Revision ID: d4c8b1e07a52
Revises: b1f8d2e4a603
Create Date: 2026-09-03

Deleting a row from ``photos`` makes PostgreSQL enforce ON DELETE CASCADE on every
referencing table. Without an index on the referencing column that enforcement is
a sequential scan *per deleted row*, so emptying a large recycle bin degrades
super-linearly. Measured on 5000 photos: 1.42s -> 0.33s once these exist.

Two tables needed one:

* ``album_photos`` — its unique constraint is keyed ``(album_id, photo_id)``, so
  the leading column is album_id and the index cannot serve a photo_id lookup.
* ``photo_clusters`` — no unique constraint at all, so nothing to piggyback on.

``photo_tag_relations`` is deliberately absent: its unique constraint is
``(photo_id, tag_id)`` and photo_id is already the leading column, so an extra
index would only cost writes.

The indexes are created CONCURRENTLY. These tables can hold millions of rows in a
mature library, and a plain CREATE INDEX takes an ACCESS EXCLUSIVE lock that would
block all writes for the duration — unacceptable for an in-place upgrade.
CONCURRENTLY cannot run inside a transaction, hence the autocommit block.
"""

import sqlalchemy as sa
from alembic import op


revision = "d4c8b1e07a52"
down_revision = "b1f8d2e4a603"
branch_labels = None
depends_on = None


# (index name, table, column)
INDEXES = (
    ("ix_album_photos_photo_id", "album_photos", "photo_id"),
    ("ix_photo_clusters_photo_id", "photo_clusters", "photo_id"),
    ("ix_photo_clusters_cluster_id", "photo_clusters", "cluster_id"),
)


def _table_missing(conn, table: str) -> bool:
    return table not in sa.inspect(conn).get_table_names()


def _is_invalid(conn, name: str) -> bool:
    """True when ``name`` exists but is an unusable leftover.

    A CREATE INDEX CONCURRENTLY that fails midway (deadlock, cancelled session)
    leaves the index present-but-INVALID. It still occupies the name, so a plain
    IF NOT EXISTS would silently skip it and the planner would never use it —
    the migration would report success while the performance fix is absent.
    """
    return bool(
        conn.execute(
            sa.text(
                "SELECT 1 FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid "
                "WHERE c.relname = :name AND NOT i.indisvalid"
            ),
            {"name": name},
        ).fetchone()
    )


def upgrade() -> None:
    # CONCURRENTLY forbids an open transaction. Alembic wraps migrations in one, so
    # step outside it explicitly.
    with op.get_context().autocommit_block():
        conn = op.get_bind()
        for name, table, column in INDEXES:
            if _table_missing(conn, table):
                continue
            # Clear a broken leftover so the rebuild below actually happens.
            if _is_invalid(conn, name):
                conn.execute(sa.text(f"DROP INDEX CONCURRENTLY IF EXISTS {name}"))
            conn.execute(
                sa.text(
                    f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} ON {table} ({column})"
                )
            )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        conn = op.get_bind()
        for name, _table, _column in reversed(INDEXES):
            conn.execute(sa.text(f"DROP INDEX CONCURRENTLY IF EXISTS {name}"))
