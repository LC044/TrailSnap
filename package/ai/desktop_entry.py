#!/usr/bin/env python
"""Frozen entry point for the optional desktop AI sidecar."""

import argparse
import multiprocessing
import os
import signal
import threading
import time


def _watch_parent(parent_pid: int) -> None:
    import psutil

    while True:
        time.sleep(2)
        if not psutil.pid_exists(parent_pid):
            os.kill(os.getpid(), signal.SIGTERM)
            return


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--parent-pid", type=int)
    args = parser.parse_args()
    if args.parent_pid:
        threading.Thread(target=_watch_parent, args=(args.parent_pid,), daemon=True).start()

    import uvicorn
    from desktop_app import app

    uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False)


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
