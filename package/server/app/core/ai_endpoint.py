"""Compatibility for the Windows development AI service's IPv4 listener."""
import sys
from urllib.parse import urlsplit, urlunsplit


def normalize_ai_api_url(value: str) -> str:
    # Only migrate the old local default. Custom ports, IPv6, remote services,
    # HTTPS and desktop gateways retain their explicitly configured endpoints.
    if sys.platform == "win32":
        parts = urlsplit(value)
        if parts.scheme == "http" and parts.netloc.lower() == "localhost:8001":
            return urlunsplit(parts._replace(netloc="127.0.0.1:8001"))
    return value
