"""Run the legacy mixed-storage migration inside an Alembic transaction."""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.service.user_storage import migrate_legacy_user_storage


logger = logging.getLogger(__name__)

# Stable signed bigint used only to serialize this migration between
# PostgreSQL application instances.  SQLite serializes schema migrations via
# its database write lock and does not support advisory locks.
POSTGRES_ADVISORY_LOCK_KEY = 6072356627500472371


def run(connection) -> dict[str, int]:
    """Migrate storage once using the transaction owned by Alembic."""
    if connection.dialect.name == "postgresql":
        connection.execute(
            text("SELECT pg_advisory_xact_lock(:lock_key)"),
            {"lock_key": POSTGRES_ADVISORY_LOCK_KEY},
        )

    session = Session(bind=connection, autoflush=False, expire_on_commit=False)
    try:
        result = migrate_legacy_user_storage(session)
        session.flush()
        logger.info("User storage v1 migration complete: %s", result)
        return result
    finally:
        session.close()
