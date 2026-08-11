# SQLite migrations

TrailSnap Desktop uses this Alembic history independently from the PostgreSQL
history in `alembic/`. The desktop sidecar upgrades this history before the API
application is imported.

When an ORM schema changes, maintain both histories:

```powershell
# PostgreSQL
alembic revision --autogenerate -m "describe change"

# SQLite (set TS_DB_URL to a disposable current SQLite database first)
alembic -c alembic_sqlite.ini revision --autogenerate -m "describe change"
```

SQLite migrations must use Alembic batch operations for table alterations.
The initial revision creates the cross-database metadata baseline; subsequent
revisions should contain explicit operations generated and reviewed against an
up-to-date SQLite database.

The desktop core currently covers users/authentication, photos, albums, tags,
metadata, tasks and JSON-backed embeddings. PostgreSQL-only reporting or
specialized queries must add a dialect implementation before being considered
part of the desktop core.
