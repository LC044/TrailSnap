"""Run only the TrailSnap mDNS advertiser on the Docker host network."""

from __future__ import annotations

import logging
import os
import signal
import threading

from app.service.discovery import DiscoveryService


def main() -> None:
    if not os.getenv("TRAILSNAP_PUBLIC_URL", "").strip():
        raise SystemExit("TRAILSNAP_PUBLIC_URL is required for host LAN discovery")

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    stopped = threading.Event()

    def request_stop(*_: object) -> None:
        stopped.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    service = DiscoveryService()
    service.start()
    try:
        stopped.wait()
    finally:
        service.stop()


if __name__ == "__main__":
    main()
