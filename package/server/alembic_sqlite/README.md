# SQLite migrations

TrailSnap keeps SQLite and PostgreSQL in separate Alembic branches. The SQLite
branch is selected whenever `TS_DB_URL` (preferred) or `DB_URL` is a SQLite
SQLAlchemy URL.

`0001_initial_sqlite_schema.py` is a bootstrap revision used by the desktop
edition. It calls `Base.metadata.create_all()` and creates a usable database,
but it is a dynamic metadata snapshot rather than a frozen historical schema.
Future revisions must therefore be idempotent on a fresh database: inspect
tables, columns, and indexes before adding them, and use Alembic batch operations
for SQLite table changes. Before declaring the SQLite format stable, `0001` can
be replaced with explicit frozen `op.create_table()` operations.

Create and apply a follow-up revision with:

```powershell
$env:TS_DB_URL = "sqlite:///./data/trailsnap.sqlite"
alembic -c alembic_sqlite.ini revision -m "describe change"
alembic -c alembic_sqlite.ini upgrade head
```

Do not point the PostgreSQL migration branch at a SQLite database.
