import asyncio
import sys
from types import SimpleNamespace

import pytest

from app.service.desktop_maintenance import DesktopMaintenance
from app.utils.desktop_network import lan_urls

pytestmark = [pytest.mark.smoke, pytest.mark.module_system]


def test_migration_waits_for_streamed_upload_and_rejects_new_requests(monkeypatch):
    calls = []
    monkeypatch.setitem(sys.modules, "railway.initialization", SimpleNamespace(
        wait_for_initialization=lambda: calls.append("railway"),
    ))

    async def scenario():
        maintenance = DesktopMaintenance()
        finish_upload = asyncio.Event()
        async def upload(scope, receive, send):
            calls.append("upload-start")
            await finish_upload.wait()
            calls.append("upload-committed")
        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}
        responses = []
        async def send(message):
            responses.append(message)
        scope = {"type": "http", "path": "/api/photos/upload", "method": "POST"}
        uploading = asyncio.create_task(maintenance.middleware(scope, receive, send, upload))
        await asyncio.sleep(0)
        preparing = asyncio.create_task(maintenance.prepare(
            SimpleNamespace(stop=lambda **kwargs: calls.append(("scheduler", kwargs["wait"]))),
            SimpleNamespace(drain_for_migration=lambda: calls.append("worker-drained")),
        ))
        await asyncio.sleep(0)
        await maintenance.middleware(scope, receive, send, upload)
        assert responses[0]["status"] == 503
        assert not preparing.done()
        assert "worker-drained" not in calls
        finish_upload.set()
        await uploading
        await preparing
        assert calls.index("upload-committed") < calls.index("worker-drained")
        assert ("scheduler", True) in calls
        assert maintenance.active == 0
    asyncio.run(scenario())


def test_failed_upload_releases_admission_counter():
    async def scenario():
        maintenance = DesktopMaintenance()
        async def broken(*args):
            raise OSError("upload failed")
        with pytest.raises(OSError):
            await maintenance.middleware({"type": "http", "path": "/photos/upload"}, None, None, broken)
        assert maintenance.active == 0
    asyncio.run(scenario())


def test_lan_urls_exclude_loopback_link_local_and_down_interfaces(monkeypatch):
    import socket
    import psutil
    monkeypatch.setattr(psutil, "net_if_stats", lambda: {
        "wifi": SimpleNamespace(isup=True), "offline": SimpleNamespace(isup=False),
    })
    def addresses(*values):
        return [SimpleNamespace(family=socket.AF_INET, address=value) for value in values]
    monkeypatch.setattr(psutil, "net_if_addrs", lambda: {
        "wifi": addresses("192.168.1.20", "127.0.0.1", "169.254.1.1", "0.0.0.0"),
        "offline": addresses("10.0.0.2"),
    })
    assert lan_urls(54321) == ["http://192.168.1.20:54321"]


def test_lan_urls_prefer_wifi_when_proxy_owns_default_route(monkeypatch):
    import socket
    import psutil

    interfaces = {
        "Wi-Fi": "192.168.1.20",
        "vEthernet (Default Switch)": "172.30.96.1",
        "VMware Network Adapter VMnet8": "192.168.142.1",
        "Proxy": "198.18.0.1",
    }
    monkeypatch.setattr(psutil, "net_if_stats", lambda: {
        name: SimpleNamespace(isup=True) for name in interfaces
    })
    monkeypatch.setattr(psutil, "net_if_addrs", lambda: {
        name: [SimpleNamespace(family=socket.AF_INET, address=address)]
        for name, address in interfaces.items()
    })

    class ProxyRoute:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def connect(self, *args):
            pass

        def getsockname(self):
            return ("198.18.0.1", 12345)

    monkeypatch.setattr(socket, "socket", lambda *args: ProxyRoute())
    assert lan_urls(54321) == [
        "http://192.168.1.20:54321",
        "http://172.30.96.1:54321",
        "http://192.168.142.1:54321",
    ]
