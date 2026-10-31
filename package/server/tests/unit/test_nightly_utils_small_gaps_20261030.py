"""Nightly watch 2026-10-30 (r3) · 一组小型工具模块的残余盲区。

被测模块（此前覆盖率均低于 90%，只剩几条错误分支未触达）：

- app/utils/hash.py：读取文件失败时返回空字符串而不是抛出异常。
- app/utils/desktop_network.py：忽略 IPv6 地址、路由探测失败时保留已收集的地址。
- app/crud/photo_paths.py：空目录、relpath 失败（跨盘符）时的降级。
- app/utils/github_download.py：已有代理前缀的 URL 不会重复嵌套代理。
- app/core/paths.py：播种反向地理编码数据时的清理与哨兵写入失败。
"""

import builtins
import os
import socket
from types import SimpleNamespace

import pytest

from app.core import paths as core_paths
from app.crud import photo_paths
from app.utils import desktop_network, github_download, hash as hash_utils

pytestmark = [pytest.mark.smoke]


# ---------------------------------------------------------------------------
# app/utils/hash.py
# ---------------------------------------------------------------------------


def test_calculate_file_md5_returns_the_digest(tmp_path, monkeypatch):
    target = tmp_path / "a.bin"
    target.write_bytes(b"trailsnap")
    digest = hash_utils.calculate_file_md5(str(target))
    assert digest and len(digest) == 32


def test_calculate_file_md5_is_empty_for_a_missing_file(tmp_path):
    assert hash_utils.calculate_file_md5(str(tmp_path / "missing.bin")) == ""


def test_calculate_file_md5_swallows_read_errors(tmp_path, monkeypatch):
    target = tmp_path / "a.bin"
    target.write_bytes(b"trailsnap")

    def explode(*args, **kwargs):
        raise OSError("disk is gone")

    monkeypatch.setattr(hash_utils, "budgeted_open", explode)
    assert hash_utils.calculate_file_md5(str(target)) == ""


# ---------------------------------------------------------------------------
# app/utils/desktop_network.py
# ---------------------------------------------------------------------------


def _fake_psutil(monkeypatch, addresses, *, up=True):
    import psutil

    stats = {name: SimpleNamespace(isup=up) for name in addresses}
    monkeypatch.setattr(psutil, "net_if_stats", lambda: stats)
    monkeypatch.setattr(psutil, "net_if_addrs", lambda: addresses)


def test_lan_urls_skip_ipv6_addresses(monkeypatch):
    _fake_psutil(monkeypatch, {
        "Ethernet": [SimpleNamespace(family=socket.AF_INET6, address="fe80::1"),
                     SimpleNamespace(family=socket.AF_INET, address="192.168.1.20")],
    })
    urls = desktop_network.lan_urls(8000)
    assert urls == ["http://192.168.1.20:8000"]


def test_lan_urls_ignore_a_down_interface(monkeypatch):
    _fake_psutil(monkeypatch, {
        "Ethernet": [SimpleNamespace(family=socket.AF_INET, address="192.168.1.20")],
    }, up=False)
    assert desktop_network.lan_urls(8000) == []


def test_lan_urls_keep_the_collected_addresses_when_the_route_probe_fails(monkeypatch):
    _fake_psutil(monkeypatch, {
        "Ethernet": [SimpleNamespace(family=socket.AF_INET, address="192.168.1.20")],
    })

    class BrokenSocket:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

        def connect(self, address):
            raise OSError("no route to host")

    monkeypatch.setattr(socket, "socket", BrokenSocket)
    assert desktop_network.lan_urls(8000) == ["http://192.168.1.20:8000"]


# ---------------------------------------------------------------------------
# app/crud/photo_paths.py
# ---------------------------------------------------------------------------


def test_stored_prefixes_are_empty_for_a_blank_directory():
    assert photo_paths.stored_prefixes("") == []


def test_stored_prefixes_survive_a_failing_relpath(monkeypatch):
    monkeypatch.setattr(photo_paths.os.path, "relpath", lambda *args, **kwargs: (_ for _ in ()).throw(ValueError()))
    assert photo_paths.stored_prefixes("C:/photos") == ["C:/photos/"]


# ---------------------------------------------------------------------------
# app/utils/github_download.py
# ---------------------------------------------------------------------------


def test_github_url_candidates_unwrap_an_existing_mirror():
    url = "https://gh-proxy.com/https://github.com/LC044/TrailSnap/releases"
    candidates = github_download.github_url_candidates(url)
    assert candidates[-1] == "https://github.com/LC044/TrailSnap/releases"
    assert candidates[0] == "https://gh-proxy.com/https://github.com/LC044/TrailSnap/releases"
    assert all("gh-proxy.com/https://gh-proxy.com" not in item for item in candidates)


def test_github_url_candidates_leave_other_hosts_alone():
    url = "https://example.com/file.zip"
    assert github_download.github_url_candidates(url) == [url]


# ---------------------------------------------------------------------------
# app/core/paths.py
# ---------------------------------------------------------------------------


def _seed_env(tmp_path, monkeypatch):
    seed_dir = tmp_path / "seed"
    seed_dir.mkdir()
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setattr(core_paths, "RG_SEED_DIR", str(seed_dir))
    monkeypatch.setattr(core_paths, "RG_DATA_DIR", str(data_dir))
    monkeypatch.setattr(core_paths, "_SEED_SENTINEL", str(data_dir / ".seeded.v1"))
    return seed_dir, data_dir


def test_ensure_rg_seed_copies_the_default_dataset(tmp_path, monkeypatch):
    seed_dir, data_dir = _seed_env(tmp_path, monkeypatch)
    (seed_dir / "CN.csv").write_text("name,lat,lng\n", encoding="utf-8")
    core_paths.ensure_rg_seed()
    assert (data_dir / "CN.csv").is_file()
    assert (data_dir / ".seeded.v1").is_file()


def test_ensure_rg_seed_cleans_up_a_failed_copy(tmp_path, monkeypatch):
    seed_dir, data_dir = _seed_env(tmp_path, monkeypatch)
    (seed_dir / "CN.csv").write_text("name,lat,lng\n", encoding="utf-8")

    def explode(source, target):
        raise OSError("cross device link")

    def refuse(path):
        raise OSError("cannot remove")

    monkeypatch.setattr(core_paths.os, "replace", explode)
    monkeypatch.setattr(core_paths.os, "remove", refuse)
    core_paths.ensure_rg_seed()
    assert not (data_dir / "CN.csv").is_file()


def test_ensure_rg_seed_survives_an_unwritable_sentinel(tmp_path, monkeypatch):
    seed_dir, data_dir = _seed_env(tmp_path, monkeypatch)
    (seed_dir / "CN.csv").write_text("name,lat,lng\n", encoding="utf-8")
    sentinel = data_dir / ".seeded.v1"
    real_open = builtins.open

    def guarded_open(file, mode="r", *args, **kwargs):
        if str(file) == str(sentinel):
            raise OSError("read-only volume")
        return real_open(file, mode, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", guarded_open)
    core_paths.ensure_rg_seed()
    assert (data_dir / "CN.csv").is_file()
    assert not sentinel.exists()
