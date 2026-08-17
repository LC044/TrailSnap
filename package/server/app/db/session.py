"""Shared SQLAlchemy engine configuration for server and desktop runtimes."""

import os

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.core.paths import DATA_DIR

DATABASE_URL = os.environ.get("TS_DB_URL") or os.environ.get("DB_URL")
if not DATABASE_URL:
    if os.environ.get("TS_DESKTOP") == "1":
        DATABASE_URL = f"sqlite:///{os.path.join(DATA_DIR, 'trailsnap.sqlite')}"
    else:
        raise ValueError("DB_URL or TS_DB_URL environment variable is not set")

IS_SQLITE = DATABASE_URL.startswith("sqlite:")

if IS_SQLITE:
    # 显式放大连接池，避免 SQLAlchemy 默认（pool_size=5, max_overflow=10）
    # 在 PROCESS_BASIC 等批量 CPU 任务并发时被打爆，导致 QueuePool 超时并连锁
    # 拖垮 generate_thumbnail → NoneType 崩溃。SQLite 启用 WAL + busy_timeout
    # 后可稳定承受数十个并发连接。
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False, "timeout": 30},
        pool_pre_ping=True,
        pool_size=20,
        max_overflow=40,
        pool_timeout=30,
        pool_recycle=1800,
    )

    @event.listens_for(engine, "connect")
    def _configure_sqlite(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()
else:
    engine = create_engine(
        DATABASE_URL,
        pool_size=10,
        max_overflow=50,
        pool_timeout=30,
        pool_recycle=1800,
        pool_pre_ping=True,
        connect_args={
            "connect_timeout": 10,
            "keepalives": 1,
            "keepalives_idle": 60,
            "keepalives_interval": 10,
        },
    )

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
