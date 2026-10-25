"""Nightly coverage for ``app.service.discovery`` (LAN / mDNS advertisement).

The 2026-10-24 backend coverage report ranked ``service/discovery.py`` at
80.9% with 13 statements never executed.  The uncovered region is the
*decision* half of the module: the environment switches that disable
advertisement, the hostname-resolution fallback, and the broad ``except``
that keeps a broken zeroconf stack from taking the whole server down.

Discovery is a convenience feature, never a hard requirement -- so the
contract under test is "never raise, never publish a half-built service".
"""

import socket
from unittest.mock import MagicMock, patch

import pytest

from app.core.config_manager import VERSION
from app.service import discovery


pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


def _props(info) -> dict:
    """zeroconf stores TXT properties as bytes; decode them for assertions."""
    decoded = {}
    for key, value in info.properties.items():
        if isinstance(key, bytes):
            key = key.decode("utf-8")
        if isinstance(value, bytes):
            value = value.decode("utf-8")
        decoded[key] = value
    return decoded


@pytest.fixture
def clean_env(monkeypatch):
    """Neutralise every environment switch that influences discovery."""
    monkeypatch.delenv("TRAILSNAP_DISCOVERY_ENABLED", raising=False)
    monkeypatch.delenv("TRAILSNAP_PUBLIC_URL", raising=False)
    monkeypatch.delenv("TRAILSNAP_INSTANCE_NAME", raising=False)
    monkeypatch.delenv("TS_DESKTOP", raising=False)
    monkeypatch.delenv("TS_DESKTOP_INSTANCE_ID", raising=False)


# ---------------------------------------------------------------------------
# _resolve_addresses
# ---------------------------------------------------------------------------


def test_resolve_addresses_uses_literal_ip_directly():
    """A literal IPv4 address short-circuits the DNS lookup."""
    assert discovery._resolve_addresses("127.0.0.1") == [socket.inet_aton("127.0.0.1")]


def test_resolve_addresses_falls_back_to_getaddrinfo():
    """A hostname is resolved through getaddrinfo and de-duplicated."""
    fake = [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.1", 0)),
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.1", 0)),
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.2", 0)),
    ]

    with patch.object(discovery.socket, "getaddrinfo", return_value=fake):
        addresses = discovery._resolve_addresses("trailsnap.local")

    assert addresses == [socket.inet_aton("10.0.0.1"), socket.inet_aton("10.0.0.2")]


# ---------------------------------------------------------------------------
# build_service_info
# ---------------------------------------------------------------------------


def test_build_service_info_rejects_non_http_scheme():
    """Only http(s) may be advertised."""
    with pytest.raises(ValueError, match="absolute HTTP"):
        discovery.build_service_info("ftp://trailsnap.local")


def test_build_service_info_rejects_relative_url():
    """A URL without a host is rejected before any DNS work happens."""
    with pytest.raises(ValueError, match="absolute HTTP"):
        discovery.build_service_info("not-a-url")


def test_build_service_info_rejects_path_query_and_fragment():
    """The advertised URL must be a bare origin."""
    for bad in (
        "http://trailsnap.local/sub",
        "http://trailsnap.local/?x=1",
        "http://trailsnap.local/#frag",
    ):
        with pytest.raises(ValueError, match="must not contain a path"):
            discovery.build_service_info(bad)


def test_build_service_info_rejects_unresolvable_host():
    """An empty resolution result is an explicit error, not a silent skip."""
    with patch.object(discovery.socket, "getaddrinfo", return_value=[]):
        with pytest.raises(ValueError, match="Unable to resolve"):
            discovery.build_service_info("http://nowhere.invalid")


def test_build_service_info_uses_default_port_for_http():
    """http defaults to port 80, https to 443."""
    with patch.object(discovery, "_resolve_addresses", return_value=[socket.inet_aton("10.0.0.1")]):
        http_info = discovery.build_service_info("http://trailsnap.local")
        https_info = discovery.build_service_info("https://trailsnap.local")

    assert http_info.port == 80
    assert https_info.port == 443


def test_build_service_info_normalizes_trailing_slash_and_name():
    """A trailing slash is stripped and a blank instance name falls back."""
    with patch.object(discovery, "_resolve_addresses", return_value=[socket.inet_aton("10.0.0.1")]):
        info = discovery.build_service_info("http://trailsnap.local/", "   ")

    assert _props(info)["url"] == "http://trailsnap.local"
    assert _props(info)["version"] == VERSION
    assert _props(info)["api_path"] == "/api"
    assert info.name.startswith("TrailSnap._trailsnap._tcp.local.")


def test_build_service_info_appends_desktop_instance_suffix(clean_env, monkeypatch):
    """Desktop instances advertise a suffix so several can coexist."""
    monkeypatch.setenv("TS_DESKTOP", "1")
    monkeypatch.setenv("TS_DESKTOP_INSTANCE_ID", "abcdef0123456789")

    with patch.object(discovery, "_resolve_addresses", return_value=[socket.inet_aton("10.0.0.1")]):
        info = discovery.build_service_info("http://trailsnap.local")

    assert info.name.startswith("TrailSnap-abcdef012345._trailsnap._tcp.local.")
    assert info.server == "trailsnap-abcdef012345.local."
    assert _props(info)["instance_id"] == "abcdef0123456789"


def test_build_service_info_ignores_instance_id_without_desktop_flag(clean_env, monkeypatch):
    """Outside the desktop build the instance id must not leak."""
    monkeypatch.setenv("TS_DESKTOP_INSTANCE_ID", "abcdef0123456789")

    with patch.object(discovery, "_resolve_addresses", return_value=[socket.inet_aton("10.0.0.1")]):
        info = discovery.build_service_info("http://trailsnap.local")

    assert info.name.startswith("TrailSnap._trailsnap._tcp.local.")
    assert "instance_id" not in _props(info)


# ---------------------------------------------------------------------------
# DiscoveryService lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("flag", ["0", "false", "no", "off"])
def test_start_is_skipped_when_discovery_disabled(clean_env, monkeypatch, flag):
    """``TRAILSNAP_DISCOVERY_ENABLED`` switches advertisement off."""
    monkeypatch.setenv("TRAILSNAP_DISCOVERY_ENABLED", flag)
    monkeypatch.setenv("TRAILSNAP_PUBLIC_URL", "http://trailsnap.local")

    service = discovery.DiscoveryService()
    with patch("zeroconf.Zeroconf") as zeroconf:
        service.start()

    zeroconf.assert_not_called()
    assert service._zeroconf is None


def test_start_is_skipped_without_public_url(clean_env, monkeypatch):
    """Without ``TRAILSNAP_PUBLIC_URL`` there is nothing to advertise."""
    service = discovery.DiscoveryService()
    with patch("zeroconf.Zeroconf") as zeroconf:
        service.start()

    zeroconf.assert_not_called()
    assert service._zeroconf is None


def test_start_swallows_registration_errors(clean_env, monkeypatch):
    """A broken mDNS stack must never prevent the server from starting."""
    monkeypatch.setenv("TRAILSNAP_PUBLIC_URL", "http://trailsnap.local")

    service = discovery.DiscoveryService()
    with patch.object(discovery, "build_service_info", side_effect=RuntimeError("no zeroconf")):
        service.start()

    assert service._zeroconf is None
    assert service._info is None


def test_start_publishes_and_stop_unregisters(clean_env, monkeypatch):
    """A successful start registers the service and stop() unregisters it."""
    monkeypatch.setenv("TRAILSNAP_PUBLIC_URL", "http://trailsnap.local")

    service = discovery.DiscoveryService()
    fake_zeroconf = MagicMock()
    with patch("zeroconf.Zeroconf", return_value=fake_zeroconf):
        with patch.object(discovery, "build_service_info", return_value=MagicMock()):
            service.start()

    assert service._zeroconf is fake_zeroconf
    fake_zeroconf.register_service.assert_called_once()

    service.stop()
    fake_zeroconf.unregister_service.assert_called_once()
    fake_zeroconf.close.assert_called_once()
    assert service._zeroconf is None
    assert service._info is None


def test_stop_without_start_is_a_noop(clean_env):
    """``stop()`` on a service that never started must not raise."""
    service = discovery.DiscoveryService()
    service.stop()
    assert service._zeroconf is None


