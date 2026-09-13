from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


def _ensure_sqlite_parent() -> None:
    if not settings.database_url.startswith("sqlite:///"):
        return
    raw_path = settings.database_url.removeprefix("sqlite:///")
    if raw_path != ":memory:":
        Path(raw_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)


_ensure_sqlite_parent()
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False, "timeout": 10} if settings.database_url.startswith("sqlite") else {},
)


if settings.database_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _configure_sqlite(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=10000")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    from . import models  # noqa: F401
    from . import usage_models  # noqa: F401

    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
