# SQLite migrations

TrailSnap keeps SQLite and PostgreSQL in separate Alembic branches. The SQLite
branch is selected whenever `TS_DB_URL` (preferred) or `DB_URL` is a SQLite
SQLAlchemy URL.

`0001_initial_sqlite_schema.py` is a frozen schema snapshot used by the desktop
edition. Historical revisions must not import application models or call
`Base.metadata.create_all()`. Every later ORM schema change needs a matching
SQLite revision so fresh installs and existing databases traverse the same
migration chain. Use Alembic batch operations for SQLite table changes.

Create and apply a follow-up revision with:

```powershell
$env:TS_DB_URL = "sqlite:///./data/trailsnap.sqlite"
alembic -c alembic_sqlite.ini revision -m "describe change"
alembic -c alembic_sqlite.ini upgrade head
```

Do not point the PostgreSQL migration branch at a SQLite database.

For every schema change, create and commit both a PostgreSQL revision under
`alembic/versions/` and a SQLite revision under `alembic_sqlite/versions/`.
