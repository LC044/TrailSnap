"""LAN addresses shared by desktop connection UI and mDNS advertising."""
import ipaddress
import socket


def lan_urls(port: int) -> list[str]:
    import psutil
    stats = psutil.net_if_stats()
    addresses = {
        address.address
        for name, values in psutil.net_if_addrs().items()
        if name in stats and stats[name].isup
        for address in values
        if address.family == socket.AF_INET
        and ipaddress.ip_address(address.address).is_private
        and not ipaddress.ip_address(address.address).is_loopback
        and not ipaddress.ip_address(address.address).is_link_local
        and not ipaddress.ip_address(address.address).is_unspecified
    }
    primary = None
    try:
        # UDP connect chooses a local route; it sends no packet to this
        # documentation-only address. Prefer Wi-Fi/Ethernet over virtual NICs.
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as route:
            route.connect(("192.0.2.1", 1))
            primary = route.getsockname()[0]
    except OSError:
        pass
    return [f"http://{address}:{port}" for address in sorted(addresses, key=lambda value: (value != primary, value))]
