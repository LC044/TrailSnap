"""Advertise the public TrailSnap entry point through DNS-SD/mDNS."""

from __future__ import annotations

import ipaddress
import logging
import os
import socket
from urllib.parse import urlparse

from zeroconf import IPVersion, ServiceInfo, Zeroconf

from app.core.config_manager import VERSION


logger = logging.getLogger(__name__)
SERVICE_TYPE = "_trailsnap._tcp.local."


def _resolve_addresses(hostname: str) -> list[bytes]:
    try:
        return [ipaddress.ip_address(hostname).packed]
    except ValueError:
        addresses: list[bytes] = []
        for result in socket.getaddrinfo(hostname, None, socket.AF_INET, socket.SOCK_STREAM):
            packed = ipaddress.ip_address(result[4][0]).packed
            if packed not in addresses:
                addresses.append(packed)
        return addresses


def build_service_info(public_url: str, instance_name: str = "TrailSnap") -> ServiceInfo:
    parsed = urlparse(public_url.strip().rstrip("/"))
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("TRAILSNAP_PUBLIC_URL must be an absolute HTTP(S) URL")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ValueError("TRAILSNAP_PUBLIC_URL must not contain a path, query, or fragment")

    addresses = _resolve_addresses(parsed.hostname)
    if not addresses:
        raise ValueError(f"Unable to resolve public TrailSnap host: {parsed.hostname}")

    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    safe_name = instance_name.strip() or "TrailSnap"
    return ServiceInfo(
        SERVICE_TYPE,
        f"{safe_name}.{SERVICE_TYPE}",
        addresses=addresses,
        port=port,
        properties={
            "url": public_url.strip().rstrip("/"),
            "version": VERSION,
            "api_path": "/api",
        },
        server="trailsnap.local.",
    )


class DiscoveryService:
    def __init__(self) -> None:
        self._zeroconf: Zeroconf | None = None
        self._info: ServiceInfo | None = None

    def start(self) -> None:
        public_url = os.getenv("TRAILSNAP_PUBLIC_URL", "").strip()
        if not public_url:
            logger.info("LAN discovery disabled: TRAILSNAP_PUBLIC_URL is not configured")
            return

        try:
            info = build_service_info(
                public_url,
                os.getenv("TRAILSNAP_INSTANCE_NAME", "TrailSnap"),
            )
            zeroconf = Zeroconf(ip_version=IPVersion.V4Only)
            zeroconf.register_service(info, allow_name_change=True)
        except Exception:
            logger.warning("Unable to publish TrailSnap LAN discovery service", exc_info=True)
            return

        self._zeroconf = zeroconf
        self._info = info
        logger.info("TrailSnap LAN discovery advertised at %s", public_url)

    def stop(self) -> None:
        if not self._zeroconf:
            return
        try:
            if self._info:
                self._zeroconf.unregister_service(self._info)
        finally:
            self._zeroconf.close()
            self._zeroconf = None
            self._info = None
