"""Recognize the unpublished index revision used by earlier local test builds."""
from sqlalchemy import inspect, text


def normalize_local_index_revision(connection, obsolete_revision: str, base_revision: str) -> None:
    # Only this exact, known intermediate build may be replayed through the
    # consolidated idempotent index migration. Unknown revisions still fail.
    if not inspect(connection).has_table('alembic_version'):
        return
    versions = connection.execute(text('SELECT version_num FROM alembic_version')).scalars().all()
    if versions == [obsolete_revision]:
        connection.execute(text('UPDATE alembic_version SET version_num=:base WHERE version_num=:old'),
                           {'base': base_revision, 'old': obsolete_revision})
