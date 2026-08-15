#!/usr/bin/env python
"""Frozen entry point for the optional desktop AI sidecar."""

import argparse
import json
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
    parser.add_argument("--port", type=int)
    parser.add_argument("--parent-pid", type=int)
    parser.add_argument("--self-check", action="store_true")
    parser.add_argument("--startup-check", action="store_true")
    args = parser.parse_args()

    if args.self_check:
        from desktop_app import app

        paths = set(app.openapi()["paths"])
        required = {
            "/face/face-recognition",
            "/ocr/predict",
            "/tickets/predict",
            "/classification/",
            "/embedding/text",
            "/embedding/image",
            "/v1/{path}",
            "/ai/models",
        }
        missing = sorted(required - paths)
        if missing:
            raise SystemExit(f"Desktop AI self-check failed; missing routes: {missing}")
        print(json.dumps({"status": "ok", "routes": len(paths)}))
        return

    if args.startup_check:
        # Exercise the real FastAPI lifespan without downloading gigabytes of
        # model data. This catches frozen-runtime startup failures that the
        # route-only self-check cannot see.
        os.environ["TS_AI_SKIP_AUTO_DOWNLOAD"] = "1"
        from fastapi.testclient import TestClient
        from desktop_app import app

        with TestClient(app) as client:
            response = client.get("/health-check")
            response.raise_for_status()
        return

    if args.port is None:
        parser.error("--port is required unless --self-check is used")
    if args.parent_pid:
        threading.Thread(target=_watch_parent, args=(args.parent_pid,), daemon=True).start()

    import uvicorn
    from desktop_app import app

    uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False, log_config=None)


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
