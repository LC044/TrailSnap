"""LAN addresses shared by desktop connection UI and mDNS advertising."""
import ipaddress
import socket


def lan_urls(port: int) -> list[str]:
    import psutil
    stats = psutil.net_if_stats()
    private_networks = tuple(ipaddress.ip_network(value) for value in (
        "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
    ))
    virtual_names = ("virtual", "vethernet", "vmware", "vbox", "hyper-v", "docker", "wsl", "tailscale", "zerotier", "wireguard", "tap", "tun")
    addresses: dict[str, int] = {}
    for name, values in psutil.net_if_addrs().items():
        if name not in stats or not stats[name].isup:
            continue
        virtual = int(any(token in name.casefold() for token in virtual_names))
        for address in values:
            if address.family != socket.AF_INET:
                continue
            ip = ipaddress.ip_address(address.address)
            # is_private also includes benchmark/reserved networks, notably the
            # 198.18/15 range used by proxy TUN adapters. Those are not LAN URLs.
            if any(ip in network for network in private_networks):
                addresses[address.address] = min(addresses.get(address.address, virtual), virtual)
    primary = None
    try:
        # UDP connect chooses a local route; it sends no packet to this
        # documentation-only address. Prefer Wi-Fi/Ethernet over virtual NICs.
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as route:
            route.connect(("192.0.2.1", 1))
            primary = route.getsockname()[0]
    except OSError:
        pass
    return [f"http://{address}:{port}" for address in sorted(
        addresses, key=lambda value: (addresses[value], value != primary, ipaddress.ip_address(value)),
    )]
