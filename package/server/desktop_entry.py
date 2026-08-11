#!/usr/bin/env python
"""Frozen entry point used by the TrailSnap desktop shell."""

from __future__ import annotations

import argparse
import multiprocessing
import os
import signal
import secrets
import threading
import time
from pathlib import Path


def _prepare_desktop_database() -> None:
    """Upgrade the local SQLite database before importing the API app."""

    data_dir = Path(os.environ["TS_DATA_DIR"]).resolve()
    session_secret = secrets.token_urlsafe(32)
    os.environ["TS_DESKTOP_SESSION_SECRET"] = session_secret
    secret_file = data_dir / "desktop_session.secret"
    secret_file.write_text(session_secret, encoding="utf-8")
    try:
        secret_file.chmod(0o600)
    except OSError:
        pass
    database_url = f"sqlite:///{(data_dir / 'trailsnap.sqlite').as_posix()}"
    os.environ["TS_DB_URL"] = database_url
    os.environ.setdefault(
        "RAILWAY_DB_URL",
        f"sqlite:///{(data_dir / 'railway.sqlite').as_posix()}",
    )

    from alembic import command
    from alembic.config import Config

    config = Config()
    from app.core.paths import BUNDLE_ROOT

    config.set_main_option("script_location", str(Path(BUNDLE_ROOT) / "alembic_sqlite"))
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")

    from app.db.bootstrap import ensure_desktop_admin
    from app.db.session import SessionLocal

    with SessionLocal() as db:
        ensure_desktop_admin(db)


def _watch_parent(parent_pid: int) -> None:
    """Stop an orphaned sidecar after an abnormal desktop-shell exit."""
    import psutil

    while True:
        time.sleep(2)
        if not psutil.pid_exists(parent_pid):
            os.kill(os.getpid(), signal.SIGTERM)
            return


def main() -> None:
    parser = argparse.ArgumentParser(description="TrailSnap desktop API sidecar")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--parent-pid", type=int)
    args = parser.parse_args()

    if args.parent_pid:
        threading.Thread(
            target=_watch_parent,
            args=(args.parent_pid,),
            name="DesktopParentWatch",
            daemon=True,
        ).start()

    _prepare_desktop_database()

    import uvicorn
    from main import app

    uvicorn.run(
        app,
        host="127.0.0.1",
        port=args.port,
        log_level=os.environ.get("TS_DESKTOP_LOG_LEVEL", "info"),
        access_log=False,
        timeout_keep_alive=60,
    )


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
