#!/usr/bin/env python
"""Frozen entry point used by the TrailSnap desktop shell."""

from __future__ import annotations

import argparse
import multiprocessing
import os
import signal
import threading
import time


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
